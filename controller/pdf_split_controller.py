"""PDF 파일 분할 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab4PdfSplit)와 연동하여 분할할 PDF 파일 목록 조회,
미리보기 생성, 페이지 렌더링, 실제 파일 분할 및 저장을 처리하는 워커를 제어합니다.
"""
# controller/pdf_split_controller.py
import os
import shutil
import tempfile
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.pdf import PdfFileListWorker, PdfPreviewPrepareWorker, PdfSplitWorker



class PdfSplitController(BaseController):
    """PDF 파일 분할 제어를 담당하는 클래스입니다.

    BaseController를 상속하며 PDF 파일 분할을 위한 파일 조회, 
    미리보기 준비 및 렌더링, 분할 처리를 담당하는 백그라운드 워커를 관리합니다.

    Attributes:
        file_list_ready (pyqtSignal): 파일 목록 조회 결과를 전달하는 시그널.
        preview_ready (pyqtSignal): 파일 다운로드 및 준비가 완료된 정보를 전달하는 시그널.
        page_rendered (pyqtSignal): 단일 페이지 이미지 렌더링 결과를 전달하는 시그널.
        split_completed (pyqtSignal): 분할 작업 완료 메시지를 전달하는 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    file_list_ready = pyqtSignal(dict)
    preview_ready = pyqtSignal(dict)
    page_rendered = pyqtSignal(int, bytes)
    split_completed = pyqtSignal(str)

    def __init__(self, task_manager=None):
        # BaseController 상속 초기화
        super().__init__(task_manager)
        # 파일 분할 전 임시로 사용할 디렉토리 생성
        self.temp_dir = tempfile.mkdtemp()

    def __del__(self):
        # 객체가 소멸될 때 임시 디렉토리를 정리
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ===========================
    # [파일 목록 조회]
    # ===========================
    def start_fetch_file_list(self, is_drive, target_dir, start_str, end_str):
        """분할 대상이 될 PDF 파일 목록을 조회하는 워커를 실행합니다.

        Args:
            is_drive (bool): 구글 드라이브 검색 여부.
            target_dir (str): 탐색할 대상 폴더 경로.
            start_str (str): 파일 이름의 시작 조건.
            end_str (str): 파일 이름의 끝 조건.

        Returns:
            None
        """
        # 탐색 대상 경로와 조건을 바탕으로 워커 생성
        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        # 작업이 끝나면 조회된 목록을 시그널로 방출
        worker.finished_signal.connect(self.file_list_ready.emit)
        # 백그라운드에서 워커 실행
        self.start_worker(worker)

    # ===========================
    # [미리보기 준비 및 렌더링]
    # ===========================
    def start_prepare_preview(self, path_or_id, is_drive):
        """선택된 PDF 파일의 미리보기를 준비하는 워커를 실행합니다.

        Args:
            path_or_id (str): 로컬 파일 경로 또는 구글 드라이브 파일 ID.
            is_drive (bool): 구글 드라이브 파일 여부.

        Returns:
            None
        """
        # 미리보기를 위한 파일 다운로드 및 준비 워커 생성
        worker = PdfPreviewPrepareWorker(path_or_id, is_drive, self.temp_dir)
        # 준비 완료 시 결과를 전달하기 위해 시그널 연결
        worker.finished_signal.connect(self.preview_ready.emit)
        # 워커 실행 시작
        self.start_worker(worker)

    def start_render_pages(self, local_path, total_pages):
        """PDF 파일의 전체 페이지를 렌더링하는 워커를 실행합니다.

        Args:
            local_path (str): 렌더링할 로컬 PDF 파일 경로.
            total_pages (int): 렌더링할 전체 페이지 수.

        Returns:
            None
        """
        from worker.pdf import PdfSplitPreviewRenderWorker
        # PDF의 페이지별 렌더링 작업을 수행할 워커 생성
        worker = PdfSplitPreviewRenderWorker(local_path, total_pages)
        # 단일 페이지 렌더링 완료 시마다 시그널 방출
        worker.page_rendered.connect(self.page_rendered.emit)
        # 렌더링 워커 시작
        self.start_worker(worker)

    # ===========================
    # [PDF 분할 저장]
    # ===========================
    def start_split_and_save(self, local_path, total_pages, split_page_text,
        out1_name, out2_name, is_drive, target_dir, original_id=None,
        original_is_drive=False):
        """지정된 기준 페이지를 바탕으로 PDF 파일을 두 개로 분할하고 저장하는 워커를 실행합니다.

        Args:
            local_path (str): 분할할 대상 PDF 파일 경로.
            total_pages (int): 대상 파일의 전체 페이지 수.
            split_page_text (str): 분할 기준이 되는 페이지 번호 텍스트.
            out1_name (str): 첫 번째 분할 결과물의 파일명.
            out2_name (str): 두 번째 분할 결과물의 파일명.
            is_drive (bool): 결과를 구글 드라이브에 저장할지 여부.
            target_dir (str): 결과물을 저장할 폴더 경로.
            original_id (str): 원본 파일의 경로 또는 드라이브 ID.
            original_is_drive (bool): 원본 파일이 드라이브 소스인지 여부.

        Returns:
            None
        """
        # 분할할 파일이 없으면 에러 처리
        if not local_path:
            self.error_signal.emit("오류", "분할할 파일을 선택해주세요.")
            return

        # 분할 기준 페이지 번호 및 중복 포함(!) 옵션 파싱
        is_overlap = False
        text = split_page_text.strip()
        if text.startswith('!'):
            is_overlap = True
            text = text[1:]
            
        try:
            split_page = int(text)
        except ValueError:
            self.error_signal.emit("오류", "정확히 1개의 기준 페이지 번호(분할 지점)를 입력해주세요. (예: 3 또는 !3)")
            return

        # 기준 페이지가 유효 범위를 벗어나면 에러 처리
        if split_page <= 0 or split_page >= total_pages:
            self.error_signal.emit("오류", f"분할 페이지 번호가 범위를 벗어났습니다. (1~{total_pages-1})")
            return

        # 출력 파일명에 '.pdf' 확장자 추가
        if not out1_name.endswith('.pdf'): out1_name += '.pdf'
        if not out2_name.endswith('.pdf'): out2_name += '.pdf'

        # 분할 작업을 수행할 워커 객체 생성
        worker = PdfSplitWorker(
            local_path=local_path,
            split_page=split_page,
            out1_name=out1_name,
            out2_name=out2_name,
            is_drive=is_drive,
            target_dir=target_dir,
            original_id=original_id,
            original_is_drive=original_is_drive,
            is_overlap=is_overlap
        )
        # 분할 및 저장 완료 시 결과를 전달
        worker.finished_signal.connect(self.split_completed.emit)
        # 백그라운드 워커 실행
        self.start_worker(worker)

