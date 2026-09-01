from base.base_worker import BaseWorker
from service.pdf_operation_service import PdfOperationService

class PdfSplitWorker(BaseWorker):
    """PDF 파일을 특정 페이지 기준으로 분할하는 워커 클래스입니다."""
    
    def __init__(self, local_path, split_page, out1_name, out2_name, is_drive, target_dir):
        """PdfSplitWorker 초기화.
        
        Args:
            local_path (str): 분할할 로컬 PDF 파일 경로.
            split_page (int): 분할할 기준 페이지 번호.
            out1_name (str): 첫 번째 분할된 파일명.
            out2_name (str): 두 번째 분할된 파일명.
            is_drive (bool): 드라이브 업로드 여부.
            target_dir (str): 저장할 대상 디렉토리.
        """
        super().__init__()
        self.local_path = local_path
        self.split_page = split_page
        self.out1_name = out1_name
        self.out2_name = out2_name
        self.is_drive = is_drive
        self.target_dir = target_dir

    def do_work(self):
        """백그라운드에서 PDF 분할 작업을 수행합니다.
        
        Returns:
            str 또는 None: 성공 시 메시지, 실패 또는 취소 시 None.
        """
        self.log_signal.emit("🚀 PDF 분할 작업을 백그라운드에서 시작합니다...")
        
        # ===========================
        # [서비스 초기화 및 취소 확인]
        # ===========================
        # PDF 조작 서비스를 초기화합니다.
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        # 작업이 취소되었는지 확인합니다.
        if self.is_cancelled(): return None

        # ===========================
        # [PDF 분할 및 저장]
        # ===========================
        # 지정된 경로와 설정에 따라 PDF를 분할하고 저장합니다.
        success, msg = operation_service.split_and_save(
            local_path=self.local_path,
            split_page=self.split_page,
            out1_name=self.out1_name,
            out2_name=self.out2_name,
            is_drive=self.is_drive,
            target_dir=self.target_dir
        )
        
        # ===========================
        # [결과 처리]
        # ===========================
        # 실패한 경우 에러 시그널을 방출합니다.
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg
