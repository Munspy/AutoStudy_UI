"""구글 드라이브 동기화 작업을 관리하는 컨트롤러 모듈입니다.

이 모듈은 UI(Tab1DriveSync)와 연결되어 사용자의 입력에 따라 
구글 드라이브와 로컬 파일 시스템 간의 동기화 워커를 실행하고 그 결과를 처리합니다.
"""
# func/func1_drive_sync.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.drive.drive_worker import DriveSyncWorker

class DriveSyncController(BaseController):
    """구글 드라이브 동기화 관련 백엔드 제어를 담당하는 컨트롤러 클래스입니다.

    BaseController를 상속하며, DriveSyncWorker를 인스턴스화하여 백그라운드 작업을 실행합니다.
    작업 진행 상태 및 완료 결과를 시그널을 통해 UI로 전달합니다.

    Attributes:
        sync_completed (pyqtSignal): 동기화 성공 결과를 리스트로 반환하는 시그널.
        sync_finished (pyqtSignal): 워커의 작업이 완전히 종료되었음을 알리는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    sync_completed = pyqtSignal(list)
    sync_finished = pyqtSignal()

    def __init__(self, task_manager=None):
        # BaseController의 초기화 메서드를 통해 기본 설정 적용
        super().__init__(task_manager)

    # ===========================
    # [동기화 작업 실행]
    # ===========================
    def execute_sync(self, search_mode, filter_value, local_path):
        """지정된 조건에 맞춰 구글 드라이브 동기화 워커를 실행합니다.

        사용자가 UI에서 선택한 검색 모드와 필터값을 기반으로
        원격 드라이브와 로컬 경로 간의 파일 동기화를 시작합니다.

        Args:
            search_mode (str): 검색 모드 (예: 'all', 'folder' 등).
            filter_value (str): 검색 시 사용할 필터값.
            local_path (str): 동기화할 로컬 디렉토리 경로.

        Returns:
            None

        Raises:
            Exception: 동기화 워커 초기화 및 실행 중 오류가 발생할 수 있습니다.
        """
        # 조건에 맞는 동기화 워커 인스턴스 생성
        self.worker = DriveSyncWorker(search_mode, filter_value, local_path)
        
        # 작업이 끝나면 워커 메모리를 해제하도록 연결
        self.worker.finished.connect(self.worker.deleteLater)
        # 워커 작업 종료 시 sync_finished 시그널 방출
        self.worker.finished.connect(self.sync_finished.emit)
        # 워커 결과를 sync_completed 시그널로 방출
        self.worker.finished_signal.connect(self.sync_completed.emit)
        
        # 워커를 백그라운드 스레드에서 실행
        self.start_worker(self.worker)
        

    # ===========================
    # [작업 실행 및 다운로드 요청]
    # 버튼 동작부. 체크된 내용에 대해 작업 실행
    # 결국 main.py에 선언된 task_manager한테
    # 사용할 worker + 체크된 리스트 제공하는 식으로 구현 될 것.
    # ===========================
    def execute_local_tasks(self, task_manager):
        # 로컬 작업 실행 요청을 로그로 출력
        self.log_signal.emit("작업 실행: 누락 로컬 작업을 모두 실행합니다.")

    def execute_whisper_transcription(self, task_manager):
        # Whisper 음성 전사 작업 실행 요청을 로그로 출력
        self.log_signal.emit("작업 실행: Whisper AI 기반 음성 스크립트 전사를 시작합니다.")

    def download_script_merged(self, task_manager):
        # 스크립트 병합본 다운로드 요청을 로그로 출력
        self.log_signal.emit("다운로드: 스크립트 합본 다운로드를 요청했습니다.")

    def download_summary(self, task_manager):
        # 요약본 전체 다운로드 요청을 로그로 출력
        self.log_signal.emit("다운로드: 요약본 전체 다운로드를 요청했습니다.")

    def download_anki(self, task_manager):
        # Anki 덱 다운로드 요청을 로그로 출력
        self.log_signal.emit("다운로드: Anki 덱 전체 다운로드를 요청했습니다.")