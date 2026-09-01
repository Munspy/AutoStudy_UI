# worker/whisper_worker.py
import time
from base.base_worker import BaseWorker
from service.whisper_service import WhisperService

class WhisperScannerWorker(BaseWorker):
    """드라이브를 스캔하여 전사가 필요한 오디오 파일만 필터링하는 워커"""
    
    def __init__(self):
        super().__init__()

    def do_work(self):
        """드라이브 스캔 및 보류 중인 오디오 파일 탐색 작업을 실행합니다."""
        self.log_signal.emit("🔄 구글 드라이브 스캔을 시작합니다...")
        
        # ===========================
        # [서비스 초기화 및 파일 필터링]
        # ===========================
        # 서비스 객체 호출 (로깅 콜백 전달)
        whisper_service = WhisperService(logger_callback=self.log_signal.emit)
        incomplete_audio_files = whisper_service.get_pending_audio_files()
        
        # 취소 여부 확인
        if self.is_cancelled():
            return []
            
        return incomplete_audio_files


class WhisperExecutionWorker(BaseWorker):
    """
    Mac mini(로컬 IP)에 접속하여 Whisper 전사를 요청하고 결과를 기다리는 스레드.
    """
    def __init__(self, file_paths: list, mac_mini_ip: str = "192.168.1.100"):
        """WhisperExecutionWorker 초기화."""
        super().__init__()
        self.file_paths = file_paths
        self.mac_mini_ip = mac_mini_ip

    def do_work(self):
        """Mac mini를 통해 Whisper 전사 작업을 백그라운드에서 실행합니다."""
        # ===========================
        # [초기 설정 및 연결 시도]
        # ===========================
        total_files = len(self.file_paths)
        completed_files = []
        
        if total_files == 0:
            return completed_files

        self.log_signal.emit(f"🖥️ Mac mini({self.mac_mini_ip}) 연결을 시도합니다...")
        time.sleep(1) # 연결 지연 시뮬레이션
        
        # ===========================
        # [전사 작업 루프]
        # ===========================
        for i, filepath in enumerate(self.file_paths):
            if self.is_cancelled():
                self.log_signal.emit("⚠️ 작업이 사용자에 의해 취소되었습니다.")
                break
                
            self.log_signal.emit(f"📥 [{i+1}/{total_files}] 파일 전송 및 전사 요청: {filepath}")
            
            # 통신 및 전사 진행률 시뮬레이션
            for step in range(1, 11):
                if self.is_cancelled(): 
                    break
                time.sleep(0.5) # 실제 서버 통신 대기 로직으로 교체될 부분
                
                # 전체 진행도를 계산합니다.
                current_progress = int(((i * 10) + step) / (total_files * 10) * 100)
                # BaseWorker 규격에 맞춰 (int, str) 두 개의 인자를 전송
                self.progress_signal.emit(current_progress, f"{filepath} 전사 중...")
                
            # 취소되지 않았다면 완료 처리
            if not self.is_cancelled():
                completed_files.append(filepath)
                self.log_signal.emit(f"✅ [{i+1}/{total_files}] 전사 완료: {filepath}")
            
        # ===========================
        # [최종 마무리]
        # ===========================
        if not self.is_cancelled():
            self.log_signal.emit("🎉 모든 Whisper 전사 작업이 완료되었습니다.")
            
        return completed_files