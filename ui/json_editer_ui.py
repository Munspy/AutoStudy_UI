"""JSON 데이터를 직접 수정하는 UI 모듈.

이 모듈은 시스템의 설정이나 데이터를 담고 있는 JSON 파일을 사용자가 직접
수정할 수 있도록 하는 간단한 다이얼로그 UI를 제공합니다.

Classes:
    JsonEditerUi: JSON 수정용 다이얼로그를 표시하는 UI 클래스.
"""
from PyQt6.QtWidgets import QDialog

class JsonEditerUi(QDialog):
    """JSON 직접 수정을 위한 다이얼로그 클래스.
    
    QDialog를 상속받으며, 전체 애플리케이션의 탭 중 하나로 사용되거나
    단독 다이얼로그로 호출되어 JSON 편집 기능을 제공하는 역할을 합니다.
    
    Attributes:
        task_manager: 백그라운드 작업을 관리하는 태스크 매니저 객체.
    """
    def __init__(self, task_manager=None, parent=None):
        """JsonEditerUi 인스턴스를 초기화합니다.
        
        Args:
            task_manager (optional): 백그라운드 작업을 관리하는 태스크 매니저. 기본값은 None.
            parent (QWidget, optional): 부모 위젯. 기본값은 None.
        """
        super().__init__(parent)
        # 태스크 매니저 저장
        self.task_manager = task_manager
        
        # UI 기본 설정
        self.setWindowTitle("Json 직접 수정")
        self.resize(340, 150)