import os
import pymupdf
from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker
from utils.auth_util import get_drive_service
from utils.drive_api import download_from_drive

class PdfPreviewPrepareWorker(BaseWorker):
    def __init__(self, path_or_id, is_drive, temp_dir):
        super().__init__()
        self.path_or_id = path_or_id
        self.is_drive = is_drive
        self.temp_dir = temp_dir

    def do_work(self):
        local_path = None
        if self.is_drive:
            drive_service = get_drive_service()
            temp_path = os.path.join(self.temp_dir, f"{self.path_or_id}.pdf")
            if not os.path.exists(temp_path):
                self.log_signal.emit(f"🔄 구글 드라이브에서 PDF 파일 다운로드 중...")
                download_from_drive(self.path_or_id, temp_path, drive_service=drive_service)
            local_path = temp_path
        else:
            local_path = self.path_or_id

        total_pages = 0
        try:
            with pymupdf.open(local_path) as doc:
                total_pages = len(doc)
        except Exception as e:
            self.error_signal.emit(f"PDF 열기 실패: {str(e)}")
            return None
            
        return {"local_path": local_path, "total_pages": total_pages}

class PdfSplitPreviewRenderWorker(BaseWorker):
    page_rendered = pyqtSignal(int, bytes)

    def __init__(self, local_path, total_pages):
        super().__init__()
        self.local_path = local_path
        self.total_pages = total_pages

    def do_work(self):
        try:
            with pymupdf.open(self.local_path) as doc:
                for i in range(self.total_pages):
                    if self.is_cancelled():
                        break
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
                    img_data = pix.tobytes("png")
                    self.page_rendered.emit(i, img_data)
        except Exception as e:
            self.error_signal.emit(f"미리보기 렌더링 실패: {str(e)}")
        return None

class PdfBatchPreviewPrepareWorker(BaseWorker):
    prepared_signal = pyqtSignal(str, object, str, bool, str)

    def __init__(self, items_to_prepare, file_paths, drive_cache, temp_dir, is_drive):
        super().__init__()
        self.items_to_prepare = items_to_prepare
        self.file_paths = file_paths
        self.drive_cache = drive_cache.copy()
        self.temp_dir = temp_dir
        self.is_drive = is_drive

    def do_work(self):
        for item_text in self.items_to_prepare:
            if self.is_cancelled():
                break
            if item_text not in self.file_paths:
                continue
            path_or_id = self.file_paths[item_text]
            
            local_path = path_or_id
            if self.is_drive:
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
                
            try:
                doc = pymupdf.open(local_path)
                self.prepared_signal.emit(item_text, doc, path_or_id, self.is_drive, local_path)
            except Exception as e:
                self.error_signal.emit(f"PDF 열기 실패: {e}")
                
        return None
