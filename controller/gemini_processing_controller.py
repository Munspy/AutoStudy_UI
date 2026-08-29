from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.gemini_worker import GeminiScanWorker, GeminiTaskWorker

class GeminiProcessingController(BaseController):
    """
    Gemini 태스크 처리를 조율하는 컨트롤러 클래스.
    UI의 요청에 따라 스캔 및 LLM 연산 작업을 백그라운드 스레드에서 비동기로 실행합니다.
    """
    scan_completed = pyqtSignal(list, bool)
    cell_updated = pyqtSignal(int, int, str)

    def __init__(self, view=None):
        super().__init__(ui_view=view)

    def start_scan(self, is_force_rerun: bool, target_mmdd: str = None):
        """드라이브 스캔 작업을 백그라운드 스레드로 실행합니다."""
        self.cleanup_worker()
        self.worker = GeminiScanWorker(is_force_rerun, target_mmdd)
        
        # 시그널 바인딩
        self.worker.success_signal.connect(lambda data: self.scan_completed.emit(data, is_force_rerun))
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()

    def start_tasks(self, task_queue: list):
        """선택된 LLM 작업 대기열을 순차적으로 백그라운드 스레드로 실행합니다."""
        self.cleanup_worker()
        self.worker = GeminiTaskWorker(task_queue)
        
        # 시그널 바인딩
        self.worker.cell_update_signal.connect(self.cell_updated.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()