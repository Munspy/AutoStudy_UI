from base.base_worker import BaseWorker
from service.pdf_operation_service import PdfOperationService

class PdfMergeWorker(BaseWorker):
    def __init__(self, task_data):
        super().__init__()
        self.task = task_data

    def do_work(self):
        self.log_signal.emit("🚀 PDF 병합 작업을 백그라운드에서 시작합니다...")
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        target_files = self.task['files']
        out_name = self.task['out_name']
        is_drive = self.task['is_drive']
        target_dir = self.task['target_dir']
        
        if not out_name.endswith('.pdf'): out_name += '.pdf'
        
        if self.is_cancelled(): return None

        success, msg = operation_service.merge_and_save(
            target_files=target_files,
            out_name=out_name,
            is_drive=is_drive,
            target_dir=target_dir
        )
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg
