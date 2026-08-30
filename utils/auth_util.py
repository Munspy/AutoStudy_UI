"""Google API 인증 및 서비스 객체 생성 유틸리티 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 파이프라인 중 **Utils(유틸리티) 계층**에 속합니다.
시스템 전반에서 요구되는 Google OAuth 2.0 인증 흐름을 중앙 집중적으로 관리하며, 
인증된 자격 증명(Credentials)을 기반으로 Google Drive 및 YouTube Data API 서비스 클라이언트 객체를 
생성하고 제공하는 핵심 인프라 역할을 담당합니다.

PDF 처리, Whisper 음성 변환, Gemini 분석 등을 수행하는 Service 및 Worker 계층의 비동기 백그라운드 작업들이 
Google API(예: 드라이브 파일 동기화, 유튜브 메타데이터 접근 등)를 호출할 때, 멀티스레드 환경에서도 
안전하게 인증 객체를 공유할 수 있도록 스레드 락(Thread Lock)과 싱글톤(Singleton) 패턴을 제공합니다.
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

# 멀티스레드 환경 Race Condition 방지 Lock (Reentrant Lock으로 변경하여 데드락 방지)
_auth_lock = threading.RLock()

def get_credentials():
    """Google API 접근을 위한 유효한 OAuth 2.0 자격 증명(Credentials)을 가져옵니다.

    이 함수는 전체 시스템에서 단일 자격 증명 객체를 유지(Singleton)하여 불필요한 파일 I/O 및 인증 플로우 재실행을 방지합니다.
    특히, AutoStudy_UI의 Worker 계층(백그라운드 스레드 및 Watchdog)이 사용자 개입 없이 자동화된 파이프라인을 
    지속적으로 실행할 수 있도록 보장하는 핵심 로직을 포함합니다. 
    
    장기 실행되는 백그라운드 작업 중 토큰이 만료될 경우, 파이프라인이 중단되지 않도록 `refresh_token`을 사용해 
    백그라운드에서 자동으로 토큰을 갱신합니다. 또한 멀티스레드 환경에서 여러 Worker가 동시에 이 함수를 호출할 때 
    발생할 수 있는 Race Condition(다중 인증 플로우 실행 및 파일 덮어쓰기 등)을 방지하기 위해 `_auth_lock`을 통해 임계 영역을 보호합니다.

    로직 실행 순서:
    1. 메모리에 캐시된 유효한 인증 객체가 있다면 즉시 반환(성능 최적화).
    2. 캐시가 없으면 로컬 파일(token.json)에서 복원 시도.
    3. 토큰이 만료되었고 갱신 토큰이 있다면 백그라운드 자동 갱신.
    4. 유효한 토큰이 전무한 경우 로컬 웹서버 기반 최초 OAuth 인증 플로우 실행.
    5. 신규 및 갱신 토큰을 로컬에 안전하게 캐싱.

    Args:
        없음

    Returns:
        google.oauth2.credentials.Credentials: 
            Google API를 호출할 수 있는 유효한 인증 정보가 담긴 자격 증명 객체.

    Raises:
        FileNotFoundError: 
            최초 인증에 필요한 클라이언트 시크릿(`credentials.json`) 파일이 지정된 경로에 존재하지 않아 
            인증 플로우를 시작할 수 없는 경우 발생합니다.
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
            _creds_instance = flow.run_local_server(port=0, timeout_seconds=30)
            
        # 5. 갱신되거나 새로 발급받은 토큰을 안전하게 파일로 저장
        try:
            with open(TOKEN_PATH, 'w', encoding='utf-8') as token:
                token.write(_creds_instance.to_json())
        except Exception as e:
            print(f"⚠️ 토큰 파일 저장 중 오류 발생: {e}")
            
        return _creds_instance

def get_drive_service():
    """Google Drive API (v3) 서비스 객체를 반환합니다.

    이 함수는 Service 계층(예: DriveSyncService) 및 Worker 계층에서 Google Drive 상호작용(파일 업로드, 다운로드, 동기화)을 
    수행할 수 있도록 빌드된 서비스 클라이언트를 싱글톤 형태로 제공합니다. 

    자동화된 백그라운드 파이프라인 특성상 대용량 PDF 분석이나 Whisper AI 변환과 같은 장기 실행 작업(Long-running tasks) 이후에 
    Drive API가 호출될 가능성이 높습니다. 따라서 호출 시점마다 `get_credentials()`를 통해 크레덴셜 유효성을 강제로 재확인하고, 
    토큰 만료로 인한 API 호출 실패(예외 발생)를 원천 차단합니다. 여러 스레드가 동시에 서비스 객체를 요청하더라도 
    내부 락(Lock)을 통해 안전하게 하나의 유효한 객체만 반환하도록 보장합니다.

    Args:
        없음

    Returns:
        googleapiclient.discovery.Resource: 
            Google Drive API(v3)와 안전하게 통신할 수 있는 빌드된 서비스 객체.
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

    이 함수는 Service 계층에서 YouTube Data API(예: 플레이리스트 정보 수집, 자막(Transcript) 처리 등)와 
    연동하기 위한 클라이언트 서비스 객체를 빌드하여 반환합니다. 

    YouTube API 연동 역시 대규모 배치 데이터 처리나 큐(Queue) 기반 비동기 Worker 환경에서 수행되므로, 
    토큰 만료 방지 및 스레드 안전성 확보가 필수적입니다. 이 함수는 싱글톤 패턴과 스레드 락을 활용해 
    안정적인 YouTube 리소스 객체 상태를 유지하며, 만료된 크레덴셜을 감지하면 즉시 갱신된 크레덴셜로 
    서비스 객체를 재생성합니다.

    Args:
        없음

    Returns:
        googleapiclient.discovery.Resource: 
            Google YouTube Data API(v3)와 안전하게 상호작용할 수 있는 빌드된 서비스 객체.
    """
    global _youtube_service
    
    with _auth_lock:
        # 매번 요청 시점에 토큰이 유효한지 크레덴셜 검사 수행
        creds = get_credentials()
        if not _youtube_service or not creds.valid:
            _youtube_service = build('youtube', 'v3', credentials=creds)
        return _youtube_service