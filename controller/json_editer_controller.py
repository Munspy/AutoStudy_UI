"""JSON 편집기 탭의 백엔드 로직을 처리하는 컨트롤러 모듈입니다.

UI(Tab9JsonEditer)와 연동되어 JSON 데이터 편집 관련 작업을 제어합니다.
"""
from base.base_controller import BaseController

class JsonEditerController(BaseController):
    """JSON 에디터 작업을 관리하는 컨트롤러 클래스입니다.

    BaseController를 상속받아 필요한 백그라운드 작업을 실행하고,
    JSON 데이터 편집과 관련된 UI와의 인터페이스 역할을 수행합니다.
    """
    
    # ===========================
    # [초기화 및 설정]
    # ===========================
    def __init__(self, task_manager=None):
        """JsonEditerController 초기화.
        
        Args:
            task_manager (BaseTaskManager, optional): 전체 태스크를 관리하는 매니저 인스턴스.
        """
        # 상위 BaseController의 초기화 메서드를 호출하여 기본 설정 진행
        super().__init__(task_manager)
