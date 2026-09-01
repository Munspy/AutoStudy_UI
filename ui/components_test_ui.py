from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, 
                             QSpacerItem, QSizePolicy, QGroupBox, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QTimer
from base.base_ui import BaseUI
from base.base_ui_components import (StyledButton, LoadingButton, CardWidget, StatusBadge, 
                                     SearchLineEdit, StyledCheckBox, StyledComboBox, COLORS)

class ComponentsTestUi(BaseUI):
    def __init__(self, task_manager=None):
        super().__init__(task_manager)
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #FFFFFF;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. 스크롤 영역 생성
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: #FFFFFF; }")
        
        # 2. 스크롤 내부에 들어갈 컨테이너 위젯
        container = QWidget()
        container.setStyleSheet("background-color: #FFFFFF;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(20)
        
        title = QLabel("🎨 UI 컴포넌트 플레이그라운드 (Tab 9)")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0F172A;")
        container_layout.addWidget(title)
        
        desc = QLabel("base_ui_components.py에 정의된 모든 색상과 커스텀 컴포넌트들을 테스트할 수 있습니다.")
        desc.setStyleSheet("color: #64748B; font-size: 14px;")
        container_layout.addWidget(desc)
        
        # COLORS에 정의된 모든 키 가져오기
        all_colors = list(COLORS.keys())
        
        # 버튼 섹션 카드
        btn_card = CardWidget()
        btn_layout = QVBoxLayout(btn_card)
        
        btn_title = QLabel(f"🔘 버튼 (모든 {len(all_colors)}가지 색상)")
        btn_title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        btn_layout.addWidget(btn_title)
        
        grid = QGridLayout()
        grid.setSpacing(15)
        
        # 헤더
        grid.addWidget(QLabel("<b>타입 (Color Key)</b>"), 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("<b>StyledButton</b>"), 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("<b>LoadingButton</b>"), 0, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        
        for i, color in enumerate(all_colors):
            row = i + 1
            # 타입 라벨
            type_lbl = QLabel(color)
            type_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(type_lbl, row, 0)
            
            # StyledButton
            s_btn = StyledButton(f"{color} 버튼", color)
            s_btn.clicked.connect(lambda checked, c=color: self.log_signal.emit(f"[{c}] StyledButton 클릭됨!"))
            grid.addWidget(s_btn, row, 1)
            
            # LoadingButton
            l_btn = LoadingButton(f"{color} 로딩", color)
            l_btn.clicked.connect(lambda checked, btn=l_btn, c=color: self.simulate_loading(btn, c))
            
            
            grid.addWidget(l_btn, row, 2)
            
        btn_layout.addLayout(grid)
        container_layout.addWidget(btn_card)
        
        # 기타 컴포넌트 섹션 카드
        other_card = CardWidget()
        other_layout = QVBoxLayout(other_card)
        
        other_title = QLabel("기타 컴포넌트 (StatusBadge, CheckBox, Input, ComboBox)")
        other_title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        other_layout.addWidget(other_title)
        
        o_grid = QGridLayout()
        o_grid.setSpacing(15)
        
        # 배지
        o_grid.addWidget(QLabel("Status Badge (모든 색상):"), 0, 0, 1, 2)
        
        # 배지가 많을 수 있으니 Grid로 배치 (한 줄에 6개씩)
        badge_grid = QGridLayout()
        col = 0
        r = 0
        for color in all_colors:
            badge_grid.addWidget(StatusBadge(color, color), r, col)
            col += 1
            if col > 5:
                col = 0
                r += 1
                
        o_grid.addLayout(badge_grid, 1, 0, 1, 2)
        
        # 체크박스
        o_grid.addWidget(QLabel("Styled CheckBox:"), 2, 0)
        chk = StyledCheckBox("체크박스 테스트")
        chk.stateChanged.connect(lambda state: self.log_signal.emit(f"체크박스 상태: {state}"))
        o_grid.addWidget(chk, 2, 1)
        
        # 콤보박스
        o_grid.addWidget(QLabel("Styled ComboBox:"), 3, 0)
        combo = StyledComboBox()
        combo.addItems(["옵션 A", "옵션 B", "옵션 C"])
        combo.currentTextChanged.connect(lambda text: self.log_signal.emit(f"콤보박스 선택: {text}"))
        o_grid.addWidget(combo, 3, 1)
        
        # 검색창
        o_grid.addWidget(QLabel("Search Input:"), 4, 0)
        search = SearchLineEdit()
        search.setPlaceholderText("검색어를 입력해보세요...")
        search.textChanged.connect(lambda text: self.log_signal.emit(f"입력 중: {text}"))
        o_grid.addWidget(search, 4, 1)
        
        other_layout.addLayout(o_grid)
        container_layout.addWidget(other_card)
        
        container_layout.addStretch()
        
        # 3. 스크롤 영역에 컨테이너 부착 및 메인 레이아웃에 추가
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def simulate_loading(self, btn: LoadingButton, color: str):
        btn.start_loading("처리 중")
        self.log_signal.emit(f"[{color}] 로딩 시작... (3초 후 완료)")
        
        # 3초 후 완료 처리
        QTimer.singleShot(3000, lambda: self.finish_loading(btn, color))
        
    def finish_loading(self, btn: LoadingButton, color: str):
        btn.stop_loading()
        self.log_signal.emit(f"[{color}] 로딩 완료!")

