# controller/whisper_transcription_controller.py
from base.base_controller import BaseController
from worker.whisper_worker import WhisperScannerWorker, WhisperExecutionWorker

class WhisperTranscriptionController(BaseController):
    """Tab6의 UI와 Worker를 연결하는 메인 컨트롤러"""
    
    def __init__(self, ui_widget):
        super().__init__(ui_view=ui_widget)
        
    def scan_drive(self):
        """드라이브 스캔 실행"""
        self.cleanup_worker()
        self.worker = WhisperScannerWorker()
        
        # BaseController의 공통 시그널 처리 외에, 고유 로직(결과 리스트업)만 추가 연결
        self.worker.log_signal.connect(self.ui.emit_log)
        self.worker.finished_signal.connect(self.ui.populate_list)
        self.worker.error_signal.connect(lambda e: self.ui.emit_log(f"🔴 {e}"))
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()

    def execute_whisper(self, selected_files):
        """선택된 파일들에 대해 Whisper 실행"""
        self.cleanup_worker()
        # Mac mini IP를 지정하거나 기본값을 사용
        self.worker = WhisperExecutionWorker(selected_files, mac_mini_ip="192.168.0.15")
        
        # 시그널 연결 (progress_signal은 int와 str을 모두 받으므로 람다로 UI에 전달)
        self.worker.log_signal.connect(self.ui.emit_log)
        self.worker.progress_signal.connect(lambda p, msg: self.ui.update_progress(p))
        self.worker.finished_signal.connect(lambda _: self.ui.on_transcription_finished())
        self.worker.error_signal.connect(lambda e: self.ui.emit_log(f"🔴 {e}"))
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()