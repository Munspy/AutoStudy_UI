from typing import List
from PyQt6.QtCore import pyqtSignal

from base.base_viewmodel import BaseViewModel
from core.logger import GlobalLogger
from worker.drive import (AnkiDeckMergeWorker, DriveSyncWorker,
                          ExamCategoryFetchWorker, ScriptedPdfMergeWorker,
                          SummaryPdfDownloadWorker)

class DriveSyncViewModel(BaseViewModel):
    sync_data_changed = pyqtSignal()
    categories_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sync_data = []
        self.categories = []
        
        self.search_mode = "DATE"
        self.filter_value = None
        self.local_path = ""

    # ===========================
    # [상태 프로퍼티]
    # ===========================
    @property
    def search_mode(self) -> str:
        return self._search_mode
        
    @search_mode.setter
    def search_mode(self, value: str):
        self._search_mode = value
        
    @property
    def filter_value(self) -> str:
        return self._filter_value
        
    @filter_value.setter
    def filter_value(self, value: str):
        self._filter_value = value

    @property
    def local_path(self) -> str:
        return self._local_path
        
    @local_path.setter
    def local_path(self, value: str):
        self._local_path = value

    # ===========================
    # [명령 (Commands)]
    # ===========================
    def fetch_categories(self, force_refresh: bool = False):
        """구글 드라이브의 폴더 구조를 조회하여 시험 기준 목록을 가져옵니다."""
        worker = ExamCategoryFetchWorker(force_refresh=force_refresh)
        worker.finished_signal.connect(self._on_categories_loaded)
        self.start_worker(worker)

    def execute_sync(self):
        """지정된 조건(현재 상태)에 맞춰 동기화 워커를 실행합니다."""
        worker = DriveSyncWorker(self.search_mode, self.filter_value, self.local_path)
        worker.finished_signal.connect(self._on_sync_completed)
        self.start_worker(worker)

    def execute_local_tasks(self):
        GlobalLogger.info("작업 실행: 누락 로컬 작업을 모두 실행합니다.")

    def execute_whisper_transcription(self):
        GlobalLogger.info("작업 실행: Whisper AI 기반 음성 스크립트 전사를 시작합니다.")

    def download_script_merged(self, checked_lessons: List[str], output_path: str):
        if not checked_lessons:
            self.emit_error("오류", "선택된(체크된) 수업이 없습니다.")
            return

        worker = ScriptedPdfMergeWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)

    def download_summary(self, checked_lessons: List[str], output_path: str):
        GlobalLogger.info(f"🚀 요약본 합본 다운로드 작업을 시작합니다... (선택된 수업: {len(checked_lessons)}개)")
        worker = SummaryPdfDownloadWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)

    def download_anki(self, checked_lessons: List[str], output_path: str):
        GlobalLogger.info(f"🚀 Anki 덱 합본 다운로드 작업을 시작합니다... (선택된 수업: {len(checked_lessons)}개)")
        worker = AnkiDeckMergeWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)

    def _on_sync_completed(self, result: list):
        """워커가 동기화 데이터를 가져오면, 자기 변수에 저장하고 UI에 알람만 쏩니다."""
        self.sync_data = result
        self.sync_data_changed.emit() # "UI야, 나 데이터 바꼈어!"

    def _on_categories_loaded(self, result: list):
        """워커가 시험 범위를 가져오면, 자기 변수에 저장하고 알람을 쏩니다."""
        self.categories = result
        self.categories_changed.emit() # "UI야, 나 데이터 바꼈어!"
