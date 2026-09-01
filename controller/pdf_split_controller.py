# controller/pdf_split_controller.py
import os
import shutil
import tempfile
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.pdf import PdfFileListWorker, PdfPreviewPrepareWorker, PdfSplitWorker



class PdfSplitController(BaseController):
    file_list_ready = pyqtSignal(dict)
    preview_ready = pyqtSignal(dict)
    page_rendered = pyqtSignal(int, bytes)
    split_completed = pyqtSignal(str)

    def __init__(self, task_manager=None):
        super().__init__(task_manager)
        self.temp_dir = tempfile.mkdtemp()

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def start_fetch_file_list(self, is_drive, target_dir, start_str, end_str):
        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        worker.finished_signal.connect(self.file_list_ready.emit)
        self.start_worker(worker)

    def start_prepare_preview(self, path_or_id, is_drive):
        worker = PdfPreviewPrepareWorker(path_or_id, is_drive, self.temp_dir)
        worker.finished_signal.connect(self.preview_ready.emit)
        self.start_worker(worker)

    def start_render_pages(self, local_path, total_pages):
        from worker.pdf import PdfSplitPreviewRenderWorker
        worker = PdfSplitPreviewRenderWorker(local_path, total_pages)
        worker.page_rendered.connect(self.page_rendered.emit)
        self.start_worker(worker)

    def start_split_and_save(self, local_path, total_pages, split_page_text, out1, out2, is_drive, target_dir):
        if not local_path:
            self.error_signal.emit("오류", "분할할 파일을 선택해주세요.")
            return

        try:
            split_page = int(split_page_text.strip())
        except ValueError:
            self.error_signal.emit("오류", "정확히 1개의 기준 페이지 번호(분할 지점)를 입력해주세요. (예: 3)")
            return

        if split_page <= 0 or split_page >= total_pages:
            self.error_signal.emit("오류", f"분할 페이지 번호가 범위를 벗어났습니다. (1~{total_pages-1})")
            return

        if not out1.endswith('.pdf'): out1 += '.pdf'
        if not out2.endswith('.pdf'): out2 += '.pdf'
        
        target = target_dir if not is_drive else None

        worker = PdfSplitWorker(local_path, split_page, out1, out2, is_drive, target)
        worker.finished_signal.connect(self.split_completed.emit)
        self.start_worker(worker)

