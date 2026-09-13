"""유튜브 재생목록 동기화 및 다운로드/업로드 작업을 관리하는 ViewModel 모듈입니다.

UI(YoutubePlaylistUi) 및 Service 레이어와 연동하여 재생목록의 업데이트 상태를 확인하고,
필요한 영상을 다운로드 또는 구글 드라이브에 업로드하는 워커들을 제어하며 상태를 관리합니다.
"""
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from service.playlist_repository import PlaylistRepository
from worker.youtube.youtube_worker import (PlaylistFetchWorker,
                                           PlaylistUpdateCheckerWorker,
                                           YoutubeUploadWorker)


class YoutubePlaylistViewModel(BaseViewModel):
    """유튜브 재생목록 데이터와 워커 작업을 관리하는 ViewModel 클래스."""

    # ===========================
    # [시그널 정의]
    # ===========================
    fetch_completed = pyqtSignal()
    checker_completed = pyqtSignal()
    upload_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo = PlaylistRepository()
        self.playlists: list[dict] = []
        self.current_videos: list[dict] = []
        self.checker_results: list[dict] = []

    # ===========================
    # [데이터 저장소(Repository) 캡슐화]
    # ===========================
    def load_playlists(self) -> list[dict]:
        self.playlists = self.repo.load_playlists() or []
        return self.playlists

    def add_playlist(self, name: str, url: str, pid: str):
        self.repo.add_playlist(name, url, pid)
        self.load_playlists()

    def delete_playlist(self, pid: str):
        self.repo.delete_playlist(pid)
        self.load_playlists()

    def rename_playlist(self, pid: str, name: str):
        self.repo.rename_playlist(pid, name)
        self.load_playlists()

    def parse_playlist_id(self, url: str) -> str:
        return self.app.yt_playlist.parse_playlist_id(url)

    def get_playlist_title(self, url: str) -> str:
        return self.app.yt_playlist.get_playlist_title(url)

    # ===========================
    # [워커 실행 메서드]
    # ===========================
    def start_fetch_playlist(self, playlist_id: str):
        worker = PlaylistFetchWorker(playlist_id)
        worker.finished_signal.connect(self._on_fetch_completed)
        self.start_worker(worker)

    def _on_fetch_completed(self, videos: list):
        self.current_videos = videos or []
        self.fetch_completed.emit()

    def start_update_checker(self):
        playlists = self.load_playlists()
        if not playlists:
            self.checker_results = []
            self.checker_completed.emit()
            return

        worker = PlaylistUpdateCheckerWorker(playlists)
        worker.finished_signal.connect(self._on_checker_completed)
        self.start_worker(worker)

    def _on_checker_completed(self, results: list):
        self.checker_results = results or []
        self.checker_completed.emit()

    def start_upload_videos(self, target_videos: list):
        if not target_videos:
            self.emit_error("오류", "업로드할 영상이 선택되지 않았습니다.")
            return

        worker = YoutubeUploadWorker(target_videos)
        worker.finished_signal.connect(lambda _: self.upload_completed.emit())
        self.start_worker(worker)
