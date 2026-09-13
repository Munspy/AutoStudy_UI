"""스크립트(텍스트) 파일의 조회, 병합, 분할 작업을 관리하는 ViewModel 모듈입니다.

UI(TranscriptMergeSplitUi)와 연동하여 로컬 및 구글 드라이브 상의
텍스트 파일 검색, 내용 읽기, 내용 분할 및 병합 저장 워커들을 제어하고 상태를 소유합니다.
"""
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from utils.file_util import list_local_files
from worker.transcript.transcript_worker import (TranscriptDriveSearchWorker,
                                                 TranscriptMergeSaveWorker,
                                                 TranscriptReadWorker,
                                                 TranscriptSplitSaveWorker)


class TranscriptMergeSplitViewModel(BaseViewModel):
    """스크립트 병합 및 분할 작업을 제어하고 상태를 관리하는 ViewModel 클래스."""

    # ===========================
    # [시그널 정의]
    # ===========================
    search_completed = pyqtSignal()
    files_read_completed = pyqtSignal()
    split_save_completed = pyqtSignal(str)
    merge_save_completed = pyqtSignal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: list[str] = []
        self.drive_files_cache: dict = {}
        self.loaded_filenames: list[str] = []
        self.loaded_contents: list[str] = []
        self.recommended_split_names: tuple[str, str] = ("", "")
        self.recommended_merged_name: str = ""

    # ===========================
    # [파일 검색 및 읽기]
    # ===========================
    def get_local_text_files(self, directory: str) -> list[str]:
        self.files = list_local_files(directory, extension=".txt")
        return self.files

    def execute_drive_search(self, start_date: str, end_date: str):
        worker = TranscriptDriveSearchWorker(start_date, end_date)
        worker.finished_signal.connect(self._on_search_completed)
        self.start_worker(worker)

    def _on_search_completed(self, result):
        if result:
            files, cache = result
            self.drive_files_cache = cache or {}
            self.files = files or []
        else:
            self.files = []
        self.search_completed.emit()

    def execute_read_files(self, filenames: list[str], folder_path: str, is_drive: bool):
        cache = self.drive_files_cache if is_drive else None
        worker = TranscriptReadWorker(filenames, folder_path, is_drive, drive_cache=cache)
        worker.finished_signal.connect(self._on_files_read)
        self.start_worker(worker)

    def _on_files_read(self, res: dict):
        if not res:
            self.loaded_filenames = []
            self.loaded_contents = []
            return

        self.loaded_filenames = res.get("filenames", [])
        self.loaded_contents = res.get("contents", [])

        if len(self.loaded_filenames) == 1:
            fname = self.loaded_filenames[0]
            splits = self.app.file_naming.generate_split_filenames(fname)
            self.recommended_split_names = (splits[0], splits[1]) if len(splits) >= 2 else ("", "")
        elif len(self.loaded_filenames) > 1:
            self.recommended_merged_name = self.app.file_naming.generate_merged_filename(self.loaded_filenames)

        self.files_read_completed.emit()

    # ===========================
    # [파일 분할 및 병합 저장]
    # ===========================
    def execute_split_save(self, folder_path: str, filename: str, text_content: str, name1: str, name2: str, is_drive: bool):
        worker = TranscriptSplitSaveWorker(folder_path, filename, text_content, name1, name2, is_drive)
        worker.finished_signal.connect(self.split_save_completed.emit)
        self.start_worker(worker)

    def execute_merge_save(self, folder_path: str, files_to_merge: list[str], merged_content: str, custom_name: str, is_drive: bool):
        worker = TranscriptMergeSaveWorker(folder_path, files_to_merge, merged_content, custom_name, is_drive)
        worker.finished_signal.connect(self.merge_save_completed.emit)
        self.start_worker(worker)
