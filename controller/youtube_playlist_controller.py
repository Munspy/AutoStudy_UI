from base.base_controller import BaseController
from worker.youtube_worker import PlaylistFetchWorker, YoutubeUploadWorker, PlaylistUpdateCheckerWorker
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
    """UI와 Worker 스레드를 연결하는 얇은 컨트롤러입니다."""
    
    fetch_completed = pyqtSignal(list)
    checker_completed = pyqtSignal(list)
    upload_completed = pyqtSignal()

    def __init__(self, task_manager=None):
        super().__init__(task_manager)

    def start_fetch_playlist(self, playlist_id: str):
        self.cleanup_worker()
        self.worker = PlaylistFetchWorker(playlist_id)
        self.worker.finished_signal.connect(self.fetch_completed.emit)
        self.start_worker(self.worker)

    def start_upload_videos(self, target_videos: list):
        self.worker = YoutubeUploadWorker(target_videos)
        self.worker.finished_signal.connect(self.upload_completed.emit)
        self.worker.progress_signal.connect(self.progress_signal.emit)
        self.start_worker(self.worker)

    def start_update_checker(self, playlists: list):
        self.worker = PlaylistUpdateCheckerWorker(playlists)
        self.worker.finished_signal.connect(self.checker_completed.emit)
        self.start_worker(self.worker)
