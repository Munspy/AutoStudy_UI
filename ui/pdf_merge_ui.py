
import os
from pathlib import Path

import pymupdf
from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QAbstractSpinBox, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QListWidgetItem,
                             QScrollArea, QVBoxLayout, QWidget)

from core.logger import GlobalLogger
from base.base_ui import BaseUI
from base.base_ui_components import (COLORS, CardWidget, LoadingButton, StyledButton,
                                     StyledCheckBox, StyledDateEdit,
                                     StyledListWidget)
from controller.pdf_merge_controller import PdfMergeController


class PreviewState:
    def __init__(self, doc, path, is_drive):
        self.doc = doc
        self.path = path
        self.is_drive = is_drive
        self.total_pages = doc.page_count
        self.loaded_pages = 0
        self.is_loading = False



class PdfMergeUi(BaseUI):
    global_progress_signal = pyqtSignal(int, str)
    global_loading_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.controller = PdfMergeController()
        
        self.controller.progress_signal.connect(self.global_progress_signal.emit)
        self.controller.error_signal.connect(self.show_error)
        self.controller.loading_signal.connect(self.global_loading_signal.emit)
        self.controller.file_list_ready.connect(self.on_file_list_ready)
        self.controller.merge_completed.connect(self.on_merge_completed)
        self.controller.preview_prepared.connect(self.on_item_prepared)
        self.controller.preview_finished.connect(self.on_preview_worker_finished)
        self.controller.page_rendered.connect(self.on_page_rendered)

        import tempfile
        self.file_paths = {}
        self.preview_states = {}
        self.drive_cache = {}
        self.temp_dir = os.path.join(tempfile.gettempdir(), "antigravity_pdf_cache")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PdfMergeUi { background-color: #FFFFFF; }
            QWidget {  color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # ===========================
        # [상단 타이틀 구성]
        # ===========================
        header_label = QLabel("🔗 PDF Merge (단순 병합)")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
        """)
        layout.addWidget(header_label)

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
        
        # drive_layout.addWidget(QLabel("📅 DATE"))
        
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
        self.search_btn.clicked.connect(self.fetch_files)
        control_layout.addWidget(self.search_btn)
        
        layout.addWidget(control_frame)

        # ===========================
        # [파일 리스트업 및 선택 영역]
        # ===========================
        file_selection_layout = QVBoxLayout()
        file_selection_layout.setSpacing(10)
        
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.select_all_cb = StyledCheckBox("전체 선택")
        self.select_all_cb.clicked.connect(self.toggle_all_items)
        mid_bar_layout.addWidget(self.select_all_cb)

        mid_bar_layout.addStretch()
        
        # '로컬로 받기' 체크박스 추가
        self.local_save_check = StyledCheckBox("로컬로 받기")
        mid_bar_layout.addWidget(self.local_save_check)
        
        self.select_scripted_btn = StyledButton("\u26A1\uFE0E 스크립트본 선택", "warning")
        self.select_scripted_btn.clicked.connect(self.select_scripted_items)
        mid_bar_layout.addWidget(self.select_scripted_btn)
        
        file_selection_layout.addLayout(mid_bar_layout)
        
        self.file_list = StyledListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(120)
        self.file_list.itemChanged.connect(self.on_item_changed)
        
        file_selection_layout.addWidget(self.file_list)
        layout.addLayout(file_selection_layout)

        # ===========================
        # [썸네일 미리보기 영역]
        # ===========================
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: " + COLORS["background_input"] + "; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(20, 20, 20, 20)
        self.preview_layout.setSpacing(20)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.preview_container)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll)
        layout.addWidget(self.scroll_area, stretch=1)

        # ===========================
        # [하단 저장 영역]
        # ===========================
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        bottom_layout.addWidget(QLabel("저장 파일명:"))
        self.save_name_input = QLineEdit("") 
        self.save_name_input.setStyleSheet("""
            QLineEdit { padding: 10px; border: 1px solid #D1D1CE; border-radius: 8px; background-color: #FFFFFF; font-weight: bold; width: 180px; }
        """)
        
        save_btn = StyledButton("💾 병합 저장", "save")
        save_btn.clicked.connect(self.start_merge)
        
        bottom_layout.addWidget(self.save_name_input)
        bottom_layout.addWidget(save_btn)
        layout.addLayout(bottom_layout)

        # 드라이브 업로드를 기본값으로 설정 (stateChanged → toggle_search_mode 자동 호출)
        self.drive_check.setChecked(True)

    def fetch_files(self):
        is_drive = self.drive_check.isChecked()
        target_dir = self.folder_input.text()
        start_str = self.start_date.date().toString("MMdd")
        end_str = self.end_date.date().toString("MMdd")
        
        # [BUG-FIX] 이전 문서 핸들 명시적 닫기 (메모리 누수 방지)
        for state in self.preview_states.values():
            if getattr(state, 'doc', None):
                try:
                    state.doc.close()
                except Exception:
                    pass
        self.preview_states.clear()

        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.file_paths.clear()
        self.file_list.blockSignals(False)
        self.controller.start_fetch_file_list(is_drive, target_dir, start_str, end_str)

    def on_file_list_ready(self, file_paths):
        self.file_paths = file_paths
        self.file_list.blockSignals(True)
        for text in self.file_paths.keys():
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.file_list.addItem(item)
        self.file_list.blockSignals(False)

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
        self.update_preview()

    def toggle_all_items(self):
        total = self.file_list.count()
        if total == 0: return

        checked_count = sum(1 for row in range(total) if self.file_list.item(row).checkState() == Qt.CheckState.Checked)
        new_state = Qt.CheckState.Unchecked if checked_count == total else Qt.CheckState.Checked
        
        self.file_list.blockSignals(True)
        for row in range(total):
            item = self.file_list.item(row)
            if item: item.setCheckState(new_state)
        self.file_list.blockSignals(False)
        
        self.update_select_all_ui()
        self.update_preview()

    def on_item_changed(self, item):
        self.update_select_all_ui()
        self.update_preview()

    def update_select_all_ui(self):
        total = self.file_list.count()
        if total == 0: return
        checked_count = sum(1 for row in range(total) if self.file_list.item(row).checkState() == Qt.CheckState.Checked)
        
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
        self.file_paths.clear()
        self.file_list.blockSignals(False)
        
        self.update_select_all_ui()
        self.update_preview()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder: self.folder_input.setText(folder)

    def update_preview(self):
        # We don't have direct access to preview_worker here anymore
        # The controller handles worker management
        
        for i in reversed(range(self.preview_layout.count())):
            widget = self.preview_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        
        selected_items = [self.file_list.item(i).text() for i in range(self.file_list.count()) if self.file_list.item(i).checkState() == Qt.CheckState.Checked]
        
        items_to_prepare = []
        for item_text in selected_items:
            if item_text not in self.preview_states:
                items_to_prepare.append(item_text)
                
        if items_to_prepare:
            self.global_loading_signal.emit(True)
            self.controller.start_prepare_previews(
                items_to_prepare, 
                self.file_paths, 
                self.drive_cache, 
                self.temp_dir, 
                self.drive_check.isChecked()
            )
        else:
            for item_text in selected_items:
                if item_text in self.preview_states:
                    self.add_preview_widget(item_text)

    def on_item_prepared(self, item_text, doc, path_or_id, is_drive, local_path):
        self.preview_states[item_text] = PreviewState(doc, path_or_id, is_drive)
        if is_drive and local_path:
            self.drive_cache[path_or_id] = local_path

    def on_preview_worker_finished(self, _=None):
        self.global_loading_signal.emit(False)
        selected_items = [self.file_list.item(i).text() for i in range(self.file_list.count()) if self.file_list.item(i).checkState() == Qt.CheckState.Checked]
        
        for i in reversed(range(self.preview_layout.count())):
            widget = self.preview_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        for item_text in selected_items:
            if item_text in self.preview_states:
                self.add_preview_widget(item_text)

    def add_preview_widget(self, item_text):
        state = self.preview_states[item_text]
        frame = QFrame()
        frame.setProperty("item_text", item_text)
        l = QVBoxLayout(frame)
        l.setContentsMargins(0, 0, 0, 10)
        l.setSpacing(5)
        title = QLabel(item_text)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        l.addWidget(title)
        
        pages_layout = QHBoxLayout()
        pages_layout.setContentsMargins(0, 0, 0, 0)
        pages_layout.setSpacing(5)
        pages_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        l.addLayout(pages_layout)
        self.preview_layout.addWidget(frame)
        
        state.loaded_pages = 0
        self.load_more_pages(state, frame, 8)
            
    def load_more_pages(self, state, frame, batch_size=8):
        if not state.doc or state.loaded_pages >= state.total_pages: return
        if getattr(state, 'is_loading', False): return
        
        state.is_loading = True
        end = min(state.loaded_pages + batch_size, state.total_pages)
        item_text = frame.property("item_text")
        
        local_path = state.path
        if state.is_drive and state.path in self.drive_cache:
            local_path = self.drive_cache[state.path]
            
        self.controller.request_render_pages(item_text, local_path, state.loaded_pages, end)
        state.loaded_pages = end

    def on_page_rendered(self, item_text, page_index, image_bytes):
        if item_text not in self.preview_states: return
        state = self.preview_states[item_text]
        
        # 찾기: preview_layout에서 해당 item_text를 가진 프레임을 찾음
        target_frame = None
        for i in range(self.preview_layout.count()):
            w = self.preview_layout.itemAt(i).widget()
            if w and w.property("item_text") == item_text:
                target_frame = w
                break
                
        if not target_frame: return
        
        pages_layout = target_frame.layout().itemAt(1).layout()
        img = QImage.fromData(image_bytes, "png")
        lbl = QLabel()
        lbl.setPixmap(QPixmap.fromImage(img))
        pages_layout.addWidget(lbl)
        
        # 렌더링이 완료되었는지 확인 (배치 마지막 페이지)
        # Note: 비동기로 도착하므로 정확한 끝 시점은 loaded_pages - 1 과 비교
        if page_index == state.loaded_pages - 1:
            state.is_loading = False
        
    def on_scroll(self, value):
        if value >= self.scroll_area.verticalScrollBar().maximum() - 10:
            for i in range(self.preview_layout.count()):
                frame = self.preview_layout.itemAt(i).widget()
                if frame:
                    item_text = frame.property("item_text")
                    if item_text in self.preview_states:
                        self.load_more_pages(self.preview_states[item_text], frame)

    def start_merge(self):
        selected = [self.file_list.item(i).text() for i in range(self.file_list.count()) if self.file_list.item(i).checkState() == Qt.CheckState.Checked]
        if len(selected) < 2:
            self.show_error("오류", "병합할 파일을 2개 이상 선택해주세요.")
            return
            
        is_drive = self.drive_check.isChecked()
        paths_to_merge = [self.file_paths[t] for t in selected]
        
        task_data = {
            'paths_to_merge': paths_to_merge,
            'save_name': self.save_name_input.text() or "merged.pdf",
            'is_drive': True,  # 출력은 항상 드라이브 업로드 수행
            'save_local': self.local_save_check.isChecked(),
            'target_dir': self.folder_input.text()
        }
        
        self.controller.start_merge(task_data)

    def on_merge_completed(self, msg):
        self.show_info("완료", msg)
