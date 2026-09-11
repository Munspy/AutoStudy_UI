"""구글 드라이브 동기화 작업을 관리하는 컨트롤러 모듈입니다.

이 모듈은 UI(Tab1DriveSync)와 연결되어 사용자의 입력에 따라 
구글 드라이브와 로컬 파일 시스템 간의 동기화 워커를 실행하고 그 결과를 처리합니다.
"""
# func/func1_drive_sync.py
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_controller import BaseController
# Moved from inline
from worker.drive import (AnkiDeckMergeWorker, DriveSyncWorker,
                          ExamCategoryFetchWorker, ScriptedPdfMergeWorker,
                          SummaryPdfDownloadWorker)


class DriveSyncController(BaseController):
    """구글 드라이브 동기화 관련 백엔드 제어를 담당하는 컨트롤러 클래스입니다.

    BaseController를 상속하며, DriveSyncWorker 및 ExamCategoryFetchWorker를 인스턴스화하여 백그라운드 작업을 실행합니다.
    작업 진행 상태 및 완료 결과를 시그널을 통해 UI로 전달합니다.

    Attributes:
        sync_completed (pyqtSignal): 동기화 성공 결과를 리스트로 반환하는 시그널.
        sync_finished (pyqtSignal): 워커의 작업이 완전히 종료되었음을 알리는 시그널.
        categories_loaded (pyqtSignal): 구글 드라이브에서 조회된 시험 기준 목록을 반환하는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    sync_completed = pyqtSignal(list)
    sync_finished = pyqtSignal()
    categories_loaded = pyqtSignal(list)

    def __init__(self):
        # BaseController의 초기화 메서드를 통해 기본 설정 적용
        super().__init__()

    # ===========================
    # [시험 기준 폴더 목록 조회]
    # ===========================
    def start_fetch_categories(self, force_refresh: bool = False):
        """구글 드라이브의 폴더 구조를 조회하여 시험 기준 목록을 가져옵니다."""
        worker = ExamCategoryFetchWorker(force_refresh=force_refresh)
        worker.finished_signal.connect(self.categories_loaded.emit)
        self.start_worker(worker)

    # ===========================
    # [동기화 작업 실행]
    # ===========================
    def execute_sync(self, search_mode, filter_value, local_path):
        """지정된 조건에 맞춰 구글 드라이브 동기화 워커를 실행합니다."""
        worker = DriveSyncWorker(search_mode, filter_value, local_path)
        
        # 워커 작업 종료 시 sync_finished 시그널 방출
        worker.finished.connect(self.sync_finished.emit)
        # 워커 결과를 sync_completed 시그널로 방출
        worker.finished_signal.connect(self.sync_completed.emit)
        
        # 워커를 백그라운드 스레드에서 실행 (BaseController가 메모리 해제 등 공통 처리 수행)
        self.start_worker(worker)

    # ===========================
    # [작업 실행 및 다운로드 요청 (추후 연동될 Placeholder)]
    # ===========================
    def execute_local_tasks(self):
        # 로컬 작업 실행 요청을 로그로 출력
        GlobalLogger.info("작업 실행: 누락 로컬 작업을 모두 실행합니다.")

    def execute_whisper_transcription(self):
        # Whisper 음성 전사 작업 실행 요청을 로그로 출력
        GlobalLogger.info("작업 실행: Whisper AI 기반 음성 스크립트 전사를 시작합니다.")

    def start_download_script_merged(self, checked_lessons: list, output_path: str):
        """체크된 수업들에 대해 구글 드라이브에서 _scripted.pdf를 다운로드하고, 목차가 포함된 합본 PDF를 생성하는 워커를 실행합니다."""
        if not checked_lessons:
            self.error_signal.emit("오류", "선택된(체크된) 수업이 없습니다.")
            return

        worker = ScriptedPdfMergeWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)

    def download_summary(self, checked_lessons: list[str], output_path: str):
        GlobalLogger.info(f"🚀 요약본 합본 다운로드 작업을 시작합니다... (선택된 수업: {len(checked_lessons)}개)")
        worker = SummaryPdfDownloadWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)

    def download_anki(self, checked_lessons: list[str], output_path: str):
        GlobalLogger.info(f"🚀 Anki 덱 합본 다운로드 작업을 시작합니다... (선택된 수업: {len(checked_lessons)}개)")
        worker = AnkiDeckMergeWorker(checked_lessons=checked_lessons, output_path=output_path)
        worker.finished_signal.connect(lambda msg: GlobalLogger.info(f"✅ {msg}"))
        self.start_worker(worker)