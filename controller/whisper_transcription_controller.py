# controller/whisper_transcription_controller.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.whisper_worker import WhisperScannerWorker, WhisperExecutionWorker

class WhisperTranscriptionController(BaseController):
    """Tab6의 UI와 Worker를 연결하는 메인 컨트롤러"""
    
    scan_completed = pyqtSignal(list)
    transcription_completed = pyqtSignal()
    progress_val_signal = pyqtSignal(int)
    
    def __init__(self, ui_widget=None):
        super().__init__(ui_view=ui_widget)
        
    def scan_drive(self):
        """드라이브 스캔 실행"""
        self.cleanup_worker()
        self.worker = WhisperScannerWorker()
        
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished_signal.connect(self.scan_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()

    def execute_whisper(self, selected_files):
        """선택된 파일들에 대해 Whisper 실행"""
        self.cleanup_worker()
        self.worker = WhisperExecutionWorker(selected_files, mac_mini_ip="192.168.0.15")
        
        self.worker.log_signal.connect(self.emit_log)
        self.worker.progress_signal.connect(lambda p, _: self.progress_val_signal.emit(p))
        self.worker.finished_signal.connect(lambda _: self.transcription_completed.emit())
        self.worker.error_signal.connect(self.emit_error)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()