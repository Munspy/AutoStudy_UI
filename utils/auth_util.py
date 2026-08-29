"""Google API 인증 및 서비스 객체 생성 유틸리티 모듈.

이 모듈은 Google OAuth 2.0 인증 흐름을 관리하고, 인증된 자격 증명(Credentials)을 
기반으로 Google Drive 및 YouTube Data API 서비스 클라이언트 객체를 생성하고 제공합니다.

멀티스레드 환경에서도 안전하게 인증 객체와 API 서비스 객체를 공유하기 위해 
스레드 락(Thread Lock)과 싱글톤(Singleton) 패턴을 활용합니다. 전체 애플리케이션 파이프라인에서 
Google API(드라이브 파일 업로드/다운로드, 유튜브 영상 업로드 등)를 호출하기 전 
반드시 거쳐야 하는 핵심 인증 인프라 역할을 담당하고 있습니다.
"""

import os
import threading
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from utils.config import BASE_DIR, Config

# 인증 관련 파일 경로
TOKEN_PATH = BASE_DIR / 'token.json'
CREDENTIALS_PATH = BASE_DIR / 'credentials.json'

# 싱글톤(Singleton) 패턴을 위한 전역 캐시 변수
_creds_instance = None
_drive_service = None
_youtube_service = None

# 멀티스레드 환경 Race Condition 방지 Lock
_auth_lock = threading.Lock()

def get_credentials():
    """Google API 접근을 위한 유효한 OAuth 2.0 자격 증명(Credentials)을 가져옵니다.

    이 함수는 전체 시스템에서 단일 자격 증명 객체를 유지(Singleton)하여 
    불필요한 파일 I/O 및 인증 플로우 재실행을 방지합니다. 
    로직은 다음과 같은 순서로 깊이 있게 동작합니다:
    
    1. 메모리에 유효한 인증 객체가 캐시되어 있다면 즉시 반환하여 성능을 최적화합니다.
    2. 캐시가 없다면 디스크(`TOKEN_PATH`)에서 기존 토큰을 읽어와 복원을 시도합니다.
    3. 로드한 토큰이 만료되었으나 갱신 토큰(Refresh Token)이 존재한다면, 
       사용자 개입 없이 백그라운드에서 Google 인증 서버에 요청하여 토큰을 갱신합니다.
    4. 토큰 파일이 없거나 갱신에 실패한 경우(예: 권한 취소), `CREDENTIALS_PATH`에 위치한 
       클라이언트 시크릿을 사용하여 로컬 웹서버 기반의 최초 OAuth 인증 플로우를 띄워 
       사용자의 직접 로그인을 유도합니다.
    5. 새로 발급받거나 갱신된 토큰은 이후의 빠른 인증을 위해 디스크에 안전하게 캐싱(저장)합니다.

    멀티스레드 환경에서의 Race Condition(여러 스레드가 동시에 토큰을 갱신하거나 인증을 시도하는 현상)을 
    방지하기 위해 내부적으로 `_auth_lock`을 사용하여 임계 영역을 철저히 보호합니다.

    Returns:
        google.oauth2.credentials.Credentials: 
            Google API를 호출할 수 있는 유효한 인증 정보가 담긴 자격 증명 객체.

    Raises:
        FileNotFoundError: `credentials.json` 파일이 지정된 경로에 존재하지 않아 
            로컬 웹서버를 통한 최초 인증 플로우를 진행할 수 없는 경우 발생합니다.
    """
    global _creds_instance
    
    with _auth_lock:
        # 1. 이미 로드된 크레덴셜이 있는 경우 유효성 검사 수행
        if _creds_instance and _creds_instance.valid:
            return _creds_instance

        # 2. 토큰 파일로부터 로드 시도
        if TOKEN_PATH.exists() and not _creds_instance:
            try:
                _creds_instance = Credentials.from_authorized_user_file(
                    str(TOKEN_PATH), 
                    Config.GOOGLE_API_SCOPES
                )
            except Exception as e:
                print(f"⚠️ 기존 토큰 파일 로드 실패: {e}")
                _creds_instance = None

        # 3. 만료되었거나 존재하지 않는 경우 갱신 또는 재인증 수행
        if _creds_instance and _creds_instance.expired and _creds_instance.refresh_token:
            try:
                # [개선] 만료된 토큰 자동 갱신 (Refresh)
                _creds_instance.refresh(Request())
            except Exception as e:
                print(f"⚠️ 토큰 갱신 실패 (재인증이 필요합니다): {e}")
                _creds_instance = None 
                if TOKEN_PATH.exists():
                    TOKEN_PATH.unlink(missing_ok=True)
        
        # 4. 여전히 유효한 크레덴셜이 없다면 로컬 웹서버를 통한 최초 인증 플로우 실행
        if not _creds_instance or not _creds_instance.valid:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"❌ '{CREDENTIALS_PATH.name}' 파일이 필요합니다. "
                    f"Google Cloud Console에서 다운로드하여 {BASE_DIR} 위치에 저장하세요."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), 
                Config.GOOGLE_API_SCOPES
            )
            _creds_instance = flow.run_local_server(port=0)
            
        # 5. 갱신되거나 새로 발급받은 토큰을 안전하게 파일로 저장
        try:
            with open(TOKEN_PATH, 'w', encoding='utf-8') as token:
                token.write(_creds_instance.to_json())
        except Exception as e:
            print(f"⚠️ 토큰 파일 저장 중 오류 발생: {e}")
            
        return _creds_instance

def get_drive_service():
    """Google Drive API (v3) 서비스 객체를 반환합니다.

    이 함수는 애플리케이션의 어느 곳에서든 Drive API를 호출할 수 있도록 
    빌드된 서비스 객체(Resource object)를 싱글톤으로 제공합니다. 
    장기 실행 작업(Long-running background tasks) 중에 API 토큰이 만료될 수 있으므로, 
    호출될 때마다 내부적으로 `get_credentials()`를 통해 현재 자격 증명의 
    유효성을 검증하고, 만료되거나 유효하지 않은 경우 서비스 객체를 새 크레덴셜로 다시 빌드합니다.
    
    스레드 안전성(Thread-safety)이 보장되므로 여러 스레드에서 동시에 Drive 서비스에 
    접근하더라도 인증 충돌이나 객체 재생성 문제가 발생하지 않습니다.

    Returns:
        googleapiclient.discovery.Resource: 
            Google Drive API(v3)와 상호작용할 수 있는 빌드된 서비스 객체.
    """
    global _drive_service
    
    with _auth_lock:
        # 매번 요청 시점에 토큰이 유효한지 크레덴셜 검사 수행 (장기 실행 작업 대응)
        creds = get_credentials()
        if not _drive_service or not creds.valid:
            _drive_service = build('drive', 'v3', credentials=creds)
        return _drive_service

def get_youtube_service():
    """Google YouTube Data API (v3) 서비스 객체를 반환합니다.

    이 함수는 YouTube Data API(예: 영상 업로드, 메타데이터 수정 등)를 호출하기 위한 
    클라이언트 서비스 객체를 빌드하여 반환합니다. `get_drive_service` 함수와 마찬가지로 
    싱글톤 패턴을 기반으로 작동하며, 호출 시점에 크레덴셜의 유효성을 다시 확인하여 
    토큰 만료로 인한 업로드 또는 API 호출 실패를 사전에 방지합니다.

    동기화 락(`_auth_lock`) 안에서 동작하므로 멀티스레드 기반의 
    비동기 업로드 또는 대용량 배치 처리 작업에서도 안전하게 호출되어 사용될 수 있습니다.

    Returns:
        googleapiclient.discovery.Resource: 
            Google YouTube Data API(v3)와 상호작용할 수 있는 빌드된 서비스 객체.
    """
    global _youtube_service
    
    with _auth_lock:
        # 매번 요청 시점에 토큰이 유효한지 크레덴셜 검사 수행
        creds = get_credentials()
        if not _youtube_service or not creds.valid:
            _youtube_service = build('youtube', 'v3', credentials=creds)
        return _youtube_service