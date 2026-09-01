# func/func1_drive_sync.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.drive.drive_worker import DriveSyncWorker

class DriveSyncController(BaseController):
    """
    [Tab 1] 백엔드 컨트롤러
    """
    sync_completed = pyqtSignal(list)
    sync_finished = pyqtSignal()

    def __init__(self, task_manager=None):
        super().__init__(task_manager)

    def execute_sync(self, search_mode, filter_value, local_path):
        self.worker = DriveSyncWorker(search_mode, filter_value, local_path)
        
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.sync_finished.emit)
        self.worker.finished_signal.connect(self.sync_completed.emit)
        
        self.start_worker(self.worker)
        

    # ===========================
    # 버튼 동작부. 체크된 내용에 대해 작업 실행
    # 결국 main.py에 선언된 task_manager한테
    # 사용할 worker + 체크된 리스트 제공하는 식으로 구현 될 것.
    # ===========================
    def execute_local_tasks(self, task_manager):
        self.log_signal.emit("작업 실행: 누락 로컬 작업을 모두 실행합니다.")

    def execute_whisper_transcription(self, task_manager):
        self.log_signal.emit("작업 실행: Whisper AI 기반 음성 스크립트 전사를 시작합니다.")

    def download_script_merged(self, task_manager):
        self.log_signal.emit("다운로드: 스크립트 합본 다운로드를 요청했습니다.")

    def download_summary(self, task_manager):
        self.log_signal.emit("다운로드: 요약본 전체 다운로드를 요청했습니다.")

    def download_anki(self, task_manager):
        self.log_signal.emit("다운로드: Anki 덱 전체 다운로드를 요청했습니다.")