# Threads/watchdog_thread.py
import os
import time
from PyQt6.QtCore import QThread, pyqtSignal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class StudyFileEventHandler(FileSystemEventHandler):
    """실제 파일 시스템 이벤트를 감지하는 핸들러"""
    def __init__(self, signal_emitter):
        super().__init__()
        self.signal_emitter = signal_emitter

    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = event.src_path
        file_name = os.path.basename(file_path)
        
        # 임시 파일 무시
        if "_temp" in file_name or file_name.startswith("~$") or file_name.startswith("."):
            return

        # 대용량 파일이 완전히 복사될 때까지 약간 대기
        time.sleep(2)
        
        extension = os.path.splitext(file_name)[1].lower()
        
        # 감지된 파일 종류에 따라 스레드 바깥(메인 UI/컨트롤러)으로 시그널 전송
        if extension in ['.mp4', '.m4a', '.mp3', '.wav']:
            self.signal_emitter.emit("AUDIO", file_path)
        elif extension == '.pdf':
            self.signal_emitter.emit("PDF", file_path)


class WatchdogThread(QThread):
    """
    백그라운드에서 특정 폴더를 무한히 감시하는 스레드입니다.
    """
    # 감지된 파일 타입("AUDIO" 또는 "PDF")과 파일 경로를 전달하는 시그널
    file_detected_signal = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, watch_path: str, parent=None):
        super().__init__(parent)
        self.watch_path = watch_path
        self.observer = Observer()
        self._is_running = False

    def run(self):
        try:
            if not os.path.exists(self.watch_path):
                os.makedirs(self.watch_path, exist_ok=True)

            event_handler = StudyFileEventHandler(self.file_detected_signal)
            self.observer.schedule(event_handler, self.watch_path, recursive=False)
            
            self._is_running = True
            self.observer.start()
            
            # 스레드가 살아있도록 유지
            while self._is_running:
                time.sleep(1)
                
        except Exception as e:
            self.error_signal.emit(f"폴더 감시 중 오류 발생: {str(e)}")

    def stop(self):
        """스레드를 안전하게 종료합니다."""
        self._is_running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()