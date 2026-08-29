# base/base_controller.py
from PyQt6.QtCore import QObject, pyqtSignal

class BaseController(QObject):
    log_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, ui_view=None):
        super().__init__()
        self.ui = ui_view
        self.worker = None

    def start_worker(self, worker_instance):
        """워커를 안전하게 시작하고 공통 시그널을 바인딩합니다."""
        self.cleanup_worker() 
        self.worker = worker_instance
        
        # 표준 시그널 연결
        if hasattr(self.worker, 'finished_signal'):
            self.worker.finished_signal.connect(self._on_worker_finished)
        if hasattr(self.worker, 'error_signal'):
            self.worker.error_signal.connect(self._on_worker_error)
        if hasattr(self.worker, 'progress_signal'):
            self.worker.progress_signal.connect(self._on_worker_progress)
        if hasattr(self.worker, 'log_signal'):
            self.worker.log_signal.connect(self.emit_log)

        if self.ui and hasattr(self.ui, 'show_loading'):
            self.ui.show_loading()

        self.worker.start()

    def _on_worker_finished(self, result):
        self._hide_loading()
        self.handle_result(result)

    def handle_result(self, result):
        pass

    def _on_worker_error(self, error_msg):
        self._hide_loading()
        self.emit_error(error_msg)

    def _on_worker_progress(self, progress, message):
        if self.ui and hasattr(self.ui, 'update_progress'):
            self.ui.update_progress(progress, message)

    def _hide_loading(self):
        if self.ui and hasattr(self.ui, 'hide_loading'):
            self.ui.hide_loading()

    def emit_log(self, message: str):
        self.log_signal.emit(message)
        if self.ui and hasattr(self.ui, 'append_log'):
            self.ui.append_log(message)

    def emit_error(self, error_msg: str):
        self.error_signal.emit(error_msg)
        if self.ui and hasattr(self.ui, 'show_error'):
            self.ui.show_error(error_msg)
        else:
            print(f"[Error] {error_msg}")

    def cleanup_worker(self):
        if self.worker is not None and self.worker.isRunning():
            if hasattr(self.worker, 'stop'):
                self.worker.stop() 
            if not self.worker.wait(2000): 
                self.worker.terminate() 
                self.worker.wait()
            self.worker = None