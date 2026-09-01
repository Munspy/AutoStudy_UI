"""
PDF 결합(Combine) 관련 워커 모듈입니다.

이 모듈은 PDF 파일 그룹 탐색, 상세 정보 검수, 그리고 실제 병합 및 저장을 
수행하는 워커 클래스들을 포함합니다. 백그라운드 스레드에서 무거운 PDF
처리 작업을 실행하여 메인 UI 스레드의 응답성을 유지합니다.
"""
from base.base_worker import BaseWorker
from service.pdf_analysis_service import PdfAnalysisService
from service.pdf_operation_service import PdfOperationService

class PdfMatchListWorker(BaseWorker):
    """지정된 폴더에서 병합할 PDF 파일 그룹을 탐색하는 워커 클래스.
    
    Attributes:
        folder_path (str): 대상 폴더 경로.
    """
    def __init__(self, folder_path):
        """PdfMatchListWorker 초기화.
        
        Args:
            folder_path (str): 탐색할 폴더의 경로.
        """
        super().__init__()
        self.folder_path = folder_path

    def do_work(self):
        """PDF 파일 그룹 탐색 작업을 실행합니다.
        
        Returns:
            dict or None: 병합 가능한 PDF 파일 그룹 매칭 딕셔너리. 취소 시 None.
        """
        self.log_signal.emit("🔍 지정된 폴더에서 병합할 PDF 파일 그룹을 탐색합니다...")
        
        # ===========================
        # [PDF 탐색 작업 실행]
        # ===========================
        # 작업 취소 여부를 확인합니다.
        if self.is_cancelled(): return None
        # 분석 서비스를 통해 매칭된 파일 그룹을 반환합니다.
        return PdfAnalysisService(logger_callback=self.log_signal.emit).get_matched_file_groups(self.folder_path)

class PdfInspectionWorker(BaseWorker):
    """선택한 PDF 파일들의 상세 정보(페이지 수 등)를 분석하는 워커 클래스.
    
    Attributes:
        folder_path (str): 대상 폴더 경로.
        selected_keys (list): 분석할 키 리스트.
        matched_groups (dict): 매칭된 파일 그룹.
    """
    def __init__(self, folder_path, selected_keys, matched_groups):
        """PdfInspectionWorker 초기화.
        
        Args:
            folder_path (str): 대상 폴더 경로.
            selected_keys (list): 분석할 그룹의 식별자 목록.
            matched_groups (dict): 파일 매칭 결과 딕셔너리.
        """
        super().__init__()
        self.folder_path = folder_path
        self.selected_keys = selected_keys
        self.matched_groups = matched_groups

    def do_work(self):
        """PDF 검수 작업을 실행합니다.
        
        Returns:
            list or None: 병합 매칭 데이터 리스트. 취소 시 None.
        """
        self.log_signal.emit("🔎 선택한 PDF 파일들의 실제 페이지 수 및 상세 정보를 분석 중입니다...")
        
        # ===========================
        # [PDF 검수 작업 실행]
        # ===========================
        # 작업 취소 여부를 확인합니다.
        if self.is_cancelled(): return None
        
        # 분석 서비스를 초기화하고 취소 콜백을 등록합니다.
        service = PdfAnalysisService(logger_callback=self.log_signal.emit)
        service.is_cancelled = self.is_cancelled 
        
        # 매칭 데이터를 생성하여 반환합니다.
        return service.generate_matching_data(
            self.folder_path, 
            self.selected_keys, 
            self.matched_groups
        )

class PdfCombineSaveWorker(BaseWorker):
    """검수 완료된 레시피를 바탕으로 PDF를 병합 및 저장하는 워커 클래스.
    
    Attributes:
        base_data (list): 검수된 병합 레시피 데이터.
        folder_path (str): 저장할 대상 폴더 경로.
    """
    def __init__(self, base_data, folder_path):
        """PdfCombineSaveWorker 초기화.
        
        Args:
            base_data (list): PDF 병합 지침이 담긴 데이터 리스트.
            folder_path (str): 결과물을 저장할 폴더 경로.
        """
        super().__init__()
        self.base_data = base_data
        self.folder_path = folder_path

    def do_work(self):
        """실제 PDF 병합 및 저장 작업을 실행합니다.
        
        Returns:
            list or None: 생성된 파일 경로 목록. 취소 시 None.
        """
        self.log_signal.emit("🚀 검수 완료된 레시피를 바탕으로 PDF 병합 및 저장을 시작합니다...")
        
        # ===========================
        # [PDF 병합 및 저장 실행]
        # ===========================
        # 작업 취소 여부를 확인합니다.
        if self.is_cancelled(): return None
        
        # 조작 서비스를 초기화하고 취소 콜백을 등록합니다.
        service = PdfAnalysisService(logger_callback=self.log_signal.emit)
        service.is_cancelled = self.is_cancelled 
        
        # 설정된 레시피와 폴더 경로를 사용하여 모든 파일을 병합하고 저장합니다.
        saved_files = service.execute_merge(
            self.base_data,
            self.folder_path
        )
            
        # ===========================
        # [결과 반환]
        # ===========================
        # 성공 메시지를 출력하고 저장된 파일 목록을 반환합니다.
        self.log_signal.emit(f"✅ 성공적으로 {len(saved_files)}개의 파일을 병합 및 저장했습니다.")
        return saved_files
