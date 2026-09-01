from base.base_worker import BaseWorker
from service.pdf_operation_service import PdfOperationService

class PdfSplitWorker(BaseWorker):
    def __init__(self, local_path, split_page, out1_name, out2_name, is_drive, target_dir):
        super().__init__()
        self.local_path = local_path
        self.split_page = split_page
        self.out1_name = out1_name
        self.out2_name = out2_name
        self.is_drive = is_drive
        self.target_dir = target_dir

    def do_work(self):
        self.log_signal.emit("🚀 PDF 분할 작업을 백그라운드에서 시작합니다...")
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        if self.is_cancelled(): return None

        success, msg = operation_service.split_and_save(
            local_path=self.local_path,
            split_page=self.split_page,
            out1_name=self.out1_name,
            out2_name=self.out2_name,
            is_drive=self.is_drive,
            target_dir=self.target_dir
        )
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg
