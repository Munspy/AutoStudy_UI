from base.base_controller import BaseController
from worker.youtube_worker import PlaylistFetchWorker, YoutubeUploadWorker, PlaylistUpdateCheckerWorker
from service.youtube_playlist_service import YoutubePlaylistService
from PyQt6.QtCore import pyqtSignal

# (CSV 래퍼 함수들은 기존처럼 외부 함수로 두거나 Controller 내부 메서드로 편하게 쓰셔도 무방합니다)
_yt_service = YoutubePlaylistService()

def load_csv_data(): return _yt_service.load_playlists()
def parse_playlist_id(url): return _yt_service.parse_playlist_id(url)
def add_playlist_to_csv(name, url, pid): _yt_service.add_playlist(name, url, pid)
def delete_playlist(pid): _yt_service.delete_playlist(pid)
def rename_playlist(pid, name): _yt_service.rename_playlist(pid, name)
def get_playlist_title(url): return _yt_service.get_playlist_title(url)


class YoutubePlaylistController(BaseController):
    """UI와 Worker 스레드를 연결하는 얇은 컨트롤러입니다."""
    
    fetch_completed = pyqtSignal(list)
    checker_completed = pyqtSignal(list)
    upload_completed = pyqtSignal()
    progress_val_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()

    def start_fetch_playlist(self, playlist_id: str):
        self.cleanup_worker()
        self.worker = PlaylistFetchWorker(playlist_id)
        
        self.worker.success_signal.connect(self.fetch_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def start_upload_videos(self, target_videos: list):
        self.cleanup_worker()
        self.worker = YoutubeUploadWorker(target_videos)
        
        self.worker.success_signal.connect(lambda _: self.upload_completed.emit())
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.progress_signal.connect(self.progress_val_signal.emit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def start_update_checker(self, playlists: list):
        self.cleanup_worker()
        self.worker = PlaylistUpdateCheckerWorker(playlists)
        
        self.worker.success_signal.connect(self.checker_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()