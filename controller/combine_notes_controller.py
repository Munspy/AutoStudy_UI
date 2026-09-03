"""PDF 파일의 매칭, 검수 및 병합 작업을 관리하는 컨트롤러 모듈입니다.

이 모듈은 UI(ui_combine_notes_ui)로부터 입력을 받아 백그라운드 워커를 실행하고,
작업 완료 시 결과를 시그널로 전달하여 UI를 업데이트하는 역할을 수행합니다.
주요 의존성으로 BaseController 및 worker.pdf 내의 관련 워커들을 사용합니다.
"""
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController

# 지금 PDF worker 에 너무 많은 worker들이 산재해 있는데
# 이를 적절하게 쪼개서 여러 worker 파일들로 만들어야 함
# 추후에 AI 에이전트의 도움을 받아서 해결하자

# 각 실행 코드 시작부에 self.cleanup_worker() 들이 반복되는데 다른 코드에서도 이거 다 없애야 함
from worker.pdf import PdfInspectionWorker, PdfCombineSaveWorker, PdfMatchListWorker

class CombineNotesController(BaseController):
    """PDF 파일 매칭, 검수, 병합 작업을 담당하는 컨트롤러 클래스입니다.

    BaseController를 상속받으며, UI 액션에 따라 적절한 백그라운드 워커를
    실행하고 그 결과를 시그널로 방출합니다.

    Attributes:
        match_list_completed (pyqtSignal): 매칭 리스트 작업이 완료되었을 때 그룹 데이터를 전달하는 시그널.
        inspection_completed (pyqtSignal): 검수 작업이 완료되었을 때 검수 결과를 전달하는 시그널.
        merge_completed (pyqtSignal): 병합 작업이 완료되었을 때 결과를 전달하는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    # 매칭 목록 작업 완료 시그널
    match_list_completed = pyqtSignal(dict)
    # 검수 작업 완료 시그널
    inspection_completed = pyqtSignal(list)
    # 병합 작업 완료 시그널
    merge_completed = pyqtSignal(list)

    def __init__(self, task_manager=None):
        # 부모 클래스의 초기화 메서드 호출하여 task_manager 연동
        super().__init__(task_manager)

    # ===========================
    # [워커 실행 메서드]
    # ===========================
    def start_get_matched_groups(self, folder_path):
        """지정된 폴더에서 매칭 가능한 PDF 그룹 목록을 탐색하는 워커를 실행합니다.

        전체 흐름에서 병합 대상을 찾기 위해 가장 먼저 호출되며,
        작업이 완료되면 `match_list_completed` 시그널로 결과를 전달합니다.

        Args:
            folder_path (str): 탐색할 대상 PDF 파일들이 있는 폴더 경로입니다.

        Returns:
            None

        Raises:
            Exception: 워커 실행 중 예외가 발생할 수 있습니다.
        """
        # 대상 폴더에서 매칭 가능한 PDF 리스트를 구하기 위해 워커 생성
        worker = PdfMatchListWorker(folder_path)
        # 워커 작업이 끝나면 match_list_completed 시그널을 방출하도록 연결
        worker.finished_signal.connect(self.match_list_completed.emit)
        # 생성한 워커를 백그라운드 스레드에서 실행
        self.start_worker(worker)

    def start_inspection(self, folder_path, selected_keys, matched_groups):
        """UI 입력을 바탕으로 무거운 PDF 파싱 및 매칭 검수 워커를 실행합니다.

        매칭된 그룹 데이터를 바탕으로 실제 PDF 텍스트를 추출하고 
        논리적인 연결이나 누락이 없는지 검사하기 위해 호출됩니다.

        Args:
            folder_path (str): 대상 PDF 파일들이 위치한 폴더 경로입니다.
            selected_keys (list): 사용자가 선택한 검수 대상 그룹 키 목록입니다.
            matched_groups (dict): 사전에 매칭된 PDF 파일들의 그룹 정보입니다.

        Returns:
            None

        Raises:
            Exception: 검수 과정에서 예기치 않은 오류가 발생할 수 있습니다.
        """
        # 사용자 선택에 따라 PDF 검수 워커 생성
        worker = PdfInspectionWorker(folder_path, selected_keys, matched_groups)
        # 검수 완료 시 inspection_completed 시그널을 방출하도록 연결
        worker.finished_signal.connect(self.inspection_completed.emit)
        # 워커를 시작하여 백그라운드에서 검수 진행
        self.start_worker(worker)

    def start_merge(self, base_data, folder_path, is_drive=True):
        """검수 완료된 레시피를 기반으로 디스크에 실제 PDF를 병합 저장하는 워커를 실행합니다.

        Args:
            base_data (list): 검수를 통해 확정된 병합 대상 레시피 데이터입니다.
            folder_path (str): 결과물 PDF가 저장될 기준 폴더 경로 (is_drive=False 시 사용).
            is_drive (bool): True이면 구글 드라이브로 업로드. 기본값 True.
        """
        # 검수 통과 데이터를 바탕으로 PDF를 병합하여 저장할 워커 생성
        worker = PdfCombineSaveWorker(base_data, folder_path, is_drive=is_drive)
        # 병합 완료 시 merge_completed 시그널 방출 연결
        worker.finished_signal.connect(self.merge_completed.emit)
        # 백그라운드에서 워커 실행
        self.start_worker(worker)
