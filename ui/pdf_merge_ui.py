import sys
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QFileDialog, QScrollArea, QFrame, 
                             QCheckBox, QListWidget, QListWidgetItem,
                             QDateEdit, QAbstractSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal, QDate

import controller.pdf_merge_controller as backend

class Tab3PdfMerge(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
        self.controller = backend.PdfMergeController(self)
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab3PdfMerge { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # 1. 상단 타이틀
        header_label = QLabel("🔗 PDF Merge (단순 병합)")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
        """)
        layout.addWidget(header_label)

        # 2. 제어 박스
        control_frame = QFrame()
        control_frame.setObjectName("ControlBox")
        control_frame.setStyleSheet("""
            #ControlBox { 
                background-color: #F4F5F7; 
                border-radius: 12px; 
                border: 1px solid #EAEAEA; 
            }
            QLabel { font-weight: bold; color: #37352f; }
        """)
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(10)
        
        # 대상 폴더 왼쪽 구름 체크박스
        self.drive_check = QCheckBox("☁️")
        self.drive_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_check.setStyleSheet("""
            QCheckBox { font-size: 18px; margin-right: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #D1D1CE; background-color: #FFFFFF; }
            QCheckBox::indicator:checked { background-color: #2383E2; border: 1px solid #2383E2; }
        """)
        self.drive_check.stateChanged.connect(self.toggle_search_mode)
        control_layout.addWidget(self.drive_check)

        # 2-1. 로컬 폴더 검색 위젯
        self.local_widget = QWidget()
        local_layout = QHBoxLayout(self.local_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addWidget(QLabel("📂 대상 폴더:"))
        
        self.folder_input = QLineEdit(str(Path.home() / "Downloads"))
        self.folder_input.setStyleSheet("""
            QLineEdit { padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; font-weight: normal; }
        """)
        self.folder_input.setReadOnly(True)
        local_layout.addWidget(self.folder_input)
        
        browse_btn = QPushButton("폴더 변경")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold; }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
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
        search_btn.setStyleSheet("""
            QPushButton { background-color: #2383E2; color: white; font-weight: bold; border-radius: 6px; padding: 6px 15px; border: none; }
            QPushButton:hover { background-color: #1A6FB0; }
        """)
        search_btn.clicked.connect(self.controller.populate_file_list)
        control_layout.addWidget(search_btn)
        
        layout.addWidget(control_frame)

        # 3. 파일 리스트업 및 선택 영역
        file_selection_layout = QVBoxLayout()
        file_selection_layout.setSpacing(10)
        
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.select_all_cb = QCheckBox("전체 선택")
        self.select_all_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_cb.setStyleSheet("""
            QCheckBox { font-weight: bold; font-size: 14px; color: #37352f; margin-left: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #D1D1CE; background-color: #FFFFFF; }
            QCheckBox::indicator:checked { background-color: #2383E2; border: 1px solid #2383E2; }
        """)
        self.select_all_cb.clicked.connect(self.toggle_all_items)
        mid_bar_layout.addWidget(self.select_all_cb)
        
        # --- 스크립트본 선택 버튼 추가 ---
        self.select_scripted_btn = QPushButton("스크립트본 선택")
        self.select_scripted_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_scripted_btn.setStyleSheet("""
            QPushButton { background-color: #F4F5F7; border: 1px solid #D1D1CE; border-radius: 4px; padding: 2px 10px; font-weight: bold; font-size: 13px; color: #37352f; margin-left: 10px; }
            QPushButton:hover { background-color: #EAEAEA; }
        """)
        self.select_scripted_btn.clicked.connect(self.select_scripted_items)
        mid_bar_layout.addWidget(self.select_scripted_btn)
        
        mid_bar_layout.addStretch()
        
        file_selection_layout.addLayout(mid_bar_layout)
        
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF; border: 1px solid #EAEAEA;
                border-radius: 8px; font-size: 13px; alternate-background-color: #FAFAFA; outline: none;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F4; color: #37352f; }
            QListWidget::item:selected { background-color: #E7F3F8; color: #37352f; border: none; }
            QListWidget::item:hover { background-color: #F8F9FA; }
        """)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(120)
        self.file_list.itemChanged.connect(self.on_item_changed)
        
        file_selection_layout.addWidget(self.file_list)
        layout.addLayout(file_selection_layout)

        # 4. 썸네일 미리보기 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: #FFFFFF; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(20, 20, 20, 20)
        self.preview_layout.setSpacing(20)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.preview_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 5. 하단 저장 영역
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        bottom_layout.addWidget(QLabel("저장 파일명:"))
        self.save_name_input = QLineEdit("") 
        self.save_name_input.setStyleSheet("""
            QLineEdit { padding: 10px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; width: 180px; }
        """)
        
        save_btn = QPushButton("💾 선택 파일 병합 및 저장")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2EA043; color: white; 
                font-weight: bold; font-size: 14px; padding: 12px 24px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #238636; }
        """)
        save_btn.clicked.connect(self.controller.merge_files)
        
        bottom_layout.addWidget(self.save_name_input)
        bottom_layout.addWidget(save_btn)
        layout.addLayout(bottom_layout)

    # --- UI 전용 헬퍼 함수 ---
    
    def select_scripted_items(self):
        total = self.file_list.count()
        if total == 0: return

        self.file_list.blockSignals(True)
        for row in range(total):
            item = self.file_list.item(row)
            if '_scripted.pdf' in item.text().lower():
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.file_list.blockSignals(False)
        
        self.update_select_all_ui()
        self.controller.update_preview()

    def toggle_all_items(self):
        total = self.file_list.count()
        if total == 0: return

        checked_count = sum(1 for row in range(total) 
                            if self.file_list.item(row).checkState() == Qt.CheckState.Checked)
        
        new_state = Qt.CheckState.Unchecked if checked_count == total else Qt.CheckState.Checked
        
        self.file_list.blockSignals(True)
        for row in range(total):
            item = self.file_list.item(row)
            if item:
                item.setCheckState(new_state)
        self.file_list.blockSignals(False)
        
        self.update_select_all_ui()
        self.controller.update_preview()

    def on_item_changed(self, item):
        self.update_select_all_ui()
        self.controller.update_preview()

    def update_select_all_ui(self):
        total = self.file_list.count()
        if total == 0: return
        checked_count = sum(1 for row in range(total) 
                            if self.file_list.item(row).checkState() == Qt.CheckState.Checked)
        
        self.select_all_cb.blockSignals(True)
        if checked_count == total:
            self.select_all_cb.setChecked(True)
            self.select_all_cb.setText("전체 선택 해제")
        else:
            self.select_all_cb.setChecked(False)
            self.select_all_cb.setText("전체 선택")
        self.select_all_cb.blockSignals(False)

    def toggle_search_mode(self, state):
        if state == 2:
            self.local_widget.hide()
            self.drive_widget.show()
        else:
            self.local_widget.show()
            self.drive_widget.hide()
            
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.controller.file_paths.clear()
        self.file_list.blockSignals(False)
        
        self.update_select_all_ui()
        self.controller.update_preview()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder: 
            self.folder_input.setText(folder)