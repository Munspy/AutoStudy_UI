from PyQt6.QtWidgets import (
    QFrame, QWidget, QPushButton, QLabel, QLineEdit, QVBoxLayout, 
    QHBoxLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor

# ==========================================
# UI 스타일 테마 상수 (중앙 관리)
# ==========================================
COLORS = {
    "primary": "#118ab2",       # 연한 파랑 (기본)
    "secondary": "#073b4c",     # 진한 파랑 (특수/선택)
    "danger": "#ef476f",        # 빨간색 (중요/취소)
    "success": "#06d6a0",       # 초록색 (진행)
    "warning": "#ffd166",       # 노란색 (기타)
    "background_card": "#F4F5F7", # 카드 위젯 내부 연회색
    "border": "#E2E8F0",          # 범용 회색 테두리
    "text_main": "#0F172A",       # 진한 텍스트
    "text_sub": "#64748B",        # 서브 텍스트
    "drop_bg": "#F8FAFC",         # 드래그 구역 배경
    "drop_border": "#CBD5E1"      # 드래그 구역 테두리
}


# ==========================================
# 1. 일관된 버튼 프리셋 (Primary, Secondary, Danger)
# ==========================================

from PyQt6.QtCore import QTimer
class LoadingButton(QPushButton):
    def __init__(self, text: str, btn_type: str = "primary", parent=None):
        super().__init__(text, parent)
        self.original_text = text
        self.btn_type = btn_type
        self.is_loading = False
        self.dots = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._animate_dots)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.apply_style()

    def apply_style(self):
        from PyQt6.QtGui import QColor
        bg = COLORS.get(self.btn_type, COLORS["primary"])
        c = QColor(bg)
        hover = c.darker(115).name()
        disabled = c.lighter(130).name()
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg}; color: white; font-weight: 600;
                font-size: 13px; border-radius: 6px; padding: 0 16px; border: none;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: {disabled}; color: #F8FAFC; }}
        """)

    def start_loading(self, text="로딩 중"):
        self.is_loading = True
        self.setEnabled(False)
        self.loading_base_text = text
        self.dots = 0
        self.setText(f"{self.loading_base_text}.")
        self.timer.start(500)

    def stop_loading(self):
        self.is_loading = False
        self.timer.stop()
        self.setText(self.original_text)
        self.setEnabled(True)

    def _animate_dots(self):
        self.dots = (self.dots + 1) % 4
        self.setText(f"{self.loading_base_text}" + "." * self.dots)

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
        c = QColor(bg)
        hover = c.darker(115).name()
        disabled = c.lighter(130).name()
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg}; color: white; font-weight: 600;
                font-size: 13px; border-radius: 6px; padding: 0 16px; border: none;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: {disabled}; color: #F8FAFC; }}
        """)


# ==========================================
# 2. 카드 컨테이너 프리셋 (CardWidget)
# ==========================================
class CardWidget(QFrame):
    """UI 항목들을 깔끔하게 그룹화하는 라운드 카드 컨테이너"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {COLORS['background_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)


# ==========================================
# 4. 상태 표시 칩/배지 (StatusBadge)
# ==========================================
class StatusBadge(QLabel):
    """작업 상태를 시각적으로 보여주는 배지"""
    def __init__(self, text: str = "완료", state: str = "success", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(24)
        self.set_state(text, state)

    def set_state(self, text: str, state: str):
        self.setText(text)
        bg = COLORS.get(state, COLORS["primary"])
        c = QColor(bg)
        text_color = c.darker(110).name()
        bg_color = c.lighter(170).name()
        
        self.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {bg_color};
                border: 1px solid {text_color};
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

# 여기는 다음에 꼭 고치고 싶은데,
# 어차피 바이트를 받아와서 pixmap으로 바꿔봣자 바로 쓰는 것도 아니고,
# 결국은 아래처럼 썸네일 프레임으로 만들어야 하기 때문에 그냥 한번에 두 작업을 진행시키는 것이 맞다고 생각함
# pdf를 byte로 만들어 주는 거는 utils 였나 아무튼 아래서 해주는데
# 그 byte -> thumbnail을 굳이 두 파트로 쪼갤 필요가 있나 그냥 한번에 하면 됐지
# 정리하자면 byte -> Qframe -> Thumbnail을 두 함수가 아니라 한 함수로 하자고ㅇㅇ
def bytes_to_pixmap(image_data: bytes | None) -> QPixmap | None:
    """
    순수 바이트(Bytes) 데이터를 PyQt QPixmap 객체로 변환하는 공통 헬퍼 함수입니다.
    """
    if not image_data:
        return None
        
    pixmap = QPixmap()
    pixmap.loadFromData(image_data)
    return pixmap

def create_pdf_thumbnail_frame(pixmap, label_text, width, height, is_empty=False):
    
    frame = QFrame()
    frame.setFixedSize(width, height)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    if pixmap:
        label.setPixmap(pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    elif label_text:
        label.setText(label_text)
        label.setStyleSheet("color: #787774; font-size: 11px;")
        
    layout.addWidget(label)
    
    if is_empty:
        frame.setStyleSheet("QFrame { background-color: #F8F9FA; border: 2px dashed #D1D1CE; border-radius: 4px; }")
    else:
        frame.setStyleSheet("QFrame { background-color: white; border: 1px solid #EAEAEA; border-radius: 4px; }")
        
    return frame

# ==========================================
# 7. 리스트 및 테이블 뷰 (StyledListWidget, StyledTableWidget)
# ==========================================
from PyQt6.QtWidgets import QListWidget, QTableWidget, QCheckBox, QComboBox, QDateEdit, QScrollArea, QScrollArea

class StyledListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(f"""
            QListWidget {{
                background-color: #FFFFFF; border: 1px solid {COLORS['border']};
                border-radius: 8px; font-size: 13px; alternate-background-color: #FAFAFA; outline: none;
            }}
            QListWidget::item {{ padding: 8px; border-bottom: 1px solid #F4F4F4; color: {COLORS['text_main']}; }}
            QListWidget::item:selected {{ background-color: #E7F3F8; color: {COLORS['text_main']}; border: none; }}
            QListWidget::item:hover {{ background-color: #F8F9FA; }}
        """)

class StyledTableWidget(QTableWidget):
    def __init__(self, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: #FFFFFF; border: 1px solid {COLORS['border']};
                border-radius: 8px; gridline-color: #F4F4F4; font-size: 13px;
                alternate-background-color: #FAFAFA; outline: none;
            }}
            QHeaderView::section {{
                background-color: #FFFFFF; border: none; border-bottom: 2px solid {COLORS['border']};
                padding: 10px 5px; font-weight: bold; color: {COLORS['text_sub']};
            }}
            QTableWidget::item {{ padding: 5px; border-bottom: 1px solid #F4F4F4; color: {COLORS['text_main']}; }}
            QTableWidget::item:selected {{ background-color: #E7F3F8; color: {COLORS['text_main']}; border: none; }}
        """)


# ==========================================
# 8. 입력 폼 (StyledCheckBox, StyledComboBox, StyledDateEdit)
# ==========================================
class StyledCheckBox(QCheckBox):
    def __init__(self, text="", theme="primary", parent=None):
        super().__init__(text, parent)
        self.theme = theme
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_style()

    def apply_style(self):
        color = COLORS.get(self.theme, COLORS['primary'])
        self.setStyleSheet(f"""
            QCheckBox {{ font-weight: bold; font-size: 14px; color: {COLORS['text_main']}; margin-left: 5px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid {COLORS['border']}; background-color: #FFFFFF; }}
            QCheckBox::indicator:checked {{ background-color: {color}; border: 1px solid {color}; }}
        """)

class StyledComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QComboBox {{
                padding: 6px 10px; border: 1px solid {COLORS['border']}; border-radius: 6px; 
                background-color: #FFFFFF; font-weight: normal; color: {COLORS['text_main']};
            }}
            QComboBox:disabled {{ background-color: #EFEFEF; color: #A0A0A0; }}
            QComboBox::drop-down {{ border: none; padding-right: 10px; }}
            QComboBox::down-arrow {{ width: 10px; height: 10px; }}
        """)

class StyledDateEdit(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QDateEdit {{
                padding: 6px; border: 1px solid {COLORS['border']}; border-radius: 6px; 
                background-color: #FFFFFF; min-width: 80px; font-weight: normal; color: {COLORS['text_main']};
            }}
            QDateEdit:disabled {{ background-color: #EFEFEF; color: #A0A0A0; }}
            QDateEdit::drop-down {{ border: none; width: 20px; }}
        """)

# ==========================================
# 9. 공통 PDF 프리뷰 영역 (PreviewScrollArea)
# ==========================================
class PreviewScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"""
            QScrollArea {{ border: 1px solid {COLORS['border']}; border-radius: 8px; background-color: #FAFAFA; }}
        """)
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #FAFAFA;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.container_layout.setContentsMargins(10, 10, 10, 10)
        self.container_layout.setSpacing(15)
        self.setWidget(self.container)
        
    def clear(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def add_page(self, pixmap, border_color=None, top_text=None, bottom_text=None):
        from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout
        page_frame = QFrame()
        layout = QVBoxLayout(page_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        border_hex = COLORS.get(border_color, "#d0d0d0") if border_color else "#d0d0d0"
        page_frame.setStyleSheet(f"background-color: white; border: 1px solid {border_hex}; border-radius: 4px;")
        
        if top_text:
            tl = QLabel(top_text)
            tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl.setStyleSheet("color: #333333; font-size: 13px; font-weight: bold; padding: 5px;")
            layout.addWidget(tl)
            
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap:
            img_lbl.setPixmap(pixmap)
        layout.addWidget(img_lbl)
        
        if bottom_text:
            bl = QLabel(bottom_text)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.setStyleSheet("color: #787774; font-size: 11px; padding: 5px;")
            layout.addWidget(bl)
            
        self.container_layout.addWidget(page_frame)
