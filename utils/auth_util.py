# utils/auth_util.py
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
    """Google Drive API (v3) 서비스 객체 반환 (Thread-safe Singleton 및 자동 토큰 갱신 보장)"""
    global _drive_service
    
    with _auth_lock:
        # 매번 요청 시점에 토큰이 유효한지 크레덴셜 검사 수행 (장기 실행 작업 대응)
        creds = get_credentials()
        if not _drive_service or not creds.valid:
            _drive_service = build('drive', 'v3', credentials=creds)
        return _drive_service

def get_youtube_service():
    """Google YouTube Data API (v3) 서비스 객체 반환 (Thread-safe Singleton 및 자동 토큰 갱신 보장)"""
    global _youtube_service
    
    with _auth_lock:
        # 매번 요청 시점에 토큰이 유효한지 크레덴셜 검사 수행
        creds = get_credentials()
        if not _youtube_service or not creds.valid:
            _youtube_service = build('youtube', 'v3', credentials=creds)
        return _youtube_service