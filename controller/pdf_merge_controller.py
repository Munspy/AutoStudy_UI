from base.base_controller import BaseController
from worker.pdf_worker import PdfFileListWorker, PdfMergeWorker
from PyQt6.QtCore import pyqtSignal

class PdfMergeController(BaseController):
    file_list_ready = pyqtSignal(dict)
    merge_completed = pyqtSignal(str)
    preview_prepared = pyqtSignal(str, object, str, bool, str)
    preview_finished = pyqtSignal(object)

    def __init__(self, task_manager=None):
        super().__init__(task_manager)

    def start_fetch_file_list(self, is_drive, target_dir, start_str, end_str):
        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        worker.finished_signal.connect(self.file_list_ready.emit)
        self.start_worker(worker)

    def start_prepare_previews(self, items_to_prepare, file_paths, drive_cache, temp_dir, is_drive):
        from worker.pdf_worker import PdfBatchPreviewPrepareWorker
        worker = PdfBatchPreviewPrepareWorker(items_to_prepare, file_paths, drive_cache, temp_dir, is_drive)
        worker.prepared_signal.connect(self.preview_prepared.emit)
        worker.finished_signal.connect(self.preview_finished.emit)
        self.start_worker(worker)

    def start_merge(self, task_data):
        if len(task_data['files']) < 2:
            self.error_signal.emit("오류", "병합할 PDF 파일을 2개 이상 선택해주세요.")
            return
            
        worker = PdfMergeWorker(task_data)
        worker.finished_signal.connect(self.merge_completed.emit)
        self.start_worker(worker)
