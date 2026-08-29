from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.pdf_worker import PdfInspectionThread, PdfCombineSaveThread
from service.pdf_analysis_service import PdfAnalysisService

class CombineNotesController(BaseController):
    """
    [Tab 2] 백엔드 컨트롤러
    UI의 지시를 받아 백그라운드 스레드를 생성하고 이벤트를 관리합니다.
    """
    inspection_completed = pyqtSignal(list)
    merge_completed = pyqtSignal(list)

    def __init__(self, view=None):
        super().__init__(ui_view=view)
        self._pdf_service = PdfAnalysisService()

    def get_matched_file_groups(self, folder_path):
        return self._pdf_service.get_matched_file_groups(folder_path)

    def prepare_edit_data(self, base_data):
        return self._pdf_service.prepare_edit_data(base_data)

    def save_edits(self, edit_data):
        return self._pdf_service.save_edits(edit_data)

    def split_item_on_yaboot_check(self, item):
        return self._pdf_service.split_item_on_yaboot_check(item)

    def swap_items(self, edit_data, idx, direction):
        return self._pdf_service.swap_items(edit_data, idx, direction)

    def start_inspection(self, folder_path, selected_keys, matched_groups):
        """UI 입력을 바탕으로 무거운 PDF 파싱 및 매칭 검수 워커를 실행합니다."""
        self.cleanup_worker()
        self.worker = PdfInspectionThread(folder_path, selected_keys, matched_groups)
        
        self.worker.success_signal.connect(self.inspection_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()

    def start_merge(self, base_data, folder_path):
        """검수 완료된 레시피를 기반으로 디스크에 실제 PDF를 병합 저장하는 워커를 실행합니다."""
        self.cleanup_worker()
        self.worker = PdfCombineSaveThread(base_data, folder_path)
        
        self.worker.success_signal.connect(self.merge_completed.emit)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()