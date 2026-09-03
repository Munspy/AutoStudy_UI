"""유튜브 재생목록 동기화 및 다운로드/업로드 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab8YoutubePlaylist) 및 Service 레이어와 연동하여 재생목록의 업데이트 상태를 확인하고,
필요한 영상을 다운로드 또는 구글 드라이브에 업로드하는 워커들을 제어합니다.
"""
from base.base_controller import BaseController
from worker.youtube.youtube_worker import PlaylistFetchWorker, YoutubeUploadWorker, PlaylistUpdateCheckerWorker
from service.youtube_playlist_service import YoutubePlaylistService
from service.playlist_repository import PlaylistRepository
from PyQt6.QtCore import pyqtSignal

_yt_service = YoutubePlaylistService()
_repo = PlaylistRepository()

def load_csv_data(): return _repo.load_playlists()
def parse_playlist_id(url): return _yt_service.parse_playlist_id(url)
def add_playlist_to_csv(name, url, pid): _repo.add_playlist(name, url, pid)
def delete_playlist(pid): _repo.delete_playlist(pid)
def rename_playlist(pid, name): _repo.rename_playlist(pid, name)
def get_playlist_title(url): return _yt_service.get_playlist_title(url)


class YoutubePlaylistController(BaseController):
    """유튜브 재생목록 관련 작업을 처리하는 컨트롤러 클래스입니다.

    재생목록 정보 조회, 신규 영상 업데이트 확인, 영상 다운로드/업로드를 담당하는
    각각의 워커들을 관리합니다.

    Attributes:
        fetch_completed (pyqtSignal): 단일 재생목록 영상 목록 조회가 완료되었을 때 발생하는 시그널.
        checker_completed (pyqtSignal): 등록된 여러 재생목록의 신규 영상 확인이 완료되었을 때 발생하는 시그널.
        upload_completed (pyqtSignal): 영상 업로드 작업이 완료되었을 때 발생하는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    fetch_completed = pyqtSignal(list)
    checker_completed = pyqtSignal(list)
    upload_completed = pyqtSignal()

    def __init__(self, task_manager=None):
        # 컨트롤러의 초기화 및 상위 BaseController 설정
        super().__init__(task_manager)

    # ===========================
    # [워커 실행 메서드]
    # ===========================
    def start_fetch_playlist(self, playlist_id: str):
        # 기존 워커를 초기화
        self.cleanup_worker()
        # 대상 플레이리스트 ID로 조회 워커 생성
        self.worker = PlaylistFetchWorker(playlist_id)
        # 조회 완료 시그널 연결
        self.worker.finished_signal.connect(self.fetch_completed.emit)
        # 백그라운드 워커 시작
        self.start_worker(self.worker)

    def start_upload_videos(self, target_videos: list):
        # 업로드 대상 영상들을 받아 유튜브 업로드 워커 생성
        self.worker = YoutubeUploadWorker(target_videos)
        # 업로드 완료 및 진행 상황 시그널 연결 (인자 무시 래핑)
        self.worker.finished_signal.connect(lambda _: self.upload_completed.emit())
        self.worker.progress_signal.connect(self.progress_signal.emit)
        # 백그라운드 워커 시작
        self.start_worker(self.worker)

    def start_update_checker(self, playlists: list):
        # 등록된 플레이리스트 목록에 대해 업데이트 확인 워커 생성
        self.worker = PlaylistUpdateCheckerWorker(playlists)
        # 확인 작업 완료 시그널 연결
        self.worker.finished_signal.connect(self.checker_completed.emit)
        # 백그라운드 워커 시작
        self.start_worker(self.worker)
