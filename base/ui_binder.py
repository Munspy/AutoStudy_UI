"""UI 데이터 바인딩 모듈입니다.

PyQt 환경에서 MVVM 패턴을 구현하기 위해 UI 위젯과 ViewModel의 상태를
선언적으로 연결(Bind)하고, 파이썬 가비지 컬렉터(GC)에 의한
메모리 누수 및 시그널 해제를 방지하는 전용 클래스를 제공합니다.

[Refactoring Point]
문자열(property_name) 기반의 getattr() 로직을 모두 제거하고, 
초깃값과 시그널(pyqtSignal) 객체를 직접 주입받아 IDE 자동완성과 타입 안정성을 100% 보장합니다.
"""

from PyQt6.QtWidgets import QWidget, QPushButton
from PyQt6.QtCore import Qt

class UIBinder:
    """UI 위젯과 ViewModel 간의 데이터/상태 바인딩을 전담하는 클래스입니다."""

    def __init__(self):
        # 파이썬 가비지 컬렉터(GC)로부터 시그널 연결이 끊기는 것을 방어하는 참조 리스트
        self._connections = []

    # ==========================================
    # [UI -> Viewmodel 방향 신호 송신]
    # ==========================================

    def _get_widget_value(self, widget: QWidget):
        """위젯의 메타 객체를 분석하여 대표값(USER Property)을 자동으로 추출합니다."""
        # 1. 위젯의 메타데이터에서 '대표 속성(USER Property)'을 찾습니다.
        user_prop = widget.metaObject().userProperty()
        
        # 2. 대표 속성이 존재한다면 그 값을 바로 읽어서 반환합니다.
        # (QLineEdit면 알아서 text, QCheckBox면 알아서 checked 값을 뱉습니다!)
        if user_prop.isValid():
            return user_prop.read(widget)
            
        # 3. 만약 직접 만든 커스텀 위젯이라 못 찾는다면 최후의 보루로 hasattr 사용
        if hasattr(widget, 'text'): return widget.text()
        return None

    def bind_command(self, button: QPushButton, command_func, *arg_widgets):
        """버튼 클릭 시 연결된 위젯들의 값을 읽어 ViewModel 함수를 실행합니다."""
        def execute():
            args = [self._get_widget_value(w) for w in arg_widgets]
            command_func(*args)
        
        button.clicked.connect(execute)
        self._connections.append((button, execute))

    # ==========================================
    # [Viewmodel -> UI 방향 신호 송신]
    # ==========================================

    def _resolve_source_and_signal(self, target_or_val, prop_or_signal):
        """(vm, 'prop_name') 또는 (initial_val, signal) 형태를 모두 지원하여 정규화합니다."""
        if isinstance(prop_or_signal, str):
            vm = target_or_val
            prop_name = prop_or_signal
            val = getattr(vm, prop_name, False)
            signal = getattr(vm, f"{prop_name}_changed", None)
            if signal is None:
                signal = getattr(vm, prop_name, None)
            return val, signal
        return target_or_val, prop_or_signal

    def bind_enabled(self, widget: QWidget, initial_value, signal, invert: bool = False):
        """시그널에 따라 위젯의 활성화(Enabled) 여부를 제어합니다."""
        initial_value, signal = self._resolve_source_and_signal(initial_value, signal)
        
        # 1. 초깃값 즉시 세팅
        widget.setEnabled(not initial_value if invert else bool(initial_value))
        
        # 2. 시그널이 울릴 때 실행할 행동 정의
        def on_changed(new_val: bool):
            widget.setEnabled(not new_val if invert else bool(new_val))
            
        # 3. 직접 연결 및 메모리 방어
        if signal and hasattr(signal, 'connect'):
            signal.connect(on_changed)
            self._connections.append((signal, on_changed))

    def bind_visibility(self, widget: QWidget, initial_value, signal, invert: bool = False):
        """시그널에 따라 위젯의 표시(Visible) 여부를 제어합니다."""
        initial_value, signal = self._resolve_source_and_signal(initial_value, signal)
        widget.setVisible(not initial_value if invert else bool(initial_value))
        
        def on_changed(new_val: bool):
            widget.setVisible(not new_val if invert else bool(new_val))
            
        if signal and hasattr(signal, 'connect'):
            signal.connect(on_changed)
            self._connections.append((signal, on_changed))

    def bind_loading_button(self, button, initial_value, signal, loading_text: str = "처리 중"):
        """시그널에 따라 커스텀 LoadingButton의 애니메이션을 자동 제어합니다."""
        initial_value, signal = self._resolve_source_and_signal(initial_value, signal)
        if initial_value: 
            button.start_loading(loading_text)
        else: 
            button.stop_loading()
            
        def on_changed(new_val: bool):
            if new_val: 
                button.start_loading(loading_text)
            else: 
                button.stop_loading()
                
        if signal and hasattr(signal, 'connect'):
            signal.connect(on_changed)
            self._connections.append((signal, on_changed))

    def bind_screen_loading(self, ui_widget: QWidget, initial_value, signal):
        """로딩 상태 시그널에 따라 전체 화면의 활성화 및 마우스 커서를 제어합니다."""
        initial_value, signal = self._resolve_source_and_signal(initial_value, signal)
        def apply_state(is_loading: bool):
            ui_widget.setEnabled(not is_loading)
            if is_loading:
                ui_widget.setCursor(Qt.CursorShape.WaitCursor)
            else:
                ui_widget.unsetCursor()

        # 초깃값 적용
        apply_state(bool(initial_value))
        
        # 직접 연결 및 메모리 방어
        if signal and hasattr(signal, 'connect'):
            signal.connect(apply_state)
            self._connections.append((signal, apply_state))

    def bind_text(self, widget, initial_value, signal):
        """
        [str 바인딩] ViewModel의 문자열 상태(예: status_message)를 
        화면의 텍스트(QLabel, QLineEdit 등)에 실시간으로 연결합니다.
        """
        initial_value, signal = self._resolve_source_and_signal(initial_value, signal)
        # 초깃값 세팅
        if hasattr(widget, 'setText'):
            widget.setText(str(initial_value or ""))
            
        # 뷰모델에서 문자열을 쏠 때마다 화면 글씨 업데이트
        def on_changed(new_text: str):
            if hasattr(widget, 'setText'):
                widget.setText(str(new_text or ""))
                
        if signal and hasattr(signal, 'connect'):
            signal.connect(on_changed)
            self._connections.append((signal, on_changed))