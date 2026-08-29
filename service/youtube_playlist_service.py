# service/youtube_playlist_service.py
import urllib.parse as urlparse
import re
from pathlib import Path
from typing import Optional, Union, Dict, Any, List, Callable, Set
import concurrent.futures

import yt_dlp
from googleapiclient.errors import HttpError

from service.file_naming_service import FileNamingService
from utils.auth_util import get_youtube_service
from base.base_service import BaseService

PathLike = Union[str, Path]

class YoutubePlaylistService(BaseService):
    """
    공식 YouTube Data API 조회, yt-dlp 기반 음원 추출 및
    구글 드라이브 업로드를 전담하는 유튜브 비즈니스 로직 서비스입니다.
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        self.naming_service = FileNamingService(logger_callback=logger_callback)

    @staticmethod
    def _parse_iso_duration(duration: str) -> str:
        """YouTube ISO 8601 시간 포맷(PT1H2M10S 등)을 HH:MM:SS 포맷으로 변환하는 내부 헬퍼 함수"""
        if not duration:
            return "00:00"
            
        match = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', duration)
        if not match:
            return "00:00"
            
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    # ==========================================
    # 1. 유튜브 메타데이터 및 URL 분석
    # ==========================================
    def parse_playlist_id(self, url: str) -> Optional[str]:
        parsed = urlparse.urlparse(url)
        query = urlparse.parse_qs(parsed.query)
        return query["list"][0] if "list" in query else None

    def get_playlist_title(self, url: str) -> str:
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', '새 재생목록')
        except Exception as e:
            self._log(f"⚠️ 재생목록 제목 조회 실패: {str(e)}")
            return '새 재생목록'

    def extract_playlist_info(self, playlist_id: str) -> Dict[str, Any]:
        """YouTube Data API를 사용하여 재생목록 메타데이터(제목, 영상 수) 조회"""
        youtube_service = get_youtube_service()
        try:
            res = (
                youtube_service.playlists()
                .list(part="snippet,contentDetails", id=playlist_id)
                .execute()
            )
            items = res.get("items", [])
            if not items:
                raise ValueError("재생목록을 찾을 수 없거나 비공개/삭제된 상태입니다.")

            item = items[0]
            return {
                "id": playlist_id,
                "title": item["snippet"]["title"],
                "item_count": item["contentDetails"]["itemCount"],
            }
        except HttpError as e:
            self._log(f"❌ YouTube API 통신 에러 (할당량 초과 의심): {e.reason}")
            raise Exception(f"재생목록 정보 조회 실패: {e.reason}")
        except Exception as e:
            raise Exception(f"❌ 재생목록 정보 조회 실패 ({playlist_id}): {str(e)}")

    def fetch_playlist_videos(self, playlist_id: str, existing_prefixes: set, naming_service) -> List[Dict]:
        """YouTube API를 통해 영상 목록을 조회하고 포맷팅합니다."""
        youtube_service = get_youtube_service()
        videos = []
        next_page_token = None
        
        while True:
            pl_request = youtube_service.playlistItems().list(
                part='snippet', playlistId=playlist_id, maxResults=50, pageToken=next_page_token
            )
            pl_response = pl_request.execute()

            vid_ids = []
            for item in pl_response.get('items', []):
                vid = item['snippet']['resourceId'].get('videoId')
                title = item['snippet'].get('title', '')
                if vid: vid_ids.append((vid, title))

            if not vid_ids: break

            ids_string = ','.join([v[0] for v in vid_ids])
            vid_request = youtube_service.videos().list(part='contentDetails', id=ids_string)
            vid_response = vid_request.execute()

            duration_map = {v['id']: v['contentDetails'].get('duration', '') for v in vid_response.get('items', [])}

            for vid, title in vid_ids:
                duration_iso = duration_map.get(vid, '')
                # 내부 헬퍼 함수 적용
                length_str = self._parse_iso_duration(duration_iso)
                prefix = naming_service.extract_lesson_id(title)
                
                extracted_status = "O" if prefix and prefix in existing_prefixes else "X"
                videos.append({
                    "title": title, "length": length_str, "extracted": extracted_status, 
                    "vid": vid, "prefix": prefix
                })

            next_page_token = pl_response.get('nextPageToken')
            if not next_page_token: break

        return videos

    def check_playlists_updates(self, playlists: list) -> list:
        """yt-dlp를 이용해 다수 재생목록의 최근 업데이트 날짜를 병렬 확인합니다."""
        def check_update_date(pl):
            ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'playlistend': 1}
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(pl['url'], download=False)
                    pl['real_last_updated'] = info.get('modified_date', '00000000')
            except Exception:
                pl['real_last_updated'] = '00000000'
            return pl

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            updated_playlists = list(executor.map(check_update_date, playlists))

        updated_playlists.sort(key=lambda x: x.get('real_last_updated', '00000000'), reverse=True)
        return updated_playlists

    def get_existing_prefixes_in_drive(self, drive_service: Any, folder_id: str) -> Set[str]:
        """드라이브에 이미 전사 대상 오디오나 폴더가 존재하는지 교차 검증"""
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            results = drive_service.files().list(q=query, fields="files(id, name, mimeType)", pageSize=1000).execute()
            items = results.get('files', [])
            
            existing_prefixes = set()
            media_extensions = ('.wav', '.mp3', '.m4a', '.mp4', '.mkv', '.webm', '.avi')
            
            for item in items:
                file_name = item.get('name', '')
                mime_type = item.get('mimeType', '')
                prefix = self.naming_service.extract_lesson_id(file_name)
                
                if not prefix:
                    continue
                if mime_type == 'application/vnd.google-apps.folder' and file_name == prefix:
                    existing_prefixes.add(prefix)
                elif file_name.lower().endswith(media_extensions):
                    existing_prefixes.add(prefix)
                    
            return existing_prefixes
        except Exception as e:
            self._log(f"⚠️ 드라이브 기존 파일 검증 중 오류 발생: {str(e)}")
            return set()