import os
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (QAbstractSpinBox, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QMessageBox,
                             QScrollArea, QSizePolicy, QStackedWidget,
                             QTextEdit, QVBoxLayout, QWidget)

from core.logger import GlobalLogger
from base.base_ui import BaseUI
from base.base_ui_components import (COLORS, CardWidget, LoadingButton, StyledButton,
                                     StyledCheckBox, StyledDateEdit, HeaderLabel,
                                     StyledListWidget, ask_delete_confirm)
from viewmodel.transcript_merge_split_viewmodel import TranscriptMergeSplitViewModel


class TranscriptMergeSplitUi(BaseUI):

    def __init__(self, parent=None):
        super().__init__(app_name="TranscriptMergeSplit", parent=parent)
        self.viewmodel = TranscriptMergeSplitViewModel()
        
        # 기본 시그널 연결
        self.viewmodel.error_occurred.connect(self.show_error)
        self.viewmodel.search_completed.connect(self._on_search_finished)
        self.viewmodel.files_read_completed.connect(self._on_files_read)
        self.viewmodel.split_save_completed.connect(self._on_split_save_finished)
        self.viewmodel.merge_save_completed.connect(self._on_merge_save_finished)
        
        self.current_text_edits = []
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            TranscriptMergeSplitUi { background-color: #FFFFFF; }
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

    def init_top_panel(self):
        # ===========================
        # [상단 타이틀 구성]
        # ===========================
        header_label = HeaderLabel("✂️ 텍스트 스크립트 분할/병합")
        self.main_layout.addWidget(header_label)

        # ===========================
        # [상단 제어 박스 (컨트롤 프레임)]
        # ===========================
        control_frame = CardWidget()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(10)
        
        self.drive_check = StyledCheckBox("☁️")
        self.drive_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_check.stateChanged.connect(self.toggle_search_mode)
        control_layout.addWidget(self.drive_check)

        # 2-1. 로컬 검색 위젯
        self.local_widget = QWidget()
        local_layout = QHBoxLayout(self.local_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addWidget(QLabel("📂"))
        
        self.folder_input = QLineEdit(str(Path.home() / "Downloads"))
        self.folder_input.setStyleSheet("padding: 6px; border: 1px solid " + COLORS["border_input"] + "; border-radius: 6px; background-color: " + COLORS["background_input"] + ";")
        self.folder_input.setReadOnly(True)
        local_layout.addWidget(self.folder_input)
        
        browse_btn = StyledButton("찾기", "secondary")
        browse_btn.clicked.connect(self.browse_folder)
        local_layout.addWidget(browse_btn)
        control_layout.addWidget(self.local_widget)

        # 2-2. 드라이브 검색 위젯
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
        self.search_btn.clicked.connect(self.populate_file_list)
        control_layout.addWidget(self.search_btn)
        
        self.main_layout.addWidget(control_frame)

    def init_file_selection_area(self):
        # ===========================
        # [파일 리스트업 영역]
        # ===========================
        self.file_list = StyledListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(100)
        self.file_list.itemSelectionChanged.connect(self.on_file_selection_changed)
        self.main_layout.addWidget(self.file_list)

        # ===========================
        # [텍스트 검색 영역]
        # ===========================
        self.search_bar_widget = QWidget()
        search_layout = QHBoxLayout(self.search_bar_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(QLabel("🔍 텍스트 검색:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색어를 입력하세요 (Ctrl+F)")
        self.search_input.setStyleSheet("padding: 6px; border: 1px solid " + COLORS["border_input"] + "; border-radius: 6px; background-color: " + COLORS["background_input"] + ";")
        self.search_input.returnPressed.connect(self.find_text)
        search_layout.addWidget(self.search_input)
        
        find_btn = StyledButton("검색", "secondary")
        find_btn.clicked.connect(self.find_text)
        search_layout.addWidget(find_btn)
        self.main_layout.addWidget(self.search_bar_widget)

        from PyQt6.QtGui import QKeySequence, QShortcut
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search_input.setFocus)

    def init_preview_area(self):
        # ===========================
        # [미리보기 영역]
        # ===========================
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: " + COLORS["background_input"] + "; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_layout.setSpacing(15)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.preview_container)
        self.main_layout.addWidget(self.scroll_area, stretch=1)

    def init_bottom_panel(self):
        # ===========================
        # [하단 상태별 동적 UI 패널]
        # ===========================
        self.bottom_stack = QStackedWidget()
        self.main_layout.addWidget(self.bottom_stack)

        # 상태 0: 대기
        wait_widget = QWidget()
        wait_layout = QHBoxLayout(wait_widget)
        wait_layout.setContentsMargins(5, 5, 5, 5)
        self.status_label = QLabel("대기 중... (파일을 선택하세요)")
        self.status_label.setStyleSheet("font-weight: bold; color: #555555;")
        wait_layout.addWidget(self.status_label)
        wait_layout.addStretch()
        self.bottom_stack.addWidget(wait_widget)

        # 상태 1: 분할 모드
        split_widget = QWidget()
        split_layout = QHBoxLayout(split_widget)
        split_layout.setContentsMargins(5, 5, 5, 5)
        split_icon = QLabel("✂️")
        split_icon.setStyleSheet("font-size: 20px;")
        split_layout.addWidget(split_icon)
        
        split_layout.addWidget(QLabel("저장 파일명 1:"))
        self.split_name_1 = QLineEdit()
        self.split_name_1.setStyleSheet("padding: 8px; border: 1px solid " + COLORS["border_input"] + "; border-radius: 8px; background-color: " + COLORS["background_input"] + "; font-weight: bold; min-width: 140px;")
        split_layout.addWidget(self.split_name_1)
        
        split_layout.addWidget(QLabel("저장 파일명 2:"))
        self.split_name_2 = QLineEdit()
        self.split_name_2.setStyleSheet("padding: 8px; border: 1px solid " + COLORS["border_input"] + "; border-radius: 8px; background-color: " + COLORS["background_input"] + "; font-weight: bold; min-width: 140px;")
        split_layout.addWidget(self.split_name_2)
        
        split_layout.addStretch()
        
        save_split_btn = StyledButton("💾 선택 파일 분할 및 저장", "danger")
        save_split_btn.clicked.connect(self.execute_split_save)
        split_layout.addWidget(save_split_btn)
        self.bottom_stack.addWidget(split_widget)

        # 상태 2: 병합 모드
        merge_widget = QWidget()
        merge_layout = QHBoxLayout(merge_widget)
        merge_layout.setContentsMargins(5, 5, 5, 5)
        merge_icon = QLabel("🔗")
        merge_icon.setStyleSheet("font-size: 20px;")
        merge_layout.addWidget(merge_icon)
        
        merge_layout.addWidget(QLabel("병합 저장 파일명:"))
        self.merge_name_input = QLineEdit()
        self.merge_name_input.setStyleSheet("padding: 8px; border: 1px solid " + COLORS["border_input"] + "; border-radius: 8px; background-color: " + COLORS["background_input"] + "; font-weight: bold; min-width: 250px;")
        merge_layout.addWidget(self.merge_name_input)
        
        merge_layout.addStretch()
        
        save_merge_btn = StyledButton("💾 선택 파일 병합 및 저장", "success")
        save_merge_btn.clicked.connect(self.execute_merge_save)
        merge_layout.addWidget(save_merge_btn)
        self.bottom_stack.addWidget(merge_widget)
        
        self.bottom_stack.setCurrentIndex(0)

        # ===========================
        # [MVVM 선언형 바인딩 적용]
        # ===========================
        self.bind_enabled(self.search_btn, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.file_list, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.bottom_stack, self.viewmodel, 'is_loading', invert=True)

    # --- 실작동 함수들 ---
    def toggle_search_mode(self, state):
        if state == 2:
            self.local_widget.hide()
            self.drive_widget.show()
        else:
            self.local_widget.show()
            self.drive_widget.hide()
        self.file_list.clear()
        self.clear_preview()
        self.bottom_stack.setCurrentIndex(0)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder: self.folder_input.setText(folder)

    def clear_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.current_text_edits.clear()

    def populate_file_list(self):
        self.file_list.clear()
        self.clear_preview()
        self.bottom_stack.setCurrentIndex(0)

        # ===========================
        # [MVVM 선언형 바인딩 적용]
        # ===========================
        self.bind_enabled(self.search_btn, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.file_list, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.bottom_stack, self.viewmodel, 'is_loading', invert=True)
        
        if self.drive_check.isChecked():
            start_date = self.start_date.date().toString("yyyy-MM-dd")
            end_date = self.end_date.date().toString("yyyy-MM-dd")
            
            self.search_btn.start_loading("조회 중")
            GlobalLogger.info(f"☁️ 구글 드라이브 검색 요청: {start_date} ~ {end_date}")
            
            # 워커 실행
            self.viewmodel.execute_drive_search(start_date, end_date)
            return

        folder_path = self.folder_input.text()
        if not os.path.exists(folder_path):
            QMessageBox.warning(self, "오류", "유효하지 않은 로컬 폴더 경로입니다.")
            return

        try:
            files = self.viewmodel.get_local_text_files(folder_path)
            for f in files: self.file_list.addItem(f)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _on_search_finished(self):
        for f in self.viewmodel.files:
            self.file_list.addItem(f)
        GlobalLogger.info(f"☁️ 총 {len(self.viewmodel.files)}개의 드라이브 파일을 성공적으로 불러왔습니다.")
        self.search_btn.stop_loading()

    def on_file_selection_changed(self):
        selected_items = self.file_list.selectedItems()
        count = len(selected_items)
        is_drive = self.drive_check.isChecked()
        
        self.clear_preview()
        folder_path = self.folder_input.text()
        
        if count == 0:
            self.bottom_stack.setCurrentIndex(0)
            return

        # ===========================
        # [MVVM 선언형 바인딩 적용]
        # ===========================
        self.bind_enabled(self.search_btn, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.file_list, self.viewmodel, 'is_loading', invert=True)
        self.bind_enabled(self.bottom_stack, self.viewmodel, 'is_loading', invert=True)
            
        self.status_label.setText("파일을 불러오는 중입니다... 잠시만 기다려주세요.")
        self.bottom_stack.setCurrentIndex(0) 
        
        filenames = [item.text() for item in selected_items]
        
        # 워커 실행
        self.viewmodel.execute_read_files(filenames, folder_path, is_drive)

    def _on_files_read(self):
        filenames = self.viewmodel.loaded_filenames
        contents = self.viewmodel.loaded_contents
        count = len(filenames)
        if count == 1:
            filename = filenames[0]
            content = contents[0]
            self.add_text_edit(filename, content, mode="split")
            n1, n2 = self.viewmodel.recommended_split_names
            self.split_name_1.setText(n1)
            self.split_name_2.setText(n2)
            self.bottom_stack.setCurrentIndex(1)
        else:
            for fname, content in zip(filenames, contents):
                self.add_text_edit(fname, content, mode="merge", min_width=350)
            self.merge_name_input.setText(self.viewmodel.recommended_merged_name)
            self.bottom_stack.setCurrentIndex(2)

    def add_text_edit(self, title, content, mode="split", min_width=None):
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        
        icon = "✂️" if mode == "split" else "🔗"
        title_label = QLabel(f"{icon} {title} (0자)")
        title_label.setStyleSheet("font-weight: bold; color: #37352f; padding-bottom: 5px;")
        vbox.addWidget(title_label)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(content)
        text_edit.setStyleSheet("""
            QTextEdit { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 10px; font-size: 13px; line-height: 1.5; }
            QTextEdit:focus { border: 1px solid #2383E2; }
        """)
        
        if min_width:
            container.setMinimumWidth(min_width)
            
        def update_metrics():
            char_count = len(text_edit.toPlainText().strip())
            title_label.setText(f"{icon} {title} ({char_count:,}자)")
        
        text_edit.textChanged.connect(update_metrics)
        update_metrics()
        
        self.current_text_edits.append(text_edit)
        vbox.addWidget(text_edit)
        self.preview_layout.addWidget(container)

    def find_text(self):
        from PyQt6.QtGui import QTextCursor
        search_text = self.search_input.text()
        if not search_text or not self.current_text_edits: return
            
        found = False
        # 1. 현재 커서 위치들에서 순차적으로 검색 시도
        for text_edit in self.current_text_edits:
            if text_edit.find(search_text):
                found = True
                text_edit.setFocus()
                break
                
        # 2. 끝까지 못 찾았다면, 모든 에디터의 커서를 처음으로 되돌리고 다시 전체 검색
        if not found:
            for text_edit in self.current_text_edits:
                cursor = text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                text_edit.setTextCursor(cursor)
                
                if text_edit.find(search_text):
                    found = True
                    text_edit.setFocus()
                    break
                
        if not found:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "검색 결과", "검색 결과가 없습니다.")

    def execute_split_save(self):
        if not self.file_list.selectedItems(): return
        
        filename = self.file_list.selectedItems()[0].text()
        text_content = self.current_text_edits[0].toPlainText()
        folder_path = self.folder_input.text()
        is_drive = self.drive_check.isChecked()
        
        name1 = self.split_name_1.text()
        name2 = self.split_name_2.text()
        
        if not name1 or not name2:
            QMessageBox.warning(self, "경고", "저장할 파일명을 모두 입력해주세요.")
            return

        GlobalLogger.info(f"[{filename}] 분할 저장을 시작합니다...")
        
        # 워커 실행
        self.viewmodel.execute_split_save(folder_path, filename, text_content, name1, name2, is_drive)

    def _on_split_save_finished(self, msg):
        QMessageBox.information(self, "완료", msg)
        GlobalLogger.info("✅ 분할 작업 및 저장이 완료되었습니다.")
        
        selected_items = self.file_list.selectedItems()
        if selected_items:
            fname = selected_items[0].text()
            is_drive = self.drive_check.isChecked()
            
            paths_or_ids = []
            if is_drive:
                file_id = self.viewmodel.drive_files_cache.get(fname)
                if file_id:
                    paths_or_ids.append(file_id)
            else:
                folder_path = self.folder_input.text()
                paths_or_ids.append(os.path.join(folder_path, fname))
                
            # [리팩토링] 1. UI: 사용자에게 팝업으로 의향만 묻기
            should_delete = ask_delete_confirm(
                parent_widget=self,
                file_paths_or_ids=paths_or_ids,
                is_drive=is_drive
            )

            # [리팩토링] 2. ViewModel: 동의했을 경우 실제 삭제 로직 위임
            if should_delete:
                GlobalLogger.info(f"원본 파일 삭제 요청: {paths_or_ids}")
                self.viewmodel.delete_files(
                    file_paths_or_ids=paths_or_ids,
                    is_drive=is_drive
                )

        self.populate_file_list()

    def execute_merge_save(self):
        if len(self.file_list.selectedItems()) < 2: return
        
        folder_path = self.folder_input.text()
        files_to_merge = [item.text() for item in self.file_list.selectedItems()]
        merged_content = "\n\n".join([edit.toPlainText() for edit in self.current_text_edits])
        is_drive = self.drive_check.isChecked()
        
        custom_name = self.merge_name_input.text()
        if not custom_name:
            QMessageBox.warning(self, "경고", "병합 저장할 파일명을 입력해주세요.")
            return
            
        GlobalLogger.info(f"{files_to_merge} 파일 병합을 시작합니다...")
        
        # 워커 실행
        self.viewmodel.execute_merge_save(folder_path, files_to_merge, merged_content, custom_name, is_drive)
        
    def _on_merge_save_finished(self, res):
        msg, new_filename = res
        QMessageBox.information(self, "완료", msg)
        GlobalLogger.info(f"✅ 병합 작업 및 저장이 완료되었습니다: {new_filename}")
        
        selected_items = self.file_list.selectedItems()
        if selected_items:
            is_drive = self.drive_check.isChecked()
            filenames = [item.text() for item in selected_items]
            paths_or_ids = []
            
            # 삭제할 대상(ID 또는 경로) 추출
            if is_drive:
                for fname in filenames:
                    file_id = self.viewmodel.drive_files_cache.get(fname)
                    if file_id: paths_or_ids.append(file_id)
            else:
                folder_path = self.folder_input.text()
                paths_or_ids = [os.path.join(folder_path, fname) for fname in filenames]
                
            should_delete = ask_delete_confirm(
                parent_widget=self,
                file_paths_or_ids=paths_or_ids,
                is_drive=is_drive
            )
            
            if should_delete:
                GlobalLogger.info(f"원본 파일 삭제 요청: {paths_or_ids}")
                self.viewmodel.delete_files(
                    file_paths_or_ids=paths_or_ids,
                    is_drive=is_drive
                )
            
        self.populate_file_list()

