from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import pyqtSignal, QSettings, Qt

class BaseTab(QWidget):
    # 1. 모든 탭 공통 시그널
    log_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 2. 공통 설정 객체 초기화 (모든 탭에서 self.settings 로 접근 가능)
        self.settings = QSettings("MyAutoStudy", "DriveSyncPipeline")

    # --- [공통 메서드 1: 로그 발행] ---
    def emit_log(self, message: str):
        self.log_signal.emit(message)

    # --- [공통 메서드 2: 설정 쉽게 저장/불러오기] ---
    def load_setting(self, key: str, default_value=""):
        return self.settings.value(key, default_value)

    def save_setting(self, key: str, value):
        self.settings.setValue(key, value)

    # --- [공통 메서드 3: 팝업창 띄우기] ---
    def show_info(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def show_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    # --- [공통 메서드 4: 작업 중 로딩 상태 표시] ---
    def set_loading_state(self, is_loading: bool):
        if is_loading:
            # 로딩 중: 화면 입력 차단 및 마우스 커서 대기 상태로 변경
            self.setEnabled(False)
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            # 완료: 화면 입력 활성화 및 마우스 커서 원상복구
            self.setEnabled(True)
            self.unsetCursor()