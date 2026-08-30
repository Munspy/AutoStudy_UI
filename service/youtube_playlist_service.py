"""YouTube 재생목록 메타데이터 조회 및 분석 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
YouTube Data API v3와 `yt-dlp`를 조합하여 사용자가 등록한 재생목록(Playlist)의 
동영상 리스트, 영상 재생 길이, 최종 업데이트 날짜 등의 메타데이터를 추출하고 분석하는 핵심 도메인 로직을 담당합니다.

UI의 메인 화면(데이터 그리드)이나 Controller 계층이 클라우드 상의 동기화 상태를 판별할 때, 
이 서비스가 유튜브 서버 측의 최신 상태를 실시간으로 긁어와(Scraping/API Fetch) 로컬 및 드라이브 상태와 
교차 검증(Cross-validation)할 수 있도록 데이터를 공급합니다.
"""
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
    """공식 YouTube Data API 조회, yt-dlp 기반 메타데이터 분석 및 상태 교차 검증을 전담하는 비즈니스 서비스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 물리적인 미디어 다운로드나 드라이브 업로드는 수행하지 않으며 
    (해당 역할은 YoutubeMediaService가 담당), 오직 텍스트 기반의 메타데이터(JSON/Dict)를 추출하고 
    정규화(Normalization)하는 읽기 전용(Read-only) 분석 역할에 집중합니다.

    의존성:
    - YouTube Data API v3: `utils.auth_util.get_youtube_service`[cite: 1]
    - 파이프라인 식별자 추출: `service.file_naming_service.FileNamingService`[cite: 1]
    - 미완료 음원 필터링 및 병렬 처리: `concurrent.futures.ThreadPoolExecutor`
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """YoutubePlaylistService 인스턴스를 초기화하고 의존성을 주입받습니다.

        Args:
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 스레드 실행 시 
                진행 상황과 오류를 메인 UI 스레드로 전달하기 위한 콜백. Defaults to None.
        """
        super().__init__(logger_callback=logger_callback)
        self.naming_service = FileNamingService(logger_callback=logger_callback)

    @staticmethod
    def _parse_iso_duration(duration: str) -> str:
        """YouTube ISO 8601 시간 포맷(PT1H2M10S 등)을 인간이 읽기 쉬운 HH:MM:SS 포맷으로 변환하는 내부 헬퍼 함수.

        YouTube Data API v3의 `contentDetails.duration` 필드는 ISO 8601의 기간(Duration) 표준을 따릅니다. 
        이를 UI 데이터 테이블에 직관적으로 시각화하기 위해, 정규식을 사용하여 시(H), 분(M), 초(S) 단위를 
        각각 파싱하고 두 자리 숫자 형식으로 제로 패딩(Zero-padding)하여 문자열로 조립합니다.

        Args:
            duration (str): ISO 8601 포맷의 원본 시간 문자열 (예: 'PT1H2M10S', 'PT45M').

        Returns:
            str: 변환된 'HH:MM:SS' 또는 'MM:SS' 포맷의 문자열. 파싱할 수 없는 입력이 들어오면 "00:00"을 반환합니다.
        """
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
        """주어진 YouTube 웹 URL에서 재생목록의 고유 식별자(playlist_id)를 파싱하여 추출합니다.

        사용자가 UI 입력창에 복사해 넣는 주소는 매우 다양한 형태(예: 모바일 공유 링크, 개별 영상 시청 중인 
        재생목록 링크 등)를 띌 수 있습니다. URL의 쿼리 스트링(Query String)을 안전하게 분해(`urlparse`)하여, 
        재생목록을 뜻하는 `list` 파라미터 값만 핀셋 추출함으로써 하위 API 호출의 안정성을 확보합니다.

        Args:
            url (str): 분석할 원본 YouTube URL 문자열.

        Returns:
            Optional[str]: 파싱에 성공한 재생목록 고유 ID 문자열 (예: 'PLxyz...'). 파라미터가 없으면 None 반환.
        """
        parsed = urlparse.urlparse(url)
        query = urlparse.parse_qs(parsed.query)
        return query["list"][0] if "list" in query else None

    def get_playlist_title(self, url: str) -> str:
        """`yt-dlp`를 사용하여 URL에 해당하는 재생목록의 제목을 매우 빠르게 조회합니다.

        UI에서 사용자가 URL을 등록할 때, 공식 API 인증 절차를 거치지 않고 가볍게 제목만 스크래핑해 오기 위해 사용됩니다. 
        실제 영상 데이터를 다운로드하지 않도록 `extract_flat=True` 옵션을 부여하여 통신 오버헤드와 
        실행 시간을 극단적으로 줄였습니다.

        Args:
            url (str): 조회할 재생목록의 전체 URL.

        Returns:
            str: 획득한 재생목록 제목. 네트워크 오류 등으로 실패할 경우 기본값인 '새 재생목록'을 반환합니다.
        """
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'nocache': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', '새 재생목록')
        except Exception as e:
            self._log(f"⚠️ 재생목록 제목 조회 실패: {str(e)}")
            return '새 재생목록'

    def extract_playlist_info(self, playlist_id: str) -> Dict[str, Any]:
        """YouTube Data API를 사용하여 재생목록의 핵심 메타데이터(제목, 총 영상 개수 등)를 정밀 조회합니다.

        재생목록 등록 시 해당 목록이 유효한지(삭제되거나 비공개 상태가 아닌지) 검증하고, 
        초기 테이블 렌더링에 필요한 총 아이템 수량(`itemCount`)을 파악하기 위해 공식 API를 호출합니다.
        API 호출 중 발생할 수 있는 일일 할당량(Quota) 초과 에러(`HttpError`)를 명시적으로 포착(Catch)하여 
        사용자에게 원인을 명확하게 안내하는 방어 로직이 포함되어 있습니다.[cite: 1]

        Args:
            playlist_id (str): 메타데이터를 조회할 대상 재생목록의 고유 ID.

        Returns:
            Dict[str, Any]: `id`, `title`, `item_count` 키를 포함하는 딕셔너리 정보.

        Raises:
            Exception: 재생목록이 비공개이거나 삭제된 경우, 혹은 API 통신 실패 및 할당량 초과 시 예외가 발생합니다.[cite: 1]
        """
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
        """YouTube API를 통해 재생목록 내의 모든 영상 목록을 순회(Pagination)하며 조회하고 포맷팅합니다.

        한 번의 API 요청(`playlistItems`)으로는 최대 50개의 영상만 가져올 수 있으므로, 
        `nextPageToken`을 활용한 Pagination 루프를 돌며 전체 리스트를 완전히 스크래핑합니다. 
        이후 얻어낸 각 영상의 ID들을 쉼표(,)로 묶어 `videos` API에 배치(Batch) 요청을 한 번 더 날려, 
        영상별 정확한 재생 시간(`duration`)을 조회합니다. 
        
        조회된 제목 문자열을 `FileNamingService`에 통과시켜 파이프라인 식별자(`lesson_id`)를 추출하고, 
        이를 구글 드라이브 상의 기존 데이터(`existing_prefixes`)와 대조하여 이미 추출/동기화가 완료된 영상인지 
        ("O" 또는 "X") 마킹(Tagging)하는 복합 비즈니스 로직입니다.

        Args:
            playlist_id (str): 영상 목록을 긁어올 재생목록의 고유 ID.
            existing_prefixes (set): 구글 드라이브에 이미 처리 완료된 파일들의 `lesson_id`를 담고 있는 집합(Set).
            naming_service (FileNamingService): 도메인 식별자를 추출할 네이밍 서비스 인스턴스.[cite: 1]

        Returns:
            List[Dict]: 제목, 길이, 추출 완료 여부(`extracted`), 영상 고유 ID, `lesson_id(prefix)` 등을 
                포함하는 딕셔너리들의 리스트. UI 테이블 렌더링에 직접 사용됩니다.
        """
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
        """yt-dlp를 이용해 로컬에 등록된 다수의 재생목록들의 최근 업데이트 날짜를 병렬(Parallel)로 확인합니다.

        메인 UI가 구동될 때, 등록된 여러 재생목록(예: 10개)에 대해 하나씩 순차적으로 API 조회를 하면 
        응답 대기(Network Latency) 시간으로 인해 로딩 속도가 심각하게 저하됩니다. 
        이를 해결하기 위해 `concurrent.futures.ThreadPoolExecutor`를 도입하여 여러 `yt-dlp` 조회 요청을 
        병렬(최대 5개 워커)로 분산 처리(Scatter-Gather)합니다. 
        조회된 최종 수정일(`modified_date`)을 기준으로 내림차순 정렬하여, 가장 최근에 영상이 업로드된 
        재생목록이 UI 상단에 노출되도록 돕습니다.[cite: 1]

        Args:
            playlists (list): 업데이트 날짜를 확인할 재생목록 정보 딕셔너리(DB 로드 데이터)들의 리스트.[cite: 1]

        Returns:
            list: `real_last_updated` 필드가 추가되고, 최신 업데이트 순으로 정렬된 새로운 재생목록 리스트.
        """
        def check_update_date(pl):
            ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'playlistend': 1, 'nocache': True}
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
        """구글 드라이브에 이미 전사 대상 오디오나 작업 폴더가 존재하는지 파이프라인 식별자 단위로 교차 검증합니다.

        유튜브에서 영상을 다운로드하기 전, "이미 과거에 다운로드해서 드라이브에 올렸거나, 처리 중인 파일이 있는가?"를 
        검사하는 멱등성(Idempotency) 보장 로직입니다. 
        타겟 구글 드라이브 폴더를 1회 스캔하여 파일명(혹은 폴더명)에서 `lesson_id`를 모두 파싱해낸 뒤, 
        고유한 집합(Set)으로 반환합니다. 이는 `fetch_playlist_videos` 내부에서 각 영상의 추출 여부를 
        "O" 또는 "X"로 마킹(Tagging)하는 데 직접적인 참조 데이터로 쓰입니다.

        Args:
            drive_service (Any): 인증이 완료된 구글 드라이브 API 서비스 객체.[cite: 1]
            folder_id (str): 스캔 대상이 될 구글 드라이브 최상위 폴더 ID.[cite: 1]

        Returns:
            Set[str]: 드라이브 내에서 발견된 처리 완료(혹은 진행 중) 파일들의 고유 교시 식별자(`lesson_id`) 집합. 
                스캔 중 예외 발생 시 빈 Set을 반환하여 시스템 다운을 방지합니다.[cite: 1]
        """
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