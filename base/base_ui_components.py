from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QLineEdit, QVBoxLayout, 
    QHBoxLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor

# ==========================================
# UI 스타일 테마 상수 (중앙 관리)
# ==========================================
COLORS = {
    "primary": "#2563EB",       # Primary Blue
    "primary_hover": "#1D4ED8",
    "secondary": "#64748B",     # Gray
    "secondary_hover": "#475569",
    "danger": "#EF4444",        # Red
    "danger_hover": "#DC2626",
    "success": "#10B981",       # Green
    "warning": "#F59E0B",       # Orange
    "background_card": "#FFFFFF",
    "border": "#E2E8F0",
    "text_main": "#0F172A",
    "text_sub": "#64748B",
    "drop_bg": "#F8FAFC",
    "drop_border": "#CBD5E1"
}


# ==========================================
# 1. 일관된 버튼 프리셋 (Primary, Secondary, Danger)
# ==========================================
class StyledButton(QPushButton):
    """기본 스타일이 적용된 버튼 클래스"""
    def __init__(self, text: str, btn_type: str = "primary", parent=None):
        super().__init__(text, parent)
        self.btn_type = btn_type
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.apply_style()

    def apply_style(self):
        bg = COLORS.get(self.btn_type, COLORS["primary"])
        hover = COLORS.get(f"{self.btn_type}_hover", COLORS["primary_hover"])
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-weight: 600;
                font-size: 13px;
                border-radius: 6px;
                padding: 0 16px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #E2E8F0;
                color: #94A3B8;
            }}
        """)


# ==========================================
# 2. 카드 컨테이너 프리셋 (CardWidget)
# ==========================================
class CardWidget(QFrame):
    """UI 항목들을 깔끔하게 그룹화하는 라운드 카드 컨테이너"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['background_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)


# ==========================================
# 3. 드래그 앤 드롭 전용 구역 (PDF/텍스트 파일용)
# ==========================================
class FileDropZone(QFrame):
    """PDF 및 문서 파일 드래그 앤 드롭 처리 컴포넌트"""
    files_dropped = pyqtSignal(list) # 파일 경로 리스트 전달

    def __init__(self, title: str = "파일을 여기에 드래그하거나 클릭하세요", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(120)
        
        layout = QVBoxLayout(self)
        self.label = QLabel(title)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(f"color: {COLORS['text_sub']}; font-weight: 500; font-size: 13px;")
        layout.addWidget(self.label)
        
        self._set_normal_style()

    def _set_normal_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['drop_bg']};
                border: 2px dashed {COLORS['drop_border']};
                border-radius: 8px;
            }}
        """)

    def _set_active_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #EFF6FF;
                border: 2px dashed {COLORS['primary']};
                border-radius: 8px;
            }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active_style()

    def dragLeaveEvent(self, event):
        self._set_normal_style()

    def dropEvent(self, event: QDropEvent):
        self._set_normal_style()
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.files_dropped.emit(files)


# ==========================================
# 4. 상태 표시 칩/배지 (StatusBadge)
# ==========================================
class StatusBadge(QLabel):
    """작업 상태(대기, 진행 중, 완료, 에러)를 시각적으로 보여주는 배지"""
    def __init__(self, text: str = "대기", state: str = "info", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(24)
        self.set_state(text, state)

    def set_state(self, text: str, state: str):
        self.setText(text)
        
        style_map = {
            "success": (COLORS["success"], "#ECFDF5"),
            "warning": (COLORS["warning"], "#FFFBEB"),
            "error": (COLORS["danger"], "#FEF2F2"),
            "info": (COLORS["primary"], "#EFF6FF")
        }
        
        color, bg = style_map.get(state, style_map["info"])
        
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg};
                border: 1px solid {color};
                border-radius: 12px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)


# ==========================================
# 5. 검색창 입력 필드 (SearchLineEdit)
# ==========================================
class SearchLineEdit(QLineEdit):
    """Drive 파일 및 PDF 목록 검색용 전용 입력창"""
    def __init__(self, placeholder: str = "검색어를 입력하세요...", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(36)
        self.setClearButtonEnabled(True) # 우측 X 버튼 활성화
        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 13px;
                background-color: white;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
            }}
        """)


# ==========================================
# 6. 라벨-입력창 결합형 필드 (LabeledInput)
# ==========================================
class LabeledInput(QWidget):
    """라벨과 입력 위젯을 깔끔하게 묶어주는 래퍼 컴포넌트"""
    def __init__(self, label_text: str, input_widget: QWidget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel(label_text)
        self.label.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: 600; font-size: 12px;")
        
        layout.addWidget(self.label)
        layout.addWidget(input_widget)


from PyQt6.QtGui import QPixmap

def bytes_to_pixmap(image_data: bytes | None) -> QPixmap | None:
    """
    순수 바이트(Bytes) 데이터를 PyQt QPixmap 객체로 변환하는 공통 헬퍼 함수입니다.
    """
    if not image_data:
        return None
        
    pixmap = QPixmap()
    pixmap.loadFromData(image_data)
    return pixmap