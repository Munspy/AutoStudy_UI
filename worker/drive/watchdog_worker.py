"""
파일 시스템 변경 감지 관련 워커 모듈입니다.

이 모듈은 특정 폴더 내의 파일 생성 이벤트를 감지하여
UI나 컨트롤러로 시그널을 전달하는 감시 스레드를 포함합니다.
"""
# Threads/watchdog_thread.py
import os
import time
from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class StudyFileEventHandler(FileSystemEventHandler):
    """실제 파일 시스템 이벤트를 감지하는 핸들러.
    
    Attributes:
        signal_emitter: 이벤트를 전달할 시그널 발행자(emitter).
    """
    def __init__(self, signal_emitter):
        """StudyFileEventHandler 초기화.
        
        Args:
            signal_emitter (pyqtSignal): UI 또는 컨트롤러로 이벤트를 쏠 시그널 객체.
        """
        super().__init__()
        self.signal_emitter = signal_emitter

    def on_created(self, event):
        """새로운 파일이 생성되었을 때 호출되는 콜백.
        
        오디오나 PDF 파일인 경우 시그널을 통해 이를 메인 스레드로 알립니다.
        
        Args:
            event (FileSystemEvent): 파일 시스템 이벤트 객체.
        """
        # ===========================
        # [파일 생성 이벤트 처리]
        # ===========================
        # 디렉토리인 경우 처리하지 않고 반환합니다.
        if event.is_directory:
            return
            
        file_path = event.src_path
        file_name = os.path.basename(file_path)
        
        # 임시 파일 무시
        # 임시 파일이거나 숨김 파일인 경우 무시합니다.
        if "_temp" in file_name or file_name.startswith("~$") or file_name.startswith("."):
            return

        # 대용량 파일이 완전히 복사될 때까지 약간 대기
        time.sleep(2)
        
        extension = os.path.splitext(file_name)[1].lower()
        
        # 감지된 파일 종류에 따라 스레드 바깥(메인 UI/컨트롤러)으로 시그널 전송
        # 파일 확장자에 따라 다른 시그널을 전송합니다.
        if extension in ['.mp4', '.m4a', '.mp3', '.wav']:
            self.signal_emitter.emit("AUDIO", file_path)
        elif extension == '.pdf':
            self.signal_emitter.emit("PDF", file_path)


class WatchdogWorker(BaseWorker):
    """
    백그라운드에서 특정 폴더를 무한히 감시하는 스레드입니다.
    
    이 클래스는 watchdog 라이브러리를 사용하여 디렉토리 변화를 
    비동기적으로 감지하고 신호를 발생시킵니다.
    
    Attributes:
        watch_path (str): 감시할 대상 디렉토리 경로.
        observer (Observer): watchdog 파일 시스템 감시자 객체.
    """
    # ===========================
    # [워커 시그널 및 초기화]
    # ===========================
    # 감지된 파일 타입("AUDIO" 또는 "PDF")과 파일 경로를 전달하는 시그널
    file_detected_signal = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, watch_path: str, parent=None):
        """WatchdogWorker 초기화.
        
        Args:
            watch_path (str): 감시할 로컬 폴더 경로.
            parent: 부모 PyQt 객체.
        """
        super().__init__(parent)
        self.watch_path = watch_path
        self.observer = Observer()
        self._is_running = False

    def do_work(self):
        """파일 시스템 감시 루프를 실행합니다.
        
        디렉토리가 없으면 생성하고, Observer를 구동시켜 파일 생성을 모니터링합니다.
        """
        # ===========================
        # [감시 루프 실행]
        # ===========================
        try:
            # 감시할 디렉토리가 없으면 생성합니다.
            if not os.path.exists(self.watch_path):
                os.makedirs(self.watch_path, exist_ok=True)

            # 이벤트 핸들러를 등록하고 감시를 시작합니다.
            event_handler = StudyFileEventHandler(self.file_detected_signal)
            self.observer.schedule(event_handler, self.watch_path, recursive=False)
            
            self._is_running = True
            self.observer.start()
            
            # 스레드가 살아있도록 유지
            # 플래그가 참인 동안 주기적으로 대기합니다.
            while self._is_running:
                time.sleep(1)
                
        except Exception as e:
            # 오류 발생 시 에러 시그널을 방출합니다.
            self.error_signal.emit(f"폴더 감시 중 오류 발생: {str(e)}")

    def stop(self):
        """스레드를 안전하게 종료합니다.
        
        Observer 감시를 멈추고 스레드가 종료될 때까지 대기합니다.
        """
        # ===========================
        # [감시 스레드 종료]
        # ===========================
        # 스레드 실행 플래그를 거짓으로 변경합니다.
        self._is_running = False
        if self.observer.is_alive():
            # 감시자를 중지하고 조인합니다.
            self.observer.stop()
            self.observer.join()