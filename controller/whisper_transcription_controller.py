# controller/whisper_transcription_controller.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.whisper_worker import WhisperScannerWorker, WhisperExecutionWorker

class WhisperTranscriptionController(BaseController):
    """Tab6의 UI와 Worker를 연결하는 메인 컨트롤러"""
    
    # 📡 [신규] UI 중계용 전용 안테나 (handle_result 대체)
    scan_completed = pyqtSignal(list)
    execution_completed = pyqtSignal()  # 결과 데이터가 필요하다면 pyqtSignal(타입)으로 수정 가능

    def __init__(self, task_manager=None):
        super().__init__(task_manager)

    def scan_drive(self):
        """드라이브 스캔 실행 (상대적으로 가볍고 즉각적인 UI 갱신이 필요하므로 단일 작업 유지)"""
        # 위스퍼 스캔이 왜 따로 있는 거...? 그럴 필요가 있나?
        worker = WhisperScannerWorker()
        worker.finished_signal.connect(self.scan_completed.emit)
        self.start_worker(worker)

    def execute_whisper(self, selected_files):
        """선택된 파일들에 대해 Whisper 실행 (Mac mini 원격 자원 사용)"""
        if not selected_files:
            return

        worker_list = []
        for file in selected_files:
            # Mac mini 같은 외부 자원으로 무거운 통신을 할 때 큐 관리가 필수적입니다.
            worker = WhisperExecutionWorker([file], mac_mini_ip="192.168.0.15") 
            worker.finished_signal.connect(self.execution_completed.emit)
            worker_list.append(worker)

        # 🚀 중앙 매니저의 "whisper" 전용 차선으로 대기열 토스!
        self.start_batch_workers(worker_list, channel="whisper")