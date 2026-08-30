import sys

from PyQt6.QtWidgets import QTableWidget, QListWidget, QListWidgetItem, QCheckBox, QDateEdit, QComboBox, QHeaderView

from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QFileDialog, QScrollArea, QFrame, 
                             QCheckBox, QComboBox, QListWidget, QListWidgetItem,
                             QDateEdit, QAbstractSpinBox, QMessageBox)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QImage, QPixmap

from base.base_ui_components import LoadingButton, StyledButton, CardWidget, StyledListWidget, StyledCheckBox, StyledDateEdit, PreviewScrollArea
import controller.pdf_split_controller as backend

class PdfSplitUi(QWidget):
    def __init__(self, task_manager=None):
        super().__init__()
        self.task_manager = task_manager
        self.controller = backend.PdfSplitController(task_manager=self.task_manager)
        
        self.controller.file_list_ready.connect(self.on_file_list_ready)
        self.controller.preview_ready.connect(self.on_preview_ready)
        self.controller.page_rendered.connect(self.on_page_rendered)
        self.controller.split_completed.connect(self.on_split_completed)
        self.controller.error_signal.connect(lambda t, msg: self.show_error(msg))
        
        self.file_paths = {}
        self.local_path = None
        self.total_pages = 0
        self.page_images = []
        
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PdfSplitUi { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        header_label = QLabel("✂️ PDF Split (다중 교시 분할)")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
        """)
        layout.addWidget(header_label)

        control_frame = CardWidget()
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(10)
        
        self.drive_check = StyledCheckBox("☁️")
        self.drive_check.stateChanged.connect(self.toggle_search_mode)
        control_layout.addWidget(self.drive_check)

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
        
        browse_btn = StyledButton("폴더 변경", "secondary")
        browse_btn.clicked.connect(self.browse_folder)
        local_layout.addWidget(browse_btn)

        control_layout.addWidget(self.local_widget)

        self.drive_widget = QWidget()
        drive_layout = QHBoxLayout(self.drive_widget)
        drive_layout.setContentsMargins(0, 0, 0, 0)
        drive_layout.setSpacing(10)
        
        drive_layout.addWidget(QLabel("📅 날짜 범위:"))
        
        today = QDate.currentDate()
        self.start_date = StyledDateEdit(today)
        self.start_date.setDisplayFormat("MM-dd")
        self.start_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.start_date.setCalendarPopup(True)
        
        self.end_date = StyledDateEdit(today)
        self.end_date.setDisplayFormat("MM-dd")
        self.end_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.end_date.setCalendarPopup(True)

        drive_layout.addWidget(self.start_date)
        drive_layout.addWidget(QLabel("~"))
        drive_layout.addWidget(self.end_date)
        
        control_layout.addWidget(self.drive_widget)
        self.drive_widget.hide()

        control_layout.addStretch()
        
        self.search_btn = LoadingButton("파일 조회", "primary")
        self.search_btn.clicked.connect(self.start_fetch_files)
        control_layout.addWidget(self.search_btn)
        
        layout.addWidget(control_frame)

        file_selection_layout = QVBoxLayout()
        file_selection_layout.setSpacing(10)
        
        file_selection_layout.addWidget(QLabel("📝 분할할 대상 파일 선택:"))
        
        self.file_list = StyledListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(120)
        self.file_list.itemClicked.connect(self.on_file_selected)
        file_selection_layout.addWidget(self.file_list)
        layout.addLayout(file_selection_layout)

        split_input_layout = QHBoxLayout()
        split_input_layout.addWidget(QLabel("✂️ 분할할 기준 페이지 번호:"))
        self.split_input = QLineEdit()
        self.split_input.setPlaceholderText("예: 3")
        self.split_input.setStyleSheet("""
            QLineEdit { padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; width: 100px; font-weight: normal; }
        """)
        self.split_input.textChanged.connect(self.update_split_lines)
        split_input_layout.addWidget(self.split_input)
        
        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet("color: #888888; font-weight: bold;")
        split_input_layout.addWidget(self.preview_label)
        
        split_input_layout.addStretch()
        layout.addLayout(split_input_layout)

        self.scroll_area = PreviewScrollArea()
        layout.addWidget(self.scroll_area, stretch=1)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        bottom_layout.addWidget(QLabel("저장 파일명 1:"))
        self.save_name_1 = QLineEdit("")
        self.save_name_1.setStyleSheet("""
            QLineEdit { padding: 10px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; width: 120px; }
        """)
        bottom_layout.addWidget(self.save_name_1)
        
        bottom_layout.addWidget(QLabel("저장 파일명 2:"))
        self.save_name_2 = QLineEdit("")
        self.save_name_2.setStyleSheet("""
            QLineEdit { padding: 10px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; width: 120px; }
        """)
        bottom_layout.addWidget(self.save_name_2)
        
        save_btn = StyledButton("💾 선택 파일 분할 및 저장", "danger")
        save_btn.clicked.connect(self.start_split)
        
        bottom_layout.addWidget(save_btn)
        layout.addLayout(bottom_layout)

    def toggle_search_mode(self, state):
        if state == 2:
            self.local_widget.hide()
            self.drive_widget.show()
        else:
            self.local_widget.show()
            self.drive_widget.hide()
        self.file_list.clear()
        self.file_paths.clear()
        self.clear_preview()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder: self.folder_input.setText(folder)

    def start_fetch_files(self):
        is_drive = self.drive_check.isChecked()
        target_dir = self.folder_input.text()
        start_str = self.start_date.date().toString("MMdd")
        end_str = self.end_date.date().toString("MMdd")
        self.file_list.clear()
        self.file_paths.clear()
        self.clear_preview()
        self.controller.start_fetch_file_list(is_drive, target_dir, start_str, end_str)

    def on_file_list_ready(self, file_paths):
        self.file_paths = file_paths
        for text in self.file_paths.keys():
            self.file_list.addItem(QListWidgetItem(text))

    def on_file_selected(self, item):
        self.clear_preview()
        filename = item.text()
        path_or_id = self.file_paths.get(filename)
        is_drive = self.drive_check.isChecked()
        if not path_or_id: return
        self.preview_label.setText("미리보기 준비 중...")
        self.controller.start_prepare_preview(path_or_id, is_drive)
        
        # 파일명 추천 로직
        import os, re
        base, ext = os.path.splitext(filename)
        m = re.search(r'(\d+)_([1-9])([1-9])(.*)', base)
        m2 = re.search(r'(\d+)_([1-9]),([1-9])(.*)', base)
        
        if m:
            n1 = f"{m.group(1)}_{m.group(2)}{m.group(4)}{ext}"
            n2 = f"{m.group(1)}_{m.group(3)}{m.group(4)}{ext}"
        elif m2:
            n1 = f"{m2.group(1)}_{m2.group(2)}{m2.group(4)}{ext}"
            n2 = f"{m2.group(1)}_{m2.group(3)}{m2.group(4)}{ext}"
        else:
            n1 = f"{base}_Part 1{ext}"
            n2 = f"{base}_Part 2{ext}"
            
        self.save_name_1.setText(n1)
        self.save_name_2.setText(n2)

    def on_preview_ready(self, result):
        self.local_path = result['local_path']
        self.total_pages = result['total_pages']
        self.preview_label.setText(f"총 {self.total_pages} 페이지")
        
        # UI 프리징 방지를 위해 백그라운드 워커에서 렌더링 시작
        self.controller.start_render_pages(self.local_path, self.total_pages)

    def on_page_rendered(self, page_idx, img_data):
        img = QImage.fromData(img_data)
        pixmap = QPixmap.fromImage(img)
        self.page_images.append(pixmap)
        
        try:
            split_point = int(self.split_input.text().strip())
        except ValueError:
            split_point = -1
            
        self.scroll_area.add_page(
            pixmap=pixmap,
            border_color="danger" if (page_idx + 1 == split_point) else None,
            top_text=f"{page_idx+1}페이지"
        )

    def update_split_lines(self, text):
        try:
            split_point = int(text.strip())
        except ValueError:
            split_point = -1

        if not hasattr(self, 'page_images'):
            return

        self.scroll_area.clear()
        for idx, pixmap in enumerate(self.page_images):
            self.scroll_area.add_page(
                pixmap=pixmap,
                border_color="danger" if (idx + 1 == split_point) else None,
                top_text=f"{idx+1}페이지"
            )

    def clear_preview(self):
        self.local_path = None
        self.total_pages = 0
        self.page_images = []
        self.preview_label.setText("")
        self.scroll_area.clear()

    def start_split(self):
        self.controller.start_split_and_save(
            local_path=self.local_path,
            total_pages=self.total_pages,
            split_page_text=self.split_input.text(),
            out1=self.save_name_1.text(),
            out2=self.save_name_2.text(),
            is_drive=self.drive_check.isChecked(),
            target_dir=self.folder_input.text()
        )

    def on_split_completed(self, msg):
        QMessageBox.information(self, "완료", msg)
        self.save_name_1.clear()
        self.save_name_2.clear()
        self.split_input.clear()
        
    def show_error(self, msg):
        QMessageBox.critical(self, "오류", msg)
