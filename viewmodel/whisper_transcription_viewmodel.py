"""Whisper AI를 활용한 음성 파일 전사 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab6WhisperTranscription)와 연동되어 음성 파일 탐색과
원격(Mac mini) 환경에서의 Whisper 스크립트 추출 작업을 제어합니다.
"""
# controller/whisper_transcription_controller.py
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from worker.transcript.whisper_worker import (WhisperExecutionWorker,
                                              WhisperScannerWorker)


class WhisperTranscriptionViewModel(BaseViewModel):
    """Whisper 전사 작업의 스캔 및 실행을 제어하는 클래스입니다.

    BaseController를 상속받으며 외부 자원을 사용하는 전사 워커들을 큐에 등록하여
    순차적으로 실행되도록 처리합니다.

    Attributes:
        scan_completed (pyqtSignal): 대상 파일 스캔 완료 시 리스트를 반환하는 시그널.
        execution_completed (pyqtSignal): 개별 Whisper 처리 작업이 완료되었음을 알리는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    scan_completed = pyqtSignal()
    execution_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.incomplete_files: list[str] = []

    # ===========================
    # [워커 관리]
    # ===========================
    def scan_drive(self):
        """드라이브 스캔 실행"""
        worker = WhisperScannerWorker()
        worker.finished_signal.connect(self._on_scan_completed)
        self.start_worker(worker)

    def _on_scan_completed(self, files: list):
        self.incomplete_files = files or []
        self.scan_completed.emit()

    def execute_whisper(self, selected_files):
        """선택된 파일들에 대해 Whisper 실행 (Mac mini 원격 자원 사용)"""
        if not selected_files:
            return

        worker_list = []
        for file in selected_files:
            # 개별 파일에 대해 실행할 Whisper 워커 객체 생성
            worker = WhisperExecutionWorker(file_paths=[file])
            worker.finished_signal.connect(lambda _: self.execution_completed.emit())
            worker_list.append(worker)

        # 🚀 중앙 매니저의 "whisper" 전용 차선으로 대기열 토스!
        self.start_batch_workers(worker_list, channel="whisper")