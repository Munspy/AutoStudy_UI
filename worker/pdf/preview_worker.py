import os
import pymupdf
from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker
from utils.auth_util import get_drive_service
from utils.drive_api import download_from_drive

class PdfPreviewPrepareWorker(BaseWorker):
    """PDF 미리보기를 위한 준비 워커 클래스입니다."""
    def __init__(self, path_or_id, is_drive, temp_dir):
        """PdfPreviewPrepareWorker 초기화.
        
        Args:
            path_or_id (str): 로컬 파일 경로 또는 구글 드라이브 ID.
            is_drive (bool): 드라이브 파일 여부.
            temp_dir (str): 임시 디렉토리 경로.
        """
        super().__init__()
        self.path_or_id = path_or_id
        self.is_drive = is_drive
        self.temp_dir = temp_dir

    def do_work(self):
        """PDF 파일을 다운로드하고 총 페이지 수를 반환합니다."""
        # ===========================
        # [파일 경로 설정 및 다운로드]
        # ===========================
        local_path = None
        if self.is_drive:
            # 드라이브 파일인 경우 서비스를 가져와서 다운로드합니다.
            drive_service = get_drive_service()
            temp_path = os.path.join(self.temp_dir, f"{self.path_or_id}.pdf")
            if not os.path.exists(temp_path):
                self.log_signal.emit(f"🔄 구글 드라이브에서 PDF 파일 다운로드 중...")
                download_from_drive(self.path_or_id, temp_path, drive_service=drive_service)
            local_path = temp_path
        else:
            # 로컬 파일인 경우 경로를 그대로 사용합니다.
            local_path = self.path_or_id

        # ===========================
        # [PDF 문서 열기 및 페이지 수 확인]
        # ===========================
        total_pages = 0
        try:
            # pymupdf를 사용하여 문서를 열고 페이지 수를 구합니다.
            with pymupdf.open(local_path) as doc:
                total_pages = len(doc)
        except Exception as e:
            # 오류 발생 시 에러 시그널을 방출합니다.
            self.error_signal.emit(f"PDF 열기 실패: {str(e)}")
            return None
            
        return {"local_path": local_path, "total_pages": total_pages}

class PdfSplitPreviewRenderWorker(BaseWorker):
    """PDF 페이지 렌더링을 처리하는 워커 클래스입니다."""
    page_rendered = pyqtSignal(int, bytes)

    def __init__(self, local_path, total_pages):
        """PdfSplitPreviewRenderWorker 초기화."""
        super().__init__()
        self.local_path = local_path
        self.total_pages = total_pages

    def do_work(self):
        """각 PDF 페이지를 이미지로 변환하여 시그널로 전달합니다."""
        # ===========================
        # [페이지 렌더링 루프]
        # ===========================
        try:
            with pymupdf.open(self.local_path) as doc:
                for i in range(self.total_pages):
                    # 취소 요청이 있으면 루프를 중단합니다.
                    if self.is_cancelled():
                        break
                    # 페이지를 로드하고 이미지로 변환합니다.
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
                    img_data = pix.tobytes("png")
                    # 렌더링된 이미지 데이터를 시그널로 전달합니다.
                    self.page_rendered.emit(i, img_data)
        except Exception as e:
            self.error_signal.emit(f"미리보기 렌더링 실패: {str(e)}")
        return None

class PdfBatchPreviewPrepareWorker(BaseWorker):
    """다수의 PDF 미리보기를 준비하는 워커 클래스입니다."""
    prepared_signal = pyqtSignal(str, object, str, bool, str)

    def __init__(self, items_to_prepare, file_paths, drive_cache, temp_dir, is_drive):
        """PdfBatchPreviewPrepareWorker 초기화."""
        super().__init__()
        self.items_to_prepare = items_to_prepare
        self.file_paths = file_paths
        self.drive_cache = drive_cache.copy()
        self.temp_dir = temp_dir
        self.is_drive = is_drive

    def do_work(self):
        """여러 PDF 항목을 준비하고 열어서 시그널로 전달합니다."""
        # ===========================
        # [일괄 처리 루프]
        # ===========================
        for item_text in self.items_to_prepare:
            if self.is_cancelled():
                break
            if item_text not in self.file_paths:
                continue
            path_or_id = self.file_paths[item_text]
            
            # ===========================
            # [파일 다운로드 및 캐시 확인]
            # ===========================
            local_path = path_or_id
            if self.is_drive:
                # 드라이브 캐시에 없는 경우 임시 디렉토리로 다운로드합니다.
                if path_or_id not in self.drive_cache:
                    temp_path = os.path.join(self.temp_dir, f"{path_or_id}.pdf")
                    try:
                        download_from_drive(path_or_id, temp_path, drive_service=get_drive_service())
                    except Exception as e:
                        self.error_signal.emit(f"다운로드 실패: {e}")
                        continue
                    local_path = temp_path
                else:
                    local_path = self.drive_cache[path_or_id]
            
            if self.is_cancelled():
                break
                
            # ===========================
            # [PDF 문서 로드 및 시그널 방출]
            # ===========================
            try:
                doc = pymupdf.open(local_path)
                self.prepared_signal.emit(item_text, doc, path_or_id, self.is_drive, local_path)
            except Exception as e:
                self.error_signal.emit(f"PDF 열기 실패: {e}")
                
        return None
