from PyQt6.QtWidgets import (
    QFrame, QWidget, QPushButton, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, 
    QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# ==========================================
# UI 스타일 테마 상수 (중앙 관리)
# ==========================================
COLORS = {
    "primary": "#2383E2",           # 커스텀 지정 가능
    "secondary": "#073b4c",         # 진한 파랑 (특수/선택) 
    "danger": "#FF3D7F",            # 빨간색 (중요/취소)     # 중요
    "success": "#5E8C6A",           # 초록색 (진행)         # 저장
    "warning": "#FBB829",           # 노란색 (기타)         # 빠르게
    "background_card": "#F4F5F7",   # 카드 위젯 내부 연회색
    "border": "#E2E8F0",            # 범용 회색 테두리
    "text_main": "#0F172A",         # 진한 텍스트
    "text_sub": "#64748B",          # 서브 텍스트
    "drop_bg": "#F8FAFC",           # 드래그 구역 배경
    "drop_border": "#CBD5E1",        # 드래그 구역 테두리

    "important": "#D70044",
    "whisper": "#BE80FF",
    "sync": "#2383E2",            # 커스텀 지정 가능
    "fast": "#FF3D7F",            # 빨간색 (중요/취소)     # 중요
    "rapid": "#F7BC05",           # 노란색 (기타)         # 빠르게
    "save": "#5E8C6A",
    "trivia": "#83AF9B",
    "check": "#8196B2"
}



# COLORS = {
#     "primary": {"base": "#2383E2", "hover": "#1A6FB0", "disabled": "#A5C9F3"}, # 커스텀 지정 가능
#     "secondary": "#073b4c",     # 진한 파랑 (특수/선택)
#     "danger": "#ef476f",        # 빨간색 (중요/취소)
#     "success": "#06d6a0",       # 초록색 (진행)
#     "warning": "#ffd166",       # 노란색 (기타)
#     "background_card": "#F4F5F7", # 카드 위젯 내부 연회색
#     "border": "#E2E8F0",          # 범용 회색 테두리
#     "text_main": "#0F172A",       # 진한 텍스트
#     "text_sub": "#64748B",        # 서브 텍스트
#     "drop_bg": "#F8FAFC",         # 드래그 구역 배경
#     "drop_border": "#CBD5E1"      # 드래그 구역 테두리
# }


# ==========================================
# 1. 일관된 버튼 프리셋 (Primary, Secondary, Danger)
# ==========================================

from PyQt6.QtCore import QTimer

def _get_base_color(color_val):
    if isinstance(color_val, dict):
        return color_val.get("base", "#000000")
    elif isinstance(color_val, tuple):
        return color_val[0]
    return color_val

def _calculate_ui_colors(base_hex):
    from PyQt6.QtGui import QColor
    c = QColor(base_hex)
    h, s, v, a = c.getHsv()
    
    # Hover: 명도는 20% 낮추고(어둡게), 채도는 5% 올려서 묵직하고 선명하게 (사용자 예시: 1A6FB0)
    hover_v = max(0, int(v * 0.8))
    hover_s = min(255, int(s * 1.05))
    hover_color = QColor.fromHsv(h, hover_s, hover_v)
    
    # Disabled: 흰색을 섞어 명도를 높이고(60% 밝게), 채도를 65% 빼서 파스텔톤으로 (사용자 예시: A5C9F3)
    disabled_s = int(s * 0.35)
    disabled_v = min(255, int(v + (255 - v) * 0.6))
    disabled_color = QColor.fromHsv(h, disabled_s, disabled_v)
    
    return hover_color.name(), disabled_color.name()

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
        color_val = COLORS.get(self.btn_type, COLORS["primary"])
        bg = _get_base_color(color_val)
        hover, disabled = _calculate_ui_colors(bg)
        
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
        color_val = COLORS.get(self.btn_type, COLORS["primary"])
        bg = _get_base_color(color_val)
        hover, disabled = _calculate_ui_colors(bg)
        
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
        bg = _get_base_color(COLORS.get(state, COLORS["primary"]))
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
        color = _get_base_color(COLORS.get(self.theme, COLORS['primary']))
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
                background-color: #FFFFFF; min-width: 60px; font-weight: normal; color: {COLORS['text_main']};
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
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        

        if border_color == "danger":
            red_line = QFrame()
            red_line.setFrameShape(QFrame.Shape.VLine)
            red_line.setStyleSheet("color: #E03E3E; border: 2px solid #E03E3E; border-radius: 2px;")
            self.container_layout.addWidget(red_line)
            
        page_frame.setStyleSheet("background-color: white; border: 1px solid #d0d0d0; border-radius: 4px;")

        
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
