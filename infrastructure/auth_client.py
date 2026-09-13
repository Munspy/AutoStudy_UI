import threading
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google_auth_httplib2
import httplib2
from core.config import BASE_DIR, Config

class GoogleAuthClient:
    """Google API 인증 및 서비스 객체 생성 클라이언트.
    
    시스템 전반에서 요구되는 Google OAuth 2.0 인증 흐름을 중앙 집중적으로 관리합니다.
    """
    def __init__(self):
        self.token_path = BASE_DIR / 'token.json'
        self.credentials_path = BASE_DIR / 'credentials.json'
        self._creds_instance = None
        self._auth_lock = threading.RLock()

    def get_credentials(self) -> Credentials:
        with self._auth_lock:
            if self._creds_instance and self._creds_instance.valid:
                return self._creds_instance

            if self.token_path.exists() and not self._creds_instance:
                try:
                    self._creds_instance = Credentials.from_authorized_user_file(
                        str(self.token_path), 
                        Config.GOOGLE_API_SCOPES
                    )
                except Exception as e:
                    print(f"⚠️ 기존 토큰 파일 로드 실패: {e}")
                    self._creds_instance = None

            if self._creds_instance and self._creds_instance.expired and self._creds_instance.refresh_token:
                try:
                    self._creds_instance.refresh(Request())
                except Exception as e:
                    print(f"⚠️ 토큰 갱신 실패 (재인증이 필요합니다): {e}")
                    self._creds_instance = None 
                    if self.token_path.exists():
                        self.token_path.unlink(missing_ok=True)
            
            if not self._creds_instance or not self._creds_instance.valid:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"❌ '{self.credentials_path.name}' 파일이 필요합니다. "
                        f"Google Cloud Console에서 다운로드하여 {BASE_DIR} 위치에 저장하세요."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), 
                    Config.GOOGLE_API_SCOPES
                )
                self._creds_instance = flow.run_local_server(port=0, timeout_seconds=60, open_browser=False)
                
            try:
                with open(self.token_path, 'w', encoding='utf-8') as token:
                    token.write(self._creds_instance.to_json())
            except Exception as e:
                print(f"⚠️ 토큰 파일 저장 중 오류 발생: {e}")
                
            return self._creds_instance

    def get_drive_service(self):
        with self._auth_lock:
            creds = self.get_credentials()
            http = httplib2.Http()
            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            return build('drive', 'v3', http=authed_http, cache_discovery=False)

    def get_youtube_service(self):
        with self._auth_lock:
            creds = self.get_credentials()
            http = httplib2.Http()
            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            return build('youtube', 'v3', http=authed_http, cache_discovery=False)
