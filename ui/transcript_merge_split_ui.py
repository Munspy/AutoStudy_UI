import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QFileDialog, QScrollArea, QFrame, 
                             QListWidget, QDateEdit, QAbstractSpinBox, QStackedWidget,
                             QSizePolicy, QTextEdit, QMessageBox, QCheckBox, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QKeySequence, QTextCursor, QShortcut

from controller.transcript_merge_split_controller import TranscriptController

class Tab5TranscriptMergeSplit(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.controller = TranscriptController(self)
        self.current_text_edits = []
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab5TranscriptMergeSplit { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # 1. 상단 타이틀
        header_label = QLabel("✂️ 텍스트 스크립트 분할/병합")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # 2. 제어 박스
        control_frame = QFrame()
        control_frame.setObjectName("ControlBox")
        control_frame.setStyleSheet("""
            #ControlBox { background-color: #F4F5F7; border-radius: 12px; border: 1px solid #EAEAEA; }
            QLabel { font-weight: bold; color: #37352f; }
        """)
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        
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
        self.folder_input.setStyleSheet("padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF;")
        self.folder_input.setReadOnly(True)
        local_layout.addWidget(self.folder_input)
        
        browse_btn = QPushButton("폴더 찾기")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold; } QPushButton:hover { background-color: #F8F9FA; color: #111111; }")
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
        
        self.search_btn = QPushButton("파일 조회")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setStyleSheet("QPushButton { background-color: #2383E2; color: white; font-weight: bold; border-radius: 6px; padding: 6px 15px; border: none; } QPushButton:hover { background-color: #1A6FB0; }")
        self.search_btn.clicked.connect(self.populate_file_list)
        control_layout.addWidget(self.search_btn)
        
        layout.addWidget(control_frame)

        # 3. 파일 리스트업 영역
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setStyleSheet("""
            QListWidget { background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 8px; font-size: 13px; alternate-background-color: #FAFAFA; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F4; color: #37352f; }
            QListWidget::item:selected { background-color: #E7F3F8; color: #37352f; border: none; }
            QListWidget::item:hover { background-color: #F8F9FA; }
        """)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(100)
        self.file_list.itemSelectionChanged.connect(self.on_file_selection_changed)
        layout.addWidget(self.file_list)

        # 4. 검색바
        self.search_bar_widget = QWidget()
        search_layout = QHBoxLayout(self.search_bar_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(QLabel("🔍 텍스트 검색:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("검색어를 입력하세요 (Ctrl+F)")
        self.search_input.setStyleSheet("padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF;")
        self.search_input.returnPressed.connect(self.find_text)
        search_layout.addWidget(self.search_input)
        
        find_btn = QPushButton("검색")
        find_btn.setStyleSheet("QPushButton { background-color: #F4F5F7; border: 1px solid #D1D1CE; border-radius: 4px; padding: 6px 12px; font-weight: bold; color: #37352f; } QPushButton:hover { background-color: #EAEAEA; }")
        find_btn.clicked.connect(self.find_text)
        search_layout.addWidget(find_btn)
        layout.addWidget(self.search_bar_widget)
        
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search_input.setFocus)

        # 5. 미리보기 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: #FFFFFF; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_layout.setSpacing(15)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.preview_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 6. 하단 상태별 동적 UI 패널 (QStackedWidget)
        self.bottom_stack = QStackedWidget()
        layout.addWidget(self.bottom_stack)

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
        self.split_name_1.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; min-width: 140px;")
        split_layout.addWidget(self.split_name_1)
        
        split_layout.addWidget(QLabel("저장 파일명 2:"))
        self.split_name_2 = QLineEdit()
        self.split_name_2.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; min-width: 140px;")
        split_layout.addWidget(self.split_name_2)
        
        split_layout.addStretch()
        
        save_split_btn = QPushButton("💾 선택 파일 분할 및 저장")
        save_split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_split_btn.setStyleSheet("QPushButton { background-color: #E03E3E; color: white; font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #C93434; }")
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
        self.merge_name_input.setStyleSheet("padding: 8px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; min-width: 250px;")
        merge_layout.addWidget(self.merge_name_input)
        
        merge_layout.addStretch()
        
        save_merge_btn = QPushButton("💾 선택 파일 병합 및 저장")
        save_merge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_merge_btn.setStyleSheet("QPushButton { background-color: #2EA043; color: white; font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #238636; }")
        save_merge_btn.clicked.connect(self.execute_merge_save)
        merge_layout.addWidget(save_merge_btn)
        self.bottom_stack.addWidget(merge_widget)
        
        self.bottom_stack.setCurrentIndex(0)

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
        
        if self.drive_check.isChecked():
            start_date = self.start_date.date().toString("yyyy-MM-dd")
            end_date = self.end_date.date().toString("yyyy-MM-dd")
            
            self.search_btn.setText("조회 중...")
            self.search_btn.setEnabled(False)
            self.log_signal.emit(f"☁️ 구글 드라이브 검색 요청: {start_date} ~ {end_date}")
            QApplication.processEvents() # UI 새로고침(먹통 방지)
            
            try:
                files = self.controller.get_drive_text_files(start_date, end_date)
                for f in files: self.file_list.addItem(f)
                self.log_signal.emit(f"☁️ 총 {len(files)}개의 드라이브 파일을 성공적으로 불러왔습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"드라이브 검색 실패: {str(e)}")
            finally:
                self.search_btn.setText("파일 조회")
                self.search_btn.setEnabled(True)
            return

        folder_path = self.folder_input.text()
        if not os.path.exists(folder_path):
            QMessageBox.warning(self, "오류", "유효하지 않은 로컬 폴더 경로입니다.")
            return

        try:
            files = self.controller.get_local_text_files(folder_path)
            for f in files: self.file_list.addItem(f)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def on_file_selection_changed(self):
        selected_items = self.file_list.selectedItems()
        count = len(selected_items)
        is_drive = self.drive_check.isChecked()
        
        self.clear_preview()
        folder_path = self.folder_input.text()
        
        if count == 0:
            self.bottom_stack.setCurrentIndex(0)
            return
            
        try:
            # 상태 메시지 변경 및 UI 즉시 적용
            self.status_label.setText("파일을 불러오는 중입니다... 잠시만 기다려주세요.")
            self.bottom_stack.setCurrentIndex(0) 
            QApplication.processEvents()
            
            if count == 1:
                filename = selected_items[0].text()
                content = self.controller.read_drive_file(filename) if is_drive else self.controller.read_local_file(folder_path, filename)
                
                self.add_text_edit(filename, content, mode="split")
                split_names = self.controller.generate_split_filenames(filename)
                self.split_name_1.setText(split_names[0])
                self.split_name_2.setText(split_names[1])
                self.bottom_stack.setCurrentIndex(1)
                
            else:
                filenames = []
                for item in selected_items:
                    filename = item.text()
                    filenames.append(filename)
                    content = self.controller.read_drive_file(filename) if is_drive else self.controller.read_local_file(folder_path, filename)
                    self.add_text_edit(filename, content, mode="merge", min_width=350)
                    
                self.merge_name_input.setText(self.controller.generate_merged_filename(filenames))
                self.bottom_stack.setCurrentIndex(2)
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 읽기 실패: {str(e)}")
            self.bottom_stack.setCurrentIndex(0)

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
        search_text = self.search_input.text()
        if not search_text or not self.current_text_edits: return
            
        found = False
        for text_edit in self.current_text_edits:
            if text_edit.find(search_text):
                found = True
                text_edit.setFocus()
                break
                
            cursor = text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            text_edit.setTextCursor(cursor)
            
            if text_edit.find(search_text):
                found = True
                text_edit.setFocus()
                break
                
        if not found:
            QMessageBox.information(self, "검색 결과", "더 이상 검색 결과가 없습니다.")

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

        try:
            self.log_signal.emit(f"[{filename}] 분할 저장을 시작합니다...")
            saved_files = self.controller.split_text_file(
                folder_path, filename, text_content, name1, name2
            )
            
            msg = f"총 {len(saved_files)}개의 파일로 분할되어 로컬에 저장되었습니다."
            
            if is_drive:
                self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
                for path in saved_files:
                    self.controller.upload_to_drive(path)
                msg += "\n(드라이브 업로드도 완료되었습니다!)"
                
            QMessageBox.information(self, "완료", msg)
            self.log_signal.emit("✅ 분할 작업 및 저장이 완료되었습니다.")
            self.populate_file_list()
            
        except ValueError as ve:
            QMessageBox.warning(self, "오류", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"분할 저장 중 오류 발생:\n{str(e)}")

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
            
        try:
            self.log_signal.emit(f"{files_to_merge} 파일 병합을 시작합니다...")
            saved_file = self.controller.merge_text_files(
                folder_path, files_to_merge, merged_content, custom_name
            )
            
            new_filename = os.path.basename(saved_file)
            msg = f"파일이 성공적으로 병합되어 로컬에 저장되었습니다:\n{new_filename}"
            
            if is_drive:
                self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
                self.controller.upload_to_drive(saved_file)
                msg += "\n\n(드라이브 업로드도 완료되었습니다!)"
            
            QMessageBox.information(self, "완료", msg)
            self.log_signal.emit(f"✅ 병합 작업 및 저장이 완료되었습니다: {new_filename}")
            self.populate_file_list()
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"병합 저장 중 오류 발생:\n{str(e)}")