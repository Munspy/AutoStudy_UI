# ui/combine_notes_ui.py
import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, QFileDialog, 
                             QScrollArea, QGraphicsOpacityEffect, QFrame, QListWidget, 
                             QListWidgetItem, QCheckBox, QDialog, QMessageBox, QWidget)
from PyQt6.QtCore import Qt

from base.base_ui import BaseTab
import controller.combine_notes_controller as backend

# ==========================================
# 🌟 분리해둔 utils 공구함 및 UI 헬퍼 임포트
# ==========================================
# (수정) 순수 바이트를 반환하는 함수로 변경
from utils.pdf_core_util import get_page_image_bytes
from base.base_ui_components import bytes_to_thumbnail_frame

# ==========================================
# 헬퍼 함수: UI 프레임 조립기
# ==========================================
def build_pdf_frame(page_info, is_empty, is_large=False):
    """
    utils의 공구를 활용해 PDF 페이지를 바이트로 추출하고, 
    UI 레벨에서 직접 썸네일 프레임을 조립하여 반환합니다.
    """
    width, height = (250, 176) if is_large else (212, 150)
    
    if is_empty or not page_info:
        return bytes_to_thumbnail_frame(None, "", width, height, is_empty=True)
        
    path = page_info["path"]
    page_num = page_info["page"]
    zoom_level = 0.8 if is_large else 0.5
    
    # 백엔드 로직: 순수 바이트(Bytes) 데이터 추출
    image_bytes = get_page_image_bytes(path, page_num, zoom=zoom_level)
    
    if not image_bytes:
        return bytes_to_thumbnail_frame(None, f"렌더링 실패\n{Path(path).name}\n{page_num+1}p", width, height, is_empty=True)
        
    return bytes_to_thumbnail_frame(image_bytes, "", width, height, is_empty=False)

# ==========================================
# (이하 팝업(FullScreenEditDialog) 및 Tab2CombineNotes 클래스 코드는 기존과 완벽히 동일합니다.)
# ==========================================
class FullScreenEditDialog(QDialog):
    def __init__(self, base_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("전체 화면 검수 및 수정")
        self.showMaximized() 
        
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
        """)
        
        self.controller = parent.controller if parent else None
        self.edit_data = self.controller.prepare_edit_data(base_data) if self.controller else prepare_edit_data(base_data)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(20)
        
        self.info_label = QLabel("✏️ 수정 모드 (야붙 체크 시 자동으로 페이지가 분리됩니다.)")
        self.info_label.setStyleSheet("font-size: 16px; color: #111111; font-weight: 800; padding-bottom: 10px;")
        self.main_layout.addWidget(self.info_label)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: #FFFFFF; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(20, 20, 20, 20)
        self.preview_layout.setSpacing(20)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.preview_container)
        self.main_layout.addWidget(self.scroll_area, stretch=1)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        cancel_btn = QPushButton("수정 취소 (Cancel)")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 8px; padding: 12px 28px; color: #E03E3E; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #FBE4E4; }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("수정 완료 (Save)")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2EA043; color: white; 
                font-weight: bold; font-size: 14px; padding: 12px 28px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #238636; }
        """)
        save_btn.clicked.connect(self.accept)
        
        bottom_layout.addWidget(cancel_btn)
        bottom_layout.addWidget(save_btn)
        self.main_layout.addLayout(bottom_layout)
        
        self.render_preview()

    def render_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for idx, item in enumerate(self.edit_data):
            self.add_edit_column(idx, item)

    def add_edit_column(self, idx, item):
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        nav_layout = QHBoxLayout()
        btn_left = QPushButton("◀")
        btn_right = QPushButton("▶")
        btn_style = """
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 4px; padding: 6px; font-size: 12px; font-weight: bold; color: #555555;
            }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
            QPushButton:disabled { background-color: #EFEFEF; color: #A0A0A0; }
        """
        btn_left.setStyleSheet(btn_style)
        btn_right.setStyleSheet(btn_style)
        
        btn_left.clicked.connect(lambda _, i=idx: self.move_item(i, -1))
        btn_right.clicked.connect(lambda _, i=idx: self.move_item(i, 1))
        
        if idx == 0: btn_left.setEnabled(False)
        if idx == len(self.edit_data) - 1: btn_right.setEnabled(False)
            
        nav_layout.addWidget(btn_left)
        nav_layout.addStretch()
        nav_layout.addWidget(btn_right)
        layout.addLayout(nav_layout)

        if item["jul"] is not None:
            top_page = build_pdf_frame(item["jul"], is_empty=False, is_large=True)
            op_top = QGraphicsOpacityEffect()
            op_top.setOpacity(1.0 if item.get("jul_checked", False) else 0.3)
            top_page.setGraphicsEffect(op_top)
            layout.addWidget(top_page)
            
            chk_top = QCheckBox("줄필기 포함")
            chk_top.setChecked(item.get("jul_checked", False))
            chk_top.setStyleSheet("font-weight: bold; color: #37352f; margin-bottom: 10px;")
            chk_top.stateChanged.connect(lambda state, i=idx: self.update_check_state(i, 'jul', state))
            
            chk_layout_top = QHBoxLayout()
            chk_layout_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout_top.addWidget(chk_top)
            layout.addLayout(chk_layout_top)
        else:
            layout.addWidget(build_pdf_frame(None, is_empty=True, is_large=True))
            layout.addSpacing(30)

        if item["yaboot"] is not None:
            bottom_page = build_pdf_frame(item["yaboot"], is_empty=False, is_large=True)
            op_bottom = QGraphicsOpacityEffect()
            op_bottom.setOpacity(1.0 if item.get("yaboot_checked", False) else 0.3)
            bottom_page.setGraphicsEffect(op_bottom)
            
            if item["type"] == "yaboot_only":
                bottom_page.setStyleSheet("background-color: white; border: 3px solid #2383E2; border-radius: 4px;")
            layout.addWidget(bottom_page)
            
            chk_bottom = QCheckBox("야붙 포함")
            chk_bottom.setChecked(item.get("yaboot_checked", False))
            chk_bottom.setStyleSheet("font-weight: bold; color: #37352f;")
            chk_bottom.stateChanged.connect(lambda state, i=idx: self.update_check_state(i, 'yaboot', state))
            
            chk_layout_bottom = QHBoxLayout()
            chk_layout_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout_bottom.addWidget(chk_bottom)
            layout.addLayout(chk_layout_bottom)
        else:
            layout.addWidget(build_pdf_frame(None, is_empty=True, is_large=True))
            layout.addSpacing(20)

        metrics = QLabel(item.get("metrics", ""))
        metrics.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metrics.setStyleSheet("color: #787774; font-size: 11px; font-weight: bold; background-color: #F1F1EF; padding: 6px; border-radius: 4px;")
        layout.addWidget(metrics)

        self.preview_layout.addWidget(column)

    def move_item(self, idx, direction):
        self.edit_data = self.controller.swap_items(self.edit_data, idx, direction)
        self.render_preview()
 
    def update_check_state(self, idx, role, state):
        item = self.edit_data[idx]
        is_checked = (state == 2)
 
        if role == 'jul':
            item["jul_checked"] = is_checked
        elif role == 'yaboot':
            item["yaboot_checked"] = is_checked
            if item["type"] == "matched" and is_checked:
                item_jul, item_yaboot = self.controller.split_item_on_yaboot_check(item)
                self.edit_data = self.edit_data[:idx] + [item_jul, item_yaboot] + self.edit_data[idx+1:]
                
        self.render_preview()

# ==========================================
# 기존 메인 탭 UI 개편
# ==========================================
class Tab2CombineNotes(BaseTab):  
    def __init__(self):
        super().__init__()
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab2CombineNotes {
                background-color: #FFFFFF;
            }
            QWidget {
                font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
                color: #37352f;
            }
            QLabel, QCheckBox {
                background-color: transparent;
                border: none;
            }
        """)
        
        self.base_data = [] 
        self.matched_groups = {} 
        
        self.controller = backend.CombineNotesController(self)
        self.controller.inspection_completed.connect(self.on_inspection_completed)
        self.controller.merge_completed.connect(self.on_merge_completed)
        self.controller.log_signal.connect(self.emit_log)
        self.controller.error_signal.connect(lambda msg: self.show_error("오류", msg))

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(20)
        
        self.init_top_panel()
        self.init_file_selection_area()
        self.init_preview_area()
        self.init_bottom_panel()
        
        self.refresh_file_list(self.folder_input.text())

    def init_top_panel(self):
        header_label = QLabel("🔄 줄필기 → 야붙필기 변환 및 검수")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
            background: transparent; border: none;
        """)
        self.main_layout.addWidget(header_label)

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
        control_layout.setSpacing(15)

        control_layout.addWidget(QLabel("📂 대상 폴더:"))
        
        # BaseTab의 load_setting 기능 활용
        default_folder = str(Path.home() / "Downloads")
        saved_folder = self.load_setting("target_folder_tab2", default_folder)
        
        self.folder_input = QLineEdit(saved_folder)
        self.folder_input.setStyleSheet("""
            QLineEdit {
                padding: 6px; border: 1px solid #D1D1CE; border-radius: 6px; 
                background-color: #FFFFFF; font-weight: normal;
            }
        """)
        self.folder_input.setReadOnly(True)
        control_layout.addWidget(self.folder_input)
        
        browse_btn = QPushButton("폴더 변경")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold;
            }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
        browse_btn.clicked.connect(self.browse_folder)
        control_layout.addWidget(browse_btn)
        
        self.main_layout.addWidget(control_frame)

    def init_file_selection_area(self):
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

        mid_bar_layout.addStretch()

        self.auto_run_btn = QPushButton("🚀 선택 파일 알아서 진행하기")
        self.auto_run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2EA043; color: white; 
                font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #238636; }
        """)
        self.auto_run_btn.clicked.connect(self.run_auto_merge)
        
        self.manual_run_btn = QPushButton("👀 선택 파일 검수하기")
        self.manual_run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2383E2; border: none; 
                border-radius: 8px; padding: 10px 20px; color: white; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #1A6FB0; }
        """)
        self.manual_run_btn.clicked.connect(self.run_manual_inspection)
        
        mid_bar_layout.addWidget(self.auto_run_btn)
        mid_bar_layout.addWidget(self.manual_run_btn)
        
        self.main_layout.addLayout(mid_bar_layout)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF; border: 1px solid #EAEAEA;
                border-radius: 8px; font-size: 13px; alternate-background-color: #FAFAFA;
                outline: none;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F4; color: #37352f; }
            QListWidget::item:selected { background-color: #E7F3F8; color: #37352f; border: none; }
            QListWidget::item:hover { background-color: #F8F9FA; }
        """)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMaximumHeight(90) 
        self.file_list.itemChanged.connect(self.check_individual_row_state)
        
        self.main_layout.addWidget(self.file_list)

    def init_preview_area(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #EAEAEA; border-radius: 8px; background-color: #FFFFFF; }")
        
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #FAFAFA;")
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(20, 20, 20, 20)
        self.preview_layout.setSpacing(20)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.preview_container)
        self.main_layout.addWidget(self.scroll_area, stretch=1)

    def init_bottom_panel(self):
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        self.edit_btn = QPushButton("상세 검수 및 수정 (전체화면)")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 8px; padding: 14px 20px; color: #555555; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
        self.edit_btn.clicked.connect(self.open_fullscreen_editor)
        
        self.approve_btn = QPushButton("최종 승인 및 병합 저장")
        self.approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.approve_btn.setStyleSheet("""
            QPushButton {
                background-color: #E03E3E; color: white; 
                font-weight: bold; font-size: 14px; padding: 14px 20px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #C93434; }
        """)
        self.approve_btn.clicked.connect(self.execute_final_save) 
        
        bottom_layout.addWidget(self.edit_btn)
        bottom_layout.addWidget(self.approve_btn)
        self.main_layout.addLayout(bottom_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "검색할 폴더 선택", self.folder_input.text())
        if folder:
            self.folder_input.setText(folder)
            # BaseTab의 save_setting 헬퍼 활용
            self.save_setting("target_folder_tab2", folder)
            self.refresh_file_list(folder)

    def refresh_file_list(self, folder_path):
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.matched_groups = self.controller.get_matched_file_groups(folder_path)
        
        for base_name, group in self.matched_groups.items():
            save_name = group["save_name"]
            if group["jul"] and group["yaboot"]:
                display_text = f"🔗 [매칭 성공 → {save_name}] 원본: {base_name}"
            elif group["jul"]:
                display_text = f"📄 [줄필기 단독 → {save_name}] 원본: {base_name}"
            else:
                display_text = f"📄 [야붙 단독 → {save_name}] 원본: {base_name}"

            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, base_name)
            self.file_list.addItem(item)
            
        self.file_list.blockSignals(False)
        self.update_select_all_ui()

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

    def check_individual_row_state(self, item):
        self.update_select_all_ui()

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

    def get_selected_keys(self):
        selected_keys = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_keys.append(item.data(Qt.ItemDataRole.UserRole))
        return selected_keys

    def run_manual_inspection(self):
        selected_keys = self.get_selected_keys()
        if not selected_keys:
            self.show_error("경고", "파일을 선택해 주세요.")
            return
        
        folder_path = self.folder_input.text()
        self.set_buttons_enabled(False)
        self.controller.start_inspection(folder_path, selected_keys, self.matched_groups)

    def run_auto_merge(self):
        selected_keys = self.get_selected_keys()
        if not selected_keys:
            self.show_error("경고", "파일을 선택해 주세요.")
            return
            
        folder_path = self.folder_input.text()
        self.set_buttons_enabled(False)
        self.auto_merge_mode = True
        self.controller.start_inspection(folder_path, selected_keys, self.matched_groups)

    def execute_final_save(self):
        if not self.base_data:
            self.show_error("경고", "저장할 데이터가 없습니다.\n먼저 검수하기를 눌러주세요.")
            return
            
        folder_path = self.folder_input.text()
        self.set_buttons_enabled(False)
        self.controller.start_merge(self.base_data, folder_path)

    def on_inspection_completed(self, base_data):
        self.base_data = base_data
        self.render_main_preview()
        
        if getattr(self, 'auto_merge_mode', False):
            self.auto_merge_mode = False
            self.execute_final_save()
        else:
            self.set_buttons_enabled(True)
            self.show_info("알림", "검수 데이터 생성이 완료되었습니다.\n하단의 미리보기를 확인하세요.")

    def on_merge_completed(self, saved_files):
        self.set_buttons_enabled(True)
        self.show_info("저장 완료", f"총 {len(saved_files)}개의 파일이 병합되어 저장되었습니다.\n\n[저장 위치]\n{self.folder_input.text()}")

    def set_buttons_enabled(self, enabled: bool):
        self.auto_run_btn.setEnabled(enabled)
        self.manual_run_btn.setEnabled(enabled)
        self.approve_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)

    def open_fullscreen_editor(self):
        if not self.base_data:
            self.show_error("경고", "먼저 '선택 파일 검수하기' 버튼을 눌러주세요.")
            return
            
        dialog = FullScreenEditDialog(self.base_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.base_data = self.controller.save_edits(dialog.edit_data)
            self.render_main_preview()

    def render_main_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in self.base_data:
            column = QWidget()
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            
            top_page = build_pdf_frame(item["jul"], is_empty=(item["jul"] is None))
            bottom_page = build_pdf_frame(item["yaboot"], is_empty=(item["yaboot"] is None))
            
            if item["type"] == "matched":
                op = QGraphicsOpacityEffect(); op.setOpacity(0.4)
                bottom_page.setGraphicsEffect(op)
            elif item["type"] == "yaboot_only":
                bottom_page.setStyleSheet("background-color: white; border: 3px solid #E03E3E; border-radius: 4px;")
                
            layout.addWidget(top_page)
            layout.addWidget(bottom_page)
            
            metrics = QLabel(item.get("metrics", ""))
            metrics.setAlignment(Qt.AlignmentFlag.AlignCenter)
            metrics.setStyleSheet("color: #787774; font-size: 11px; font-weight: bold; background-color: #F1F1EF; padding: 4px; border-radius: 4px;")
            layout.addWidget(metrics)
            
            self.preview_layout.addWidget(column)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = Tab2CombineNotes()
    window.show()
    sys.exit(app.exec())