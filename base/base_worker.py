# base/base_worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class BaseWorker(QThread):
    finished_signal = pyqtSignal(object)   # 성공 시 결과 전달
    error_signal = pyqtSignal(str)         # 에러 발생 시 메시지 전달
    progress_signal = pyqtSignal(int, str) # (진행률 %, 진행 메시지)
    log_signal = pyqtSignal(str)           # 실시간 로그 텍스트

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = True

    def run(self):
        self._is_running = True
        try:
            result = self.do_work()
            if self._is_running:
                self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def do_work(self):
        raise NotImplementedError("Subclasses must implement do_work()")

    def stop(self):
        self._is_running = False

    def is_cancelled(self) -> bool:
        return not self._is_running