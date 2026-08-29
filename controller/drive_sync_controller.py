# func/func1_drive_sync.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.drive_worker import DriveSyncThread

class DriveSyncController(BaseController):
    """
    [Tab 1] 백엔드 컨트롤러
    """
    sync_completed = pyqtSignal(list)
    sync_finished = pyqtSignal()

    def __init__(self):
        super().__init__()

    def execute_sync(self, search_mode, filter_value, local_path):
        self.worker = DriveSyncThread(search_mode, filter_value, local_path)
        
        # BaseThread의 정석 시그널에 직접 연결합니다.
        self.worker.success_signal.connect(self.sync_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        
        # 기본 공통 시그널 연결 (BaseController에 구현해둔 헬퍼 사용)
        self.worker.log_signal.connect(self.emit_log)
        
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.sync_finished.emit)
        
        self.worker.start()

    def execute_local_tasks(self):
        self.emit_log("작업 실행: 누락 로컬 작업을 모두 실행합니다.")

    def execute_whisper_transcription(self):
        self.emit_log("작업 실행: Whisper AI 기반 음성 스크립트 전사를 시작합니다.")

    def download_script_merged(self):
        self.log_signal.emit("다운로드: 스크립트 합본 다운로드를 요청했습니다.")

    def download_summary(self):
        self.log_signal.emit("다운로드: 요약본 전체 다운로드를 요청했습니다.")

    def download_anki(self):
        self.log_signal.emit("다운로드: Anki 덱 전체 다운로드를 요청했습니다.")