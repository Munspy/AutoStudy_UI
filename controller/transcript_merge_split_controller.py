"""스크립트(텍스트) 파일의 조회, 병합, 분할 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab5TranscriptMergeSplit)와 연동하여 로컬 및 구글 드라이브 상의
텍스트 파일 검색, 내용 읽기, 내용 분할 및 병합 저장 워커들을 제어합니다.
"""
# controller/transcript_merge_split_controller.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from utils.file_util import list_local_files
from worker.transcript.transcript_worker import (
    TranscriptDriveSearchWorker, 
    TranscriptReadWorker, 
    TranscriptSplitSaveWorker, 
    TranscriptMergeSaveWorker
)

class TranscriptController(BaseController):
    """스크립트 병합 및 분할 작업을 제어하는 클래스입니다.

    BaseController를 상속하며 스크립트 검색, 읽기, 분할, 병합과 관련된
    워커들을 인스턴스화하여 실행하고 결과를 UI에 전달합니다.

    Attributes:
        search_completed (pyqtSignal): 드라이브 파일 검색 완료 시 결과를 전달하는 시그널.
        files_read_completed (pyqtSignal): 대상 파일들의 텍스트 읽기가 완료되었을 때 정보를 전달하는 시그널.
        split_save_completed (pyqtSignal): 텍스트 분할 저장이 완료되었을 때 결과를 전달하는 시그널.
        merge_save_completed (pyqtSignal): 텍스트 병합 저장이 완료되었을 때 결과를 전달하는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    search_completed = pyqtSignal(list)
    files_read_completed = pyqtSignal(int, list, list)
    split_save_completed = pyqtSignal(list)
    merge_save_completed = pyqtSignal(str)

    def __init__(self, task_manager=None):
        # BaseController 초기화
        super().__init__(task_manager)
        # 구글 드라이브 검색 결과를 캐싱할 딕셔너리
        self.drive_files_cache = {}

    # ===========================
    # [파일 검색 및 읽기]
    # ===========================
    def get_local_text_files(self, directory: str):
        # 주어진 로컬 디렉토리에서 .txt 확장자 파일들을 탐색하여 반환
        return list_local_files(directory, extension=".txt")

    def execute_drive_search(self, start_date, end_date):
        """구글 드라이브에서 텍스트 스크립트 파일들을 검색하는 워커를 실행합니다.

        Args:
            start_date (str): 검색을 시작할 날짜 조건.
            end_date (str): 검색을 종료할 날짜 조건.

        Returns:
            None
        """
        # 드라이브 검색 워커 객체 생성
        worker = TranscriptDriveSearchWorker(start_date, end_date)
        def on_search_completed(result):
            # 검색 완료 시 캐시 업데이트 및 결과 시그널 방출
            if result:
                files, cache = result
                self.drive_files_cache = cache
                self.search_completed.emit(files)
        # 검색 완료 시그널 연결
        worker.finished_signal.connect(on_search_completed)
        # 백그라운드 워커 실행
        self.start_worker(worker)

    def execute_read_files(self, filenames, folder_path, is_drive):
        """선택한 스크립트 파일들의 텍스트 내용을 읽어오는 워커를 실행합니다.

        Args:
            filenames (list): 읽을 대상 파일명 목록.
            folder_path (str): 파일이 위치한 기준 폴더.
            is_drive (bool): 드라이브 모드 여부.

        Returns:
            None
        """
        # 파일 내용을 읽어오는 워커 객체 생성
        worker = TranscriptReadWorker(filenames, folder_path, is_drive, drive_cache=self.drive_files_cache if is_drive else None)
        # 읽기 작업이 완료되면 파일 갯수, 이름 목록, 내용을 묶어서 시그널 방출
        worker.finished_signal.connect(
            lambda res: self.files_read_completed.emit(len(res["filenames"]), res["filenames"], res["contents"]) if res else None
        )
        # 워커 실행 시작
        self.start_worker(worker)

    # ===========================
    # [파일 분할 및 병합 저장]
    # ===========================
    def execute_split_save(self, folder_path, filename, text_content, name1, name2, is_drive):
        """사용자가 수정한 텍스트 내용을 분할하여 2개의 새로운 파일로 저장하는 워커를 실행합니다.

        Args:
            folder_path (str): 저장될 기준 폴더 경로.
            filename (str): 원본 파일명.
            text_content (list): 2개로 분할된 텍스트 컨텐츠.
            name1 (str): 첫 번째 분할 저장할 파일명.
            name2 (str): 두 번째 분할 저장할 파일명.
            is_drive (bool): 드라이브 모드 여부.

        Returns:
            None
        """
        # 분할 저장 작업을 처리할 워커 생성
        worker = TranscriptSplitSaveWorker(folder_path, filename, text_content, name1, name2, is_drive)
        # 저장 완료 시 시그널 방출 연결
        worker.finished_signal.connect(self.split_save_completed.emit)
        # 워커 실행
        self.start_worker(worker)

    def execute_merge_save(self, folder_path, files_to_merge, merged_content, custom_name, is_drive):
        """여러 스크립트 파일 내용을 하나로 병합하여 저장하는 워커를 실행합니다.

        Args:
            folder_path (str): 저장될 기준 폴더 경로.
            files_to_merge (list): 병합할 원본 파일 목록.
            merged_content (str): 하나로 합쳐진 텍스트 컨텐츠.
            custom_name (str): 병합본을 저장할 커스텀 파일명.
            is_drive (bool): 드라이브 모드 여부.

        Returns:
            None
        """
        # 병합 저장 작업을 처리할 워커 생성
        worker = TranscriptMergeSaveWorker(folder_path, files_to_merge, merged_content, custom_name, is_drive)
        # 완료 시 시그널 연결
        worker.finished_signal.connect(self.merge_save_completed.emit)
        # 워커 실행
        self.start_worker(worker)

# ===========================
# [유틸리티 함수]
# ===========================
def generate_split_filenames(filename: str) -> list:
    # 파일명 생성 서비스를 이용해 분할 파일명 자동 생성
    from service.file_naming_service import FileNamingService
    return FileNamingService().generate_split_filenames(filename)

def generate_merged_filename(filenames: list) -> str:
    # 파일명 생성 서비스를 이용해 병합 파일명 자동 생성
    from service.file_naming_service import FileNamingService
    return FileNamingService().generate_merged_filename(filenames)
