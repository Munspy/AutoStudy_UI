"""PDF 파일 병합 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab3PdfMerge)와 연동하여 병합할 PDF 파일 목록 조회,
미리보기 생성, 실제 병합 작업을 수행하는 워커들을 제어합니다.
"""
from base.base_controller import BaseController
from worker.pdf import PdfFileListWorker, PdfMergeWorker
from PyQt6.QtCore import pyqtSignal

class PdfMergeController(BaseController):
    """PDF 파일 병합 제어를 담당하는 클래스입니다.

    BaseController를 상속하며 대상 파일 목록 조회, 미리보기, 병합 등의
    작업을 백그라운드 워커에 위임하고 결과를 시그널로 전달합니다.

    Attributes:
        file_list_ready (pyqtSignal): 대상 파일 목록 조회가 완료되었을 때 발생하는 시그널.
        merge_completed (pyqtSignal): PDF 병합이 완료된 후 결과 메시지를 전달하는 시그널.
        preview_prepared (pyqtSignal): 단일 PDF 미리보기가 준비될 때 발생하는 시그널.
        preview_finished (pyqtSignal): 모든 미리보기 준비 작업이 완료되었음을 알리는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    file_list_ready = pyqtSignal(dict)
    merge_completed = pyqtSignal(str)
    preview_prepared = pyqtSignal(str, object, str, bool, str)
    preview_finished = pyqtSignal(object)

    def __init__(self, task_manager=None):
        # BaseController를 통한 컨트롤러 초기화
        super().__init__(task_manager)

    # ===========================
    # [파일 목록 조회]
    # ===========================
    def start_fetch_file_list(self, is_drive, target_dir, start_str, end_str):
        """병합 대상이 될 PDF 파일 목록을 조회하는 워커를 실행합니다.

        지정된 경로(로컬 또는 구글 드라이브)에서 조건에 맞는 파일들을 가져옵니다.

        Args:
            is_drive (bool): 구글 드라이브 검색 여부.
            target_dir (str): 탐색할 대상 폴더 경로.
            start_str (str): 파일 이름의 시작 조건 문자열.
            end_str (str): 파일 이름의 끝 조건 문자열.

        Returns:
            None
        """
        # 대상 폴더에서 조건에 맞는 파일 목록을 가져오기 위한 워커 생성
        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        # 작업 완료 시 결과를 UI로 전달하도록 시그널 연결
        worker.finished_signal.connect(self.file_list_ready.emit)
        # 백그라운드에서 조회 워커 실행
        self.start_worker(worker)

    # ===========================
    # [미리보기 준비]
    # ===========================
    def start_prepare_previews(self, items_to_prepare, file_paths, drive_cache, temp_dir, is_drive):
        """목록에 추가된 PDF 파일들의 첫 페이지 미리보기를 일괄 생성하는 워커를 실행합니다.

        로컬 파일 또는 드라이브에서 파일을 임시 다운로드한 후, 미리보기 이미지를 추출합니다.

        Args:
            items_to_prepare (list): 미리보기를 생성할 대상 아이템 목록.
            file_paths (dict): 각 파일의 경로 또는 ID 매핑.
            drive_cache (dict): 구글 드라이브 캐시 데이터.
            temp_dir (str): 임시 작업용 디렉토리 경로.
            is_drive (bool): 드라이브 모드 여부.

        Returns:
            None
        """
        from worker.pdf import PdfBatchPreviewPrepareWorker
        # 여러 PDF 파일의 미리보기를 일괄 생성할 워커 인스턴스 생성
        worker = PdfBatchPreviewPrepareWorker(items_to_prepare, file_paths, drive_cache, temp_dir, is_drive)
        # 개별 파일 미리보기 준비가 완료될 때마다 시그널 발생
        worker.prepared_signal.connect(self.preview_prepared.emit)
        # 전체 미리보기 준비가 끝나면 완료 시그널 방출
        worker.finished_signal.connect(self.preview_finished.emit)
        # 백그라운드에서 렌더링 시작
        self.start_worker(worker)

    # ===========================
    # [PDF 병합 실행]
    # ===========================
    def start_merge(self, task_data):
        """사용자가 설정한 순서대로 PDF 파일을 병합하는 워커를 실행합니다.

        Args:
            task_data (dict): 병합할 파일 목록과 결과 저장 경로 등 설정 정보.

        Returns:
            None
        """
        # 파일이 2개 이상 선택되지 않았으면 에러 발생
        if len(task_data['files']) < 2:
            self.error_signal.emit("오류", "병합할 PDF 파일을 2개 이상 선택해주세요.")
            return
            
        # PDF 병합 처리를 위한 워커 객체 생성
        worker = PdfMergeWorker(task_data)
        # 병합 완료 시 결과를 전달하기 위한 연결
        worker.finished_signal.connect(self.merge_completed.emit)
        # 백그라운드에서 병합 작업 시작
        self.start_worker(worker)
