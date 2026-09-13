
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QAbstractSpinBox, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QListWidgetItem, QMessageBox,
                             QVBoxLayout, QWidget)

from core.logger import GlobalLogger
from base.base_ui import BaseUI
from base.base_ui_components import (COLORS, CardWidget, LoadingButton,
                                     PreviewScrollArea, StyledButton,
                                     StyledCheckBox, StyledDateEdit,
                                     StyledListWidget, ask_delete_confirm,
                                     HeaderLabel)
from viewmodel.pdf_split_viewmodel import PdfSplitViewModel


class PdfSplitUi(BaseUI):
    def __init__(self, parent=None):
        super().__init__(app_name="PdfSplit", parent=parent)
        self.viewmodel = PdfSplitViewModel()
        
        self.viewmodel.file_list_ready.connect(self.on_file_list_ready)
        self.viewmodel.preview_ready.connect(self.on_preview_ready)
        self.viewmodel.page_rendered.connect(self.on_page_rendered)
        self.viewmodel.split_completed.connect(self.on_split_completed)
        self.viewmodel.error_occurred.connect(self.show_error)
        
        self.page_images = []
        
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PdfSplitUi { background-color: #FFFFFF; }
            QWidget {  color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(20)
        
        self.init_top_panel()
        self.init_file_selection_area()
        self.init_preview_area()
        self.init_bottom_panel()

        # 드라이브 업로드를 기본값으로 설정
        self.drive_check.setChecked(True)

    def init_top_panel(self):
        # ===========================
        # [상단 타이틀 구성]
        # ===========================
        header_label = HeaderLabel("✂️ PDF Split (다중 교시 분할)")
        self.main_layout.addWidget(header_label)

        # ===========================
        # [상단 제어 박스 (컨트롤 프레임)]
        # ===========================
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
        local_layout.addWidget(QLabel("📂"))
        
        self.folder_input = QLineEdit(str(Path.home() / "Downloads"))
        self.folder_input.setStyleSheet("""
            QLineEdit { padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; font-weight: normal; }
        """)
        self.folder_input.setReadOnly(True)
        local_layout.addWidget(self.folder_input)
        
        browse_btn = StyledButton("찾기", "secondary")
        browse_btn.clicked.connect(self.browse_folder)
        local_layout.addWidget(browse_btn)

        control_layout.addWidget(self.local_widget)

        self.drive_widget = QWidget()
        drive_layout = QHBoxLayout(self.drive_widget)
        drive_layout.setContentsMargins(0, 0, 0, 0)
        drive_layout.setSpacing(10)
        
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
        
        self.main_layout.addWidget(control_frame)

    def init_file_selection_area(self):
        # ===========================
        # [파일 리스트업 영역]
        # ===========================
        file_selection_layout = QVBoxLayout()
        
        self.file_list = StyledListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(120)
        self.file_list.itemClicked.connect(self.on_file_selected)
        file_selection_layout.addWidget(self.file_list)
        self.main_layout.addLayout(file_selection_layout)

    def init_preview_area(self):
        # ===========================
        # [미리보기 영역]
        # ===========================
        self.scroll_area = PreviewScrollArea()
        self.main_layout.addWidget(self.scroll_area, stretch=1)

    def init_bottom_panel(self):
        # ===========================
        # [하단 저장 영역]
        # ===========================
        bottom_layout = QHBoxLayout()

        bottom_layout.addWidget(QLabel("✂️"))
        self.split_input = QLineEdit()
        self.split_input.setPlaceholderText("번호")
        self.split_input.setStyleSheet("""
            QLineEdit { padding: 10px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; width: 60px; }
        """)
        self.split_input.textChanged.connect(self.update_split_lines)
        bottom_layout.addWidget(self.split_input)
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
        
        save_btn = StyledButton("💾 분할 저장", "save")
        save_btn.clicked.connect(self.start_split)
        
        # ===========================
        # [MVVM 선언형 바인딩 적용]
        # ===========================
        self.bind_enabled(save_btn, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.search_btn, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.file_list, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.split_input, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.save_name_1, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.save_name_2, self.viewmodel, 'is_loading', invert=True)
        bottom_layout.addWidget(save_btn)

        self.main_layout.addLayout(bottom_layout)


    def toggle_search_mode(self, state):
        if state == 2:
            self.local_widget.hide()
            self.drive_widget.show()
        else:
            self.local_widget.show()
            self.drive_widget.hide()
        self.file_list.clear()
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
        self.clear_preview()
        self.viewmodel.start_fetch_file_list(is_drive, target_dir, start_str, end_str)

    def on_file_list_ready(self):
        self.file_list.clear()
        for text in self.viewmodel.file_paths.keys():
            self.file_list.addItem(QListWidgetItem(text))

    def on_file_selected(self, item):
        self.clear_preview()
        filename = item.text()
        is_drive = self.drive_check.isChecked()
        self.viewmodel.select_file(filename, is_drive)
        
        n1, n2 = self.viewmodel.recommended_save_names
        self.save_name_1.setText(n1)
        self.save_name_2.setText(n2)

    def on_preview_ready(self):
        # 미리보기가 준비되면 기존 페이지를 지우고 새로 그려질 준비를 함
        self.clear_preview()

    def on_page_rendered(self, page_idx, img_data):
        img = QImage.fromData(img_data)
        pixmap = QPixmap.fromImage(img)
        self.page_images.append(pixmap)
        
        try:
            text = self.split_input.text().strip()
            is_overlap = text.startswith('!')
            if is_overlap:
                split_point = int(text[1:])
            else:
                split_point = int(text) + 1  # 수직선(분할선) 표시를 위해 타겟을 다음 페이지 앞(즉, 다음 페이지)으로 지정
        except ValueError:
            split_point = -1
            is_overlap = False
            
        border_type = "overlap" if is_overlap else "danger"
        self.scroll_area.add_page(
            pixmap=pixmap,
            border_color=border_type if (page_idx + 1 == split_point) else None,
            top_text=f"{page_idx+1}페이지"
        )

    def update_split_lines(self, text):
        try:
            val = text.strip()
            is_overlap = val.startswith('!')
            if is_overlap:
                split_point = int(val[1:])
            else:
                split_point = int(val) + 1
        except ValueError:
            split_point = -1
            is_overlap = False

        if not self.page_images:
            return

        self.scroll_area.clear()
        for idx, pixmap in enumerate(self.page_images):
            border_type = "overlap" if is_overlap else "danger"
            self.scroll_area.add_page(
                pixmap=pixmap,
                border_color=border_type if (idx + 1 == split_point) else None,
                top_text=f"{idx+1}페이지"
            )

    def clear_preview(self):
        self.page_images = []
        self.scroll_area.clear()

    def start_split(self):
        self.viewmodel.start_split_and_save(
            split_page_text=self.split_input.text(),
            out1_name=self.save_name_1.text(),
            out2_name=self.save_name_2.text(),
            target_dir=self.folder_input.text()
        )

    def on_split_completed(self, msg):
        # 1. 완료 안내 및 UI 초기화
        self.show_info("완료", msg)
        self.save_name_1.clear()
        self.save_name_2.clear()
        self.split_input.clear()
        
        # 2. 원본 삭제 프로세스 진행 (선택된 파일이 있는 경우)
        if self.viewmodel.selected_path_or_id:
            should_delete = ask_delete_confirm(
                parent_widget=self,
                file_paths_or_ids=[self.viewmodel.selected_path_or_id],
                is_drive=self.viewmodel.selected_is_drive
            )
            if should_delete:
                self.viewmodel.delete_selected_file()

        self.start_fetch_files()