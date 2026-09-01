from base.base_worker import BaseWorker
from service.pdf_analysis_service import PdfAnalysisService
from service.pdf_operation_service import PdfOperationService

class PdfMatchListWorker(BaseWorker):
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def do_work(self):
        self.log_signal.emit("🔍 지정된 폴더에서 병합할 PDF 파일 그룹을 탐색합니다...")
        if self.is_cancelled(): return None
        return PdfAnalysisService(logger_callback=self.log_signal.emit).get_matched_file_groups(self.folder_path)

class PdfInspectionWorker(BaseWorker):
    def __init__(self, folder_path, selected_keys, matched_groups):
        super().__init__()
        self.folder_path = folder_path
        self.selected_keys = selected_keys
        self.matched_groups = matched_groups

    def do_work(self):
        self.log_signal.emit("🔎 선택한 PDF 파일들의 실제 페이지 수 및 상세 정보를 분석 중입니다...")
        if self.is_cancelled(): return None
        
        service = PdfAnalysisService(logger_callback=self.log_signal.emit)
        service.is_cancelled = self.is_cancelled 
        return service.generate_matching_data(
            self.folder_path, 
            self.selected_keys, 
            self.matched_groups
        )

class PdfCombineSaveWorker(BaseWorker):
    def __init__(self, base_data, folder_path):
        super().__init__()
        self.base_data = base_data
        self.folder_path = folder_path

    def do_work(self):
        self.log_signal.emit("🚀 검수 완료된 레시피를 바탕으로 PDF 병합 및 저장을 시작합니다...")
        if self.is_cancelled(): return None
        
        service = PdfOperationService(logger_callback=self.log_signal.emit)
        service.is_cancelled = self.is_cancelled 
        saved_files = service.combine_and_save_all(
            self.base_data,
            self.folder_path,
            progress_callback=lambda p, m: self.progress_signal.emit(p, m)
        )
            
        self.log_signal.emit(f"✅ 성공적으로 {len(saved_files)}개의 파일을 병합 및 저장했습니다.")
        return saved_files
