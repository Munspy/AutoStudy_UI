from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.pdf_worker import PdfInspectionThread, PdfCombineSaveThread
from service.pdf_analysis_service import PdfAnalysisService

# 1. UI 호출 호환성을 위해 싱글톤 서비스 인스턴스를 컨트롤러 레벨에 생성
_pdf_service = PdfAnalysisService()

# 2. 기존에 UI가 `backend.함수명()` 형태로 접근하던 엔드포인트들을 살려두되, 
# 모든 실제 연산은 Service 계층으로 전달(Delegation)합니다.
def get_matched_file_groups(folder_path):
    return _pdf_service.get_matched_file_groups(folder_path)

def generate_real_data(folder_path, selected_keys, matched_groups):
    return _pdf_service.generate_matching_data(folder_path, selected_keys, matched_groups)

def prepare_edit_data(base_data):
    return _pdf_service.prepare_edit_data(base_data)

def save_edits(edit_data):
    return _pdf_service.save_edits(edit_data)

def split_item_on_yaboot_check(item):
    return _pdf_service.split_item_on_yaboot_check(item)

def swap_items(edit_data, idx, direction):
    return _pdf_service.swap_items(edit_data, idx, direction)

def execute_merge(base_data, output_folder):
    return _pdf_service.execute_merge(base_data, output_folder)

# 3. 비즈니스 로직이 완전히 분리되어, 순수하게 스레드 제어만 담당하는 얇은 컨트롤러
class CombineNotesController(BaseController):
    """
    [Tab 2] 백엔드 컨트롤러
    UI의 지시를 받아 백그라운드 스레드를 생성하고 이벤트를 관리합니다.
    """
    inspection_completed = pyqtSignal(list)
    merge_completed = pyqtSignal(list)

    def __init__(self):
        super().__init__()

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