# ui/pdf_split_ui.py
import sys
import re
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QFileDialog, QScrollArea, QFrame, 
                             QCheckBox, QListWidget, QListWidgetItem,
                             QDateEdit, QAbstractSpinBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QDate

# 새로 작성한 컨트롤러 임포트
import controller.pdf_split_controller as backend

# UI 렌더링 헬퍼 임포트 (추가)
from utils.pdf_core_util import get_page_image_bytes
from base.base_ui_components import bytes_to_pixmap

class Tab4PdfSplit(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # 선 그리기 객체를 UI에서 직접 관리
        self.split_lines = {} 
        self.controller = backend.PdfSplitController(self)
        self.init_ui()

    # ... (init_ui 내부 코드는 기존과 동일하되, 시그널 연결부만 아래와 같이 수정) ...
    # self.file_list.itemChanged.connect(self.on_item_changed)
    # self.split_input.textChanged.connect(self.update_split_lines)
    # self.drive_check.stateChanged.connect(self.toggle_search_mode) 
    
    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab4PdfSplit { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # 1. 상단 타이틀
        header_label = QLabel("✂️ PDF Split (단일 교시 분할)")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # 2. 제어 박스 (검색 영역)
        control_frame = QFrame()
        control_frame.setObjectName("ControlBox")
        control_frame.setStyleSheet("""
            #ControlBox { background-color: #F4F5F7; border-radius: 12px; border: 1px solid #EAEAEA; }
            QLabel { font-weight: bold; color: #37352f; }
        """)
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(10)

        self.drive_check = QCheckBox("☁️")
        self.drive_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_check.setStyleSheet("""
            QCheckBox { font-size: 18px; margin-right: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #D1D1CE; background-color: #FFFFFF; }
            QCheckBox::indicator:checked { background-color: #2383E2; border: 1px solid #2383E2; }
        """)
        self.drive_check.stateChanged.connect(self.toggle_search_mode)
        control_layout.addWidget(self.drive_check)

        # 2-1. 로컬 검색 위젯
        self.local_widget = QWidget()
        local_layout = QHBoxLayout(self.local_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addWidget(QLabel("📂 대상 폴더:"))
        
        self.folder_input = QLineEdit(str(Path.home() / "Downloads"))
        self.folder_input.setStyleSheet("padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; font-weight: normal;")
        self.folder_input.setReadOnly(True)
        local_layout.addWidget(self.folder_input)
        
        browse_btn = QPushButton("폴더 찾기")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold; } QPushButton:hover { background-color: #F8F9FA; color: #111111; }")
        browse_btn.clicked.connect(self.browse_folder)
        local_layout.addWidget(browse_btn)
        
        control_layout.addWidget(self.local_widget)

        # 2-2. 드라이브 날짜 검색 위젯
        self.drive_widget = QWidget()
        drive_layout = QHBoxLayout(self.drive_widget)
        drive_layout.setContentsMargins(0, 0, 0, 0)
        drive_layout.setSpacing(10)
        
        drive_layout.addWidget(QLabel("📅 날짜 범위:"))
        
        today = QDate.currentDate()
        date_style = """
            QDateEdit {
                padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; 
                background-color: #FFFFFF; min-width: 80px; font-weight: normal;
            }
        """
        
        self.start_date = QDateEdit(today)
        self.start_date.setDisplayFormat("MM-dd")
        self.start_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.start_date.setCalendarPopup(True)
        self.start_date.setStyleSheet(date_style)
        
        self.end_date = QDateEdit(today)
        self.end_date.setDisplayFormat("MM-dd")
        self.end_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.end_date.setCalendarPopup(True)
        self.end_date.setStyleSheet(date_style)

        drive_layout.addWidget(self.start_date)
        drive_layout.addWidget(QLabel("~"))
        drive_layout.addWidget(self.end_date)
        
        control_layout.addWidget(self.drive_widget)
        self.drive_widget.hide()

        control_layout.addStretch()
        
        search_btn = QPushButton("파일 조회")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.setStyleSheet("QPushButton { background-color: #2383E2; color: white; font-weight: bold; border-radius: 6px; padding: 6px 15px; border: none; } QPushButton:hover { background-color: #1A6FB0; }")
        search_btn.clicked.connect(self.controller.populate_file_list)
        control_layout.addWidget(search_btn)
        
        layout.addWidget(control_frame)

        # 3. 파일 리스트업 영역
        file_selection_layout = QVBoxLayout()
        file_selection_layout.setSpacing(10)
        
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 8px; font-size: 13px; alternate-background-color: #FAFAFA; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F4; color: #37352f; }
            QListWidget::item:selected { background-color: #E7F3F8; color: #37352f; border: none; }
            QListWidget::item:hover { background-color: #F8F9FA; }
        """)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(90)
        
        # [수정] 컨트롤러가 아닌 UI 자체의 on_item_changed 로 연결
        self.file_list.itemChanged.connect(self.on_item_changed)
        file_selection_layout.addWidget(self.file_list)
        layout.addLayout(file_selection_layout)

        # 4. 썸네일 미리보기 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumWidth(100)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: #FFFFFF; }
            QScrollBar:horizontal { height: 8px; background: #F1F5F9; border-radius: 4px; }
            QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 4px; min-width: 20px; }
            QScrollBar::handle:horizontal:hover { background: #94A3B8; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; background: none; }
        """)
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(20, 20, 20, 20)
        self.preview_layout.setSpacing(20)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.preview_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 5. 하단 분할 입력 및 저장 영역
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        
        split_icon = QLabel("✂️")
        split_icon.setStyleSheet("font-size: 20px;")
        bottom_layout.addWidget(split_icon)
        
        self.split_input = QLineEdit()
        self.split_input.setPlaceholderText("분할 기준 페이지 (예: 3)")
        self.split_input.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; max-width: 160px; font-weight: normal;")
        # [수정] 컨트롤러가 아닌 UI 자체의 update_split_lines 로 연결
        self.split_input.textChanged.connect(self.update_split_lines)
        bottom_layout.addWidget(self.split_input)
        
        bottom_layout.addStretch() 
        
        bottom_layout.addWidget(QLabel("저장 파일명 1:"))
        self.save_name_1 = QLineEdit()
        self.save_name_1.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; min-width: 120px;")
        bottom_layout.addWidget(self.save_name_1)
        
        bottom_layout.addWidget(QLabel("저장 파일명 2:"))
        self.save_name_2 = QLineEdit()
        self.save_name_2.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; min-width: 120px;")
        bottom_layout.addWidget(self.save_name_2)
        
        save_btn = QPushButton("💾 선택 파일 분할 및 저장")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("QPushButton { background-color: #E03E3E; color: white; font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #C93434; }")
        save_btn.clicked.connect(self.controller.split_and_save)
        
        bottom_layout.addWidget(save_btn)
        layout.addLayout(bottom_layout)

    # ====================================================
    # 이전된 UI 렌더링 함수들
    # ====================================================

    def toggle_search_mode(self, state):
        if state == 2:
            self.local_widget.hide()
            self.drive_widget.show()
        else:
            self.local_widget.show()
            self.drive_widget.hide()
            
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.clear_preview()
        self.file_list.blockSignals(False)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder: self.folder_input.setText(folder)

    def on_item_changed(self, item):
        """파일 리스트 체크박스 변경 시 단일 선택으로 제한하고 썸네일을 로드합니다."""
        self.file_list.blockSignals(True)
        if item.checkState() == Qt.CheckState.Checked:
            for i in range(self.file_list.count()):
                other_item = self.file_list.item(i)
                if other_item != item:
                    other_item.setCheckState(Qt.CheckState.Unchecked)
            self.load_preview(item)
        else:
            self.clear_preview()
        self.file_list.blockSignals(False)

    def clear_preview(self):
        """미리보기 영역 초기화"""
        self.split_lines.clear()
        
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self.save_name_1.clear()
        self.save_name_2.clear()

    def load_preview(self, item):
        """선택된 PDF 파일의 썸네일을 렌더링합니다."""
        self.clear_preview()
        is_drive = self.drive_check.isChecked()
        path_or_id = self.controller.file_paths.get(item.text())
        
        if not path_or_id:
            return

        self.log_signal.emit(f"🔄 [{item.text()}] 미리보기를 로딩합니다...")

        # 1. 컨트롤러에 로컬 파일 경로와 전체 페이지 수를 준비해달라고 요청
        local_path, total_pages = self.controller.prepare_file_for_preview(path_or_id, is_drive)
        if not local_path or total_pages == 0:
            return

        # 2. UI 렌더링
        for i in range(total_pages):
            image_bytes = get_page_image_bytes(local_path, i, zoom=0.2)
            
            page_frame = QFrame()
            page_frame.setFixedHeight(100)
            page_frame.setStyleSheet("background-color: white; border: 1px solid #EAEAEA; border-radius: 4px;")
            v_layout = QVBoxLayout(page_frame)
            v_layout.setContentsMargins(5, 5, 5, 5)

            if image_bytes:
                pixmap = bytes_to_pixmap(image_bytes)
                if pixmap:
                    scaled = pixmap.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
                    img_label = QLabel()
                    img_label.setPixmap(scaled)
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    v_layout.addWidget(img_label)

            lbl = QLabel(f"Page {i+1}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #37352f; font-size: 10px; font-weight: bold;")
            v_layout.addWidget(lbl)

            self.preview_layout.addWidget(page_frame)

            if i < total_pages - 1:
                red_line = QFrame()
                red_line.setFrameShape(QFrame.Shape.VLine)
                red_line.setStyleSheet("color: #E03E3E; border: 2px solid #E03E3E; border-radius: 2px;")
                red_line.hide()
                self.preview_layout.addWidget(red_line)
                self.split_lines[i + 1] = red_line 

        # 파일명 자동 분할 처리
        original_name = item.text().replace("📄 ", "").replace("☁️ ", "").replace(".pdf", "")
        match = re.search(r'^(\d{4})_(\d)(\d)(.*)$', original_name)
        
        if match:
            date_part = match.group(1)
            p1 = match.group(2)
            p2 = match.group(3)
            rest = match.group(4)
            self.save_name_1.setText(f"{date_part}_{p1}{rest}.pdf")
            self.save_name_2.setText(f"{date_part}_{p2}{rest}.pdf")
        else:
            self.save_name_1.setText(f"{original_name}_1.pdf")
            self.save_name_2.setText(f"{original_name}_2.pdf")

        self.log_signal.emit("✅ 렌더링 완료")
        self.update_split_lines(self.split_input.text())

    def update_split_lines(self, text):
        try:
            split_point = int(text.strip())
        except ValueError:
            split_point = -1

        for page_num, line_widget in self.split_lines.items():
            if page_num == split_point:
                line_widget.show()
            else:
                line_widget.hide()