from typing import Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal, pyqtProperty
from core.container import AppContainer

class BaseViewModel(QObject):
    """
    모든 ViewModel의 부모 클래스.
    UI(View)와 비즈니스 로직(Service/Worker) 사이에서 상태 관리와 비동기 작업을 중재합니다.
    """
    # ===========================
    # [공통 상태 시그널]
    # ===========================
    is_loading_changed = pyqtSignal(bool)
    status_message_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str) # title, message
    progress_changed = pyqtSignal(int, str) # percent, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading: bool = False
        self._status_message: str = ""
        self.worker = None

        # 작업 관리자(Task Manager) 연동
        self.task_manager = self.app.task_manager
        self.task_manager.queue_progress_signal.connect(self._on_queue_progress)
        self.task_manager.queue_finished_signal.connect(self._on_queue_finished)

    @property
    def app(self):
        """뷰모델에서 DI 컨테이너(AppContainer)의 서비스들에 접근하기 위한 글로벌 단축키입니다."""
        from core.container import AppContainer
        return AppContainer.get_instance()

    # ===========================
    # [공통 프로퍼티 (바인딩용)]
    # ===========================
    @pyqtProperty(bool, notify=is_loading_changed)
    def is_loading(self) -> bool:
        return self._is_loading

    @is_loading.setter
    def is_loading(self, value: bool):
        if self._is_loading != value:
            self._is_loading = value
            self.is_loading_changed.emit(value)

    @pyqtProperty(str, notify=status_message_changed)
    def status_message(self) -> str:
        return self._status_message

    @status_message.setter
    def status_message(self, value: str):
        if self._status_message != value:
            self._status_message = value
            self.status_message_changed.emit(value)

    def emit_error(self, title: str, message: str):
        self.error_occurred.emit(title, message)
        self.is_loading = False

    # ===========================
    # [비동기 워커 실행 로직]
    # ===========================
    def start_worker(self, worker_instance):
        """단일 백그라운드 작업을 실행하고 상태를 관리합니다."""
        self.cleanup_worker()
        self.worker = worker_instance
        
        # 워커 시그널 바인딩
        self.worker.progress_signal.connect(self.progress_changed.emit)
        self.worker.error_signal.connect(lambda msg: self.emit_error("작업 오류", msg))
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)

        self.is_loading = True
        self.worker.start()

    def _on_worker_finished(self, result: Any = None):
        self.is_loading = False

    def start_batch_workers(self, worker_list: list, channel: str = "general"):
        if not worker_list:
            return
        
        self.is_loading = True
        for w in worker_list:
            w.error_signal.connect(lambda msg: self.emit_error("배치 작업 오류", msg))
            self.task_manager.add_task(w, channel=channel)

    def _on_queue_progress(self, completed: int, total: int):
        if total > 0 and self.is_loading:
            percent = int((completed / total) * 100)
            self.progress_changed.emit(percent, f"대기열 처리 중 ({completed}/{total})")

    def _on_queue_finished(self):
        self.is_loading = False

    def cleanup_worker(self):
        try:
            if self.worker and self.worker.isRunning():
                self.worker.stop()
                if not self.worker.wait(2000):
                    self.worker.terminate()
                    self.worker.wait()
                    self.worker.deleteLater() # 강제 종료 시 직접 메모리 해제 지시!
        except RuntimeError:
            pass
        finally:
            self.worker = None

