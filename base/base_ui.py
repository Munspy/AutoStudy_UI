"""기본 UI(Base UI) 모듈입니다.

이 모듈은 모든 탭이나 UI 컴포넌트들이 공통으로 상속받아야 하는 
`BaseUI` 클래스를 정의합니다. 로깅, 설정 저장/불러오기, 팝업 메시지 출력, 
로딩 상태 제어 등 반복적으로 사용되는 UI 관련 편의 기능들을 제공합니다.

주요 클래스:
    BaseUI: 앱 내 모든 탭 화면의 기반이 되는 공통 QWidget 클래스.

의존성:
    PyQt6.QtWidgets: QWidget, QMessageBox 등 UI 구성요소.
    PyQt6.QtCore: QSettings, pyqtSignal, Qt 등 설정 및 이벤트.
"""

from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import pyqtSignal, QSettings, Qt

class BaseUI(QWidget):
    """모든 UI 탭 화면의 기반이 되는 공통 부모 클래스입니다.
    
    개별 탭에서 자주 쓰이는 설정값(QSettings) 제어, 안내/에러 팝업 띄우기,
    전체 화면 로딩 상태 관리 등의 기능을 통합하여 코드 중복을 줄입니다.

    Attributes:
        log_signal (pyqtSignal): 로그 메시지(str)를 메인 윈도우로 전달하기 위한 시그널.
        task_manager (BaseTaskManager, optional): 앱 전역에서 큐 기반 작업 관리를 수행하는 글로벌 매니저 객체.
        settings (QSettings): 로컬 설정값 저장 및 조회를 위한 객체 ("MyAutoStudy", "DriveSyncPipeline" 사용).

    Inherits:
        QWidget: PyQt의 기본 화면 위젯을 상속.
    """
    # 1. 모든 탭 공통 시그널
    log_signal = pyqtSignal(str)
    
    def __init__(self, task_manager=None, parent=None):
        """BaseUI 인스턴스를 초기화하고 공통 설정 객체를 준비합니다.

        Args:
            task_manager (BaseTaskManager, optional): main에서 주입해주는 글로벌 태스크 매니저. 
                이후 Controller 등으로 넘겨주기 위해 들고 있습니다. Defaults to None.
            parent (QWidget, optional): 상위 부모 위젯. Defaults to None.
        
        Returns:
            None
        """
        # ===========================
        # [초기화 및 공통 의존성 설정]
        # ===========================
        # 부모 클래스 초기화
        super().__init__(parent)

        # main.py에서 단일 gloabl task manger을 생성하여 내려줌. 다시 받아서 controller로 내려주면 됨
        self.task_manager = task_manager
        
        # ===========================
        # [공통 설정 객체 초기화]
        # ===========================
        # 2. 공통 설정 객체 초기화 (모든 탭에서 self.settings 로 접근 가능)
        self.settings = QSettings("MyAutoStudy", "DriveSyncPipeline")

    # --- [공통 메서드 1: 로그 발행] ---
    def emit_log(self, message: str):
        """로그 메시지를 상위(MainUI 등)로 전달하는 시그널을 방출합니다.

        개별 탭의 UI 로직이나 워커에서 발생한 문자열 형태의 로그를 중앙 로그 패널에 
        출력하기 위해 호출됩니다.

        Args:
            message (str): 출력할 로그 내용.

        Returns:
            None
        """
        self.log_signal.emit(message)

    # --- [공통 메서드 2: 설정 쉽게 저장/불러오기] ---
    def load_setting(self, key: str, default_value=""):
        """QSettings를 통해 이전에 저장된 로컬 설정값을 불러옵니다.

        앱 실행 시 마지막으로 입력했던 폴더 경로나 옵션 등을 복원하기 위해 호출됩니다.

        Args:
            key (str): 불러올 설정의 키 이름.
            default_value (Any, optional): 저장된 값이 없을 때 반환할 기본값. Defaults to "".

        Returns:
            Any: 조회된 설정값 또는 기본값.
        """
        return self.settings.value(key, default_value)

    def save_setting(self, key: str, value):
        """QSettings를 통해 로컬에 설정값을 저장합니다.

        사용자가 입력 필드의 값을 변경하거나 체크박스 등을 클릭할 때 
        다음에 앱을 켤 때 유지하기 위해 호출됩니다.

        Args:
            key (str): 저장할 설정의 키 이름.
            value (Any): 저장할 값.

        Returns:
            None
        """
        self.settings.setValue(key, value)

    # --- [공통 메서드 3: 팝업창 띄우기] ---
    def show_info(self, title: str, message: str):
        """정보(안내) 팝업 메시지 박스를 띄웁니다.

        작업이 성공적으로 끝났거나 사용자에게 단순 알림을 제공해야 할 때 호출됩니다.

        Args:
            title (str): 팝업창 상단에 표시될 제목.
            message (str): 팝업창 본문에 표시될 안내 내용.

        Returns:
            None
        """
        QMessageBox.information(self, title, message)

    def show_error(self, title: str, message: str):
        """에러(경고) 팝업 메시지 박스를 띄웁니다.

        사용자의 입력이 잘못되었거나, 시스템 내부에서 치명적인 오류가 발생했을 때 
        상황을 안내하기 위해 호출됩니다.

        Args:
            title (str): 팝업창 상단에 표시될 제목.
            message (str): 팝업창 본문에 표시될 오류 내용.

        Returns:
            None
        """
        QMessageBox.critical(self, title, message)

    # --- [공통 메서드 4: 작업 중 로딩 상태 표시] ---
    def set_loading_state(self, is_loading: bool):
        """현재 탭 화면의 입력 요소들을 차단(로딩 상태)하거나 활성화합니다.

        비동기 작업이 진행되는 동안 사용자가 중복으로 버튼을 클릭하는 것을 방지하고,
        마우스 커서를 모래시계 모양으로 바꿔 현재 작업 중임을 알리기 위해 호출됩니다.

        Args:
            is_loading (bool): True이면 입력을 차단하고 로딩 상태 적용, False이면 원래대로 복구.

        Returns:
            None
        """
        # ===========================
        # [화면 로딩 상태 업데이트]
        # ===========================
        if is_loading:
            # 로딩 중: 화면 입력 차단 및 마우스 커서 대기 상태로 변경
            self.setEnabled(False)
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            # 완료: 화면 입력 활성화 및 마우스 커서 원상복구
            self.setEnabled(True)
            self.unsetCursor()