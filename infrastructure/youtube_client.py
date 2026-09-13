"""유튜브 Data API v3 통신을 전담하는 인프라스트럭처 클라이언트.

이 모듈은 클린 아키텍처의 가장 바깥쪽인 인프라(Infrastructure) 계층에 속합니다.
서비스(Service) 계층이 구글 API의 복잡한 쿼리문이나 HTTP 통신 방식에 대해 몰라도 되도록,
필요한 기능(재생목록 조회, 비디오 정보 조회 등)을 직관적인 파이썬 함수로 추상화하여 제공합니다.
"""
import threading
from typing import Dict, List, Optional
from infrastructure.auth_client import GoogleAuthClient

class YoutubeClient:
    def __init__(self, auth_client: GoogleAuthClient):
        """YoutubeClient 인스턴스를 초기화합니다.
        
        Args:
            auth_client (GoogleAuthClient): 인증 자격증명을 관리하는 클라이언트 객체.
        """
        self.auth_client = auth_client
        self._local = threading.local()

    def _get_service(self):
        """스레드별로 서비스 객체를 캐싱하여 같은 스레드 내에서는 TCP 연결을 재활용합니다."""
        if not hasattr(self._local, 'service'):
            self._local.service = self.auth_client.get_youtube_service()
        return self._local.service

    def get_playlist_metadata(self, playlist_id: str) -> dict:
        """재생목록의 메타데이터(제목, 아이템 개수 등)를 반환합니다."""
        service = self._get_service()
        res = service.playlists().list(part="snippet,contentDetails", id=playlist_id).execute()
        items = res.get("items", [])
        if not items:
            raise ValueError("재생목록을 찾을 수 없거나 비공개/삭제된 상태입니다.")
        return items[0]

    def get_playlist_items_page(self, playlist_id: str, page_token: Optional[str] = None) -> dict:
        """재생목록 내부의 영상 아이템 목록을 페이지 단위로 조회합니다."""
        service = self._get_service()
        req = service.playlistItems().list(
            part='snippet', playlistId=playlist_id, maxResults=50, pageToken=page_token
        )
        return req.execute()

    def get_videos_duration_map(self, video_ids: List[str]) -> Dict[str, str]:
        """비디오 ID 목록에 대한 재생 길이(duration) 맵을 반환합니다."""
        if not video_ids:
            return {}
        service = self._get_service()
        ids_string = ','.join(video_ids)
        req = service.videos().list(part='contentDetails', id=ids_string)
        res = req.execute()
        return {v['id']: v['contentDetails'].get('duration', '') for v in res.get('items', [])}

    def verify_auth(self) -> bool:
        """API 인증이 정상적으로 완료되었는지 확인합니다."""
        try:
            self._get_service()
            return True
        except Exception:
            return False
