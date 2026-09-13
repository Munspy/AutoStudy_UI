"""기본 UI(Base UI) 모듈입니다.

이 모듈은 모든 UI 컴포넌트들이 공통으로 상속받아야 하는 `BaseUI` 클래스를
정의합니다. 로깅, 설정 저장/불러오기, 팝업 메시지 출력 기능을 제공하며,
내부적으로 `UIBinder`를 통해 MVVM 데이터 바인딩 기능을 지원합니다.
"""

from PyQt6.QtWidgets import QMessageBox, QWidget
from PyQt6.QtCore import QSettings
from core.logger import GlobalLogger
from core.config import Config
from base.ui_binder import UIBinder 

class BaseUI(QWidget):
    """모든 UI 탭 화면의 기반이 되는 공통 부모 클래스입니다."""
    
    def __init__(self, app_name="DefaultApp", parent=None):
        """BaseUI 인스턴스를 초기화하고 공통 설정 객체와 바인더를 준비합니다."""
        super().__init__(parent)
        
        # 1. 탭별 고유 설정 보관함
        self.settings = QSettings(Config.PROJECT_NAME, app_name)
        
        # 2. 바인딩 도우미 장착 (이제 모든 자식 탭에서 self.binder 로 접근 가능)
        self.binder = UIBinder()

    # --- [공통 메서드: 설정 제어] ---
    def load_setting(self, key: str, default_value=""):
        """저장된 로컬 설정값을 불러옵니다."""
        return self.settings.value(key, default_value)

    def save_setting(self, key: str, value):
        """로컬에 설정값을 저장합니다."""
        self.settings.setValue(key, value)

    # --- [공통 메서드: 팝업 제어] ---
    def show_info(self, title: str, message: str):
        """정보(안내) 팝업 메시지 박스를 띄웁니다."""
        QMessageBox.information(self, title, message)

    def show_error(self, title: str, message: str):
        """에러(경고) 팝업 메시지 박스를 띄웁니다."""
        QMessageBox.critical(self, title, message)

    # --- [공통 메서드: 바인딩 헬퍼] ---
    def bind_enabled(self, widget, *args, **kwargs):
        return self.binder.bind_enabled(widget, *args, **kwargs)

    def bind_loading_button(self, button, *args, **kwargs):
        return self.binder.bind_loading_button(button, *args, **kwargs)

    def bind_visibility(self, widget, *args, **kwargs):
        return self.binder.bind_visibility(widget, *args, **kwargs)

    def bind_screen_loading(self, *args, **kwargs):
        return self.binder.bind_screen_loading(*args, **kwargs)

    def bind_text(self, widget, *args, **kwargs):
        return self.binder.bind_text(widget, *args, **kwargs)