# controller/youtube_playlist_controller.py
from PyQt6.QtCore import pyqtSignal

from base.base_controller import BaseController
from worker.youtube_worker import PlaylistFetchWorker, YoutubeUploadWorker, PlaylistUpdateCheckerWorker
from service.youtube_playlist_service import YoutubePlaylistService
from service.playlist_repository import PlaylistRepository

class YoutubePlaylistController(BaseController):
    """UI와 Worker 스레드 및 로컬 리포지토리를 연결하는 컨트롤러 클래스."""
    
    fetch_completed = pyqtSignal(list)
    checker_completed = pyqtSignal(list)
    upload_completed = pyqtSignal()
    progress_val_signal = pyqtSignal(int)

    def __init__(self, ui_view=None):
        super().__init__(ui_view=ui_view)
        self.repository = PlaylistRepository(logger_callback=self.emit_log)
        self.yt_service = YoutubePlaylistService(logger_callback=self.emit_log)

    def init_csv(self):
        self.repository._init_csv()

    def load_csv_data(self):
        return self.repository.load_playlists()

    def parse_playlist_id(self, url):
        return self.yt_service.parse_playlist_id(url)

    def add_playlist_to_csv(self, name, url, pid):
        self.repository.add_playlist(name, url, pid)

    def delete_playlist(self, pid):
        self.repository.delete_playlist(pid)

    def rename_playlist(self, pid, name):
        self.repository.rename_playlist(pid, name)

    def get_playlist_title(self, url):
        return self.yt_service.get_playlist_title(url)

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