"""
PDF 병합(Merge) 관련 워커 모듈입니다.

이 모듈은 단일 PDF 병합 작업을 백그라운드에서 처리하는 
`PdfMergeWorker` 클래스를 제공합니다. 구글 드라이브와 로컬 경로로
병합된 PDF를 저장하는 기능과 연동됩니다.
"""
from base.base_worker import BaseWorker
from service.pdf_operation_service import PdfOperationService

class PdfMergeWorker(BaseWorker):
    """여러 PDF 파일을 하나로 병합하는 작업을 처리하는 워커 클래스.
    
    Attributes:
        task (dict): 병합에 필요한 설정 데이터(파일 목록, 저장 이름, 경로 등).
    """
    def __init__(self, task_data):
        """PdfMergeWorker 초기화.
        
        Args:
            task_data (dict): 병합 작업 관련 데이터 딕셔너리.
        """
        super().__init__()
        self.task = task_data

    def do_work(self):
        """백그라운드에서 PDF 병합을 실행합니다.
        
        Returns:
            str or None: 성공 시 결과 메시지. 실패 시 None.
        """
        self.log_signal.emit("🚀 PDF 병합 작업을 백그라운드에서 시작합니다...")
        
        # ===========================
        # [서비스 초기화 및 작업 데이터 설정]
        # ===========================
        # PDF 조작 서비스를 초기화합니다.
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        # 작업 데이터를 변수에 할당합니다.
        paths_to_merge = self.task['paths_to_merge']
        save_name = self.task['save_name']
        is_drive = self.task['is_drive']
        target_dir = self.task['target_dir']
        save_local = self.task.get('save_local', False)
        
        # 출력 파일명에 '.pdf' 확장자가 없으면 추가합니다.
        if not save_name.endswith('.pdf'): save_name += '.pdf'
        
        # ===========================
        # [병합 작업 수행]
        # ===========================
        # 작업이 취소되었는지 확인합니다.
        if self.is_cancelled(): return None

        # 지정된 파일들을 병합하고 저장합니다.
        success, msg = operation_service.merge_and_save(
            paths_to_merge=paths_to_merge,
            save_name=save_name,
            is_drive=is_drive,
            target_dir=target_dir,
            save_local=save_local
        )
        
        # ===========================
        # [결과 반환]
        # ===========================
        # 병합에 실패한 경우 에러 시그널을 방출합니다.
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg
