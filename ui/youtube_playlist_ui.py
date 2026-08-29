import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableWidget, QTableWidgetItem, QLabel, 
                             QHeaderView, QCheckBox, QComboBox, QInputDialog, 
                             QFrame, QMessageBox, QDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

# ---------------------------------------------------------
# 백엔드 함수 모듈 임포트 (경로 호환성 처리)
# ---------------------------------------------------------
import controller.youtube_playlist_controller as backend


class PlaylistManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("재생목록 관리")
        self.resize(340, 150)
        
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        self.combo = QComboBox()
        self.combo.setStyleSheet("""
            QComboBox {
                padding: 6px 10px; border: 1px solid #D1D1CE; border-radius: 6px; 
                background-color: #FFFFFF; font-weight: normal;
            }
        """)
        self.load_data()
        
        title_label = QLabel("관리할 재생목록을 선택하세요:")
        title_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(title_label)
        self.layout.addWidget(self.combo)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.rename_btn = QPushButton("이름 변경")
        self.delete_btn = QPushButton("삭제")
        
        for btn in [self.rename_btn, self.delete_btn]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                    border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold;
                }
                QPushButton:hover { background-color: #F8F9FA; color: #111111; }
            """)
            
        self.rename_btn.clicked.connect(self.rename_pl)
        self.delete_btn.clicked.connect(self.delete_pl)
        
        btn_layout.addWidget(self.rename_btn)
        btn_layout.addWidget(self.delete_btn)
        self.layout.addLayout(btn_layout)
        
    def load_data(self):
        self.combo.clear()
        playlists = backend.load_csv_data()
        for p in playlists:
            self.combo.addItem(p['name'], p['playlist_id'])
            
    def rename_pl(self):
        pid = self.combo.currentData()
        if not pid:
            return
        new_name, ok = QInputDialog.getText(self, "이름 변경", "새 이름을 입력하세요:", text=self.combo.currentText())
        if ok and new_name.strip():
            backend.rename_playlist(pid, new_name.strip())
            self.load_data()
            QMessageBox.information(self, "성공", "이름이 변경되었습니다.")
            
    def delete_pl(self):
        pid = self.combo.currentData()
        if not pid:
            return
        reply = QMessageBox.question(
            self, "삭제 확인", "정말 삭제하시겠습니까?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            backend.delete_playlist(pid)
            self.load_data()
            QMessageBox.information(self, "성공", "삭제되었습니다.")


class Tab8YoutubePlaylist(QWidget):
    log_signal = pyqtSignal(str)
    global_progress_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        backend.init_csv()
        self.videos_data = [] 
        self.init_ui()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab8YoutubePlaylist {
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
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # --- 상단 헤더 ---
        header_label = QLabel("▶️ YouTube 재생목록 관리")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
            background: transparent; border: none;
        """)
        layout.addWidget(header_label)

        # --- 상단 컨트롤 박스 ---
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

        control_layout.addWidget(QLabel("현재 재생목록:"))
        
        self.playlist_combo = QComboBox()
        self.playlist_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 10px; border: 1px solid #D1D1CE; border-radius: 6px; 
                background-color: #FFFFFF; min-width: 250px; font-weight: normal;
            }
            QComboBox::drop-down { border: none; }
        """)
        control_layout.addWidget(self.playlist_combo)
        
        refresh_video_btn = QPushButton("데이터 새로고침")
        refresh_video_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_video_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold;
            }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
        refresh_video_btn.clicked.connect(self.load_playlist_data)
        control_layout.addWidget(refresh_video_btn)
        
        control_layout.addStretch()

        manage_pl_btn = QPushButton("⚙️ 관리")
        add_pl_btn = QPushButton("➕ 추가")
        refresh_list_btn = QPushButton("🔄 목록 갱신")
        
        secondary_btn_style = """
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold;
            }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """
        for btn in [manage_pl_btn, add_pl_btn, refresh_list_btn]:
            btn.setStyleSheet(secondary_btn_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            control_layout.addWidget(btn)
            
        manage_pl_btn.clicked.connect(self.open_manage_dialog)
        add_pl_btn.clicked.connect(self.add_playlist_dialog)
        refresh_list_btn.clicked.connect(self.refresh_combo_box)

        layout.addWidget(control_frame)

        # --- 중간 액션바 ---
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.select_all_cb = QCheckBox("전체 선택")
        self.select_all_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_cb.setStyleSheet("""
            QCheckBox { font-weight: bold; font-size: 14px; color: #37352f; margin-left: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #D1D1CE; background-color: #FFFFFF; }
            QCheckBox::indicator:checked { background-color: #2383E2; border: 1px solid #2383E2; }
        """)
        self.select_all_cb.clicked.connect(self.toggle_all_rows_smart)
        mid_bar_layout.addWidget(self.select_all_cb)
        
        mid_bar_layout.addStretch()

        sel_unex_btn = QPushButton("🎯 음성 미추출 자동 선택")
        sel_unex_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sel_unex_btn.setStyleSheet("""
            QPushButton {
                background-color: #F4F5F7; border: 1px solid #D1D1CE; 
                border-radius: 6px; padding: 8px 14px; font-weight: bold; font-size: 13px; color: #37352f;
            }
            QPushButton:hover { background-color: #EAEAEA; }
        """)
        sel_unex_btn.clicked.connect(self.select_unextracted)
        mid_bar_layout.addWidget(sel_unex_btn)

        layout.addLayout(mid_bar_layout)

        # --- 테이블 영역 ---
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "영상 제목", "추출 Prefix", "영상 길이", "음성 추출 여부", "링크"])
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF; border: 1px solid #EAEAEA;
                border-radius: 8px; gridline-color: #F4F4F4; font-size: 13px;
                alternate-background-color: #FAFAFA;
            }
            QHeaderView::section {
                background-color: #FFFFFF; border: none; border-bottom: 2px solid #EAEAEA;
                padding: 10px 5px; font-weight: bold; color: #787774;
            }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #F4F4F4; }
        """)
        self.table.setAlternatingRowColors(True)
        
        self.table.setColumnWidth(0, 40)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 80)
        
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self.check_individual_row_state)
        
        layout.addWidget(self.table)
        
        # --- 하단 실행 버튼 ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        self.upload_btn = QPushButton("☁️ 선택 영상 음성 추출 및 업로드")
        self.upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #2383E2; color: white; 
                font-weight: bold; font-size: 14px; padding: 14px 24px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #1A6FB0; }
            QPushButton:disabled { background-color: #A5C9F3; }
        """)
        self.upload_btn.clicked.connect(self.execute_upload)
        bottom_layout.addWidget(self.upload_btn)
        
        layout.addLayout(bottom_layout)

        # 시작 시 콤보박스 최신화 및 목록 자동 로드
        self.refresh_combo_box()

    def emit_log(self, message):
        self.log_signal.emit(message)
        
    def open_manage_dialog(self):
        dlg = PlaylistManagerDialog(self)
        dlg.exec()
        self.refresh_combo_box()

    def refresh_combo_box(self):
        self.playlist_combo.blockSignals(True)
        self.playlist_combo.clear()
        self.playlist_combo.addItem("⏳ 유튜브 업데이트 상태 확인 중...")
        
        playlists = backend.load_csv_data()
        
        if not playlists:
            self.playlist_combo.clear()
            self.playlist_combo.addItem("등록된 재생목록 없음")
            self.playlist_combo.blockSignals(False)
            return

        self.checker = backend.AllPlaylistUpdateChecker(playlists)
        self.checker.log_signal.connect(self.emit_log)
        self.checker.finished_signal.connect(self.on_checker_finished)
        self.checker.start()

    def on_checker_finished(self, sorted_playlists):
        self.playlist_combo.clear()
        
        for pl in sorted_playlists:
            date_str = pl.get('real_last_updated', '00000000')
            if len(date_str) == 8 and date_str != '00000000':
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                date_str = "확인 불가"
                
            self.playlist_combo.addItem(f"{pl['name']} (업데이트: {date_str})", pl['playlist_id'])
            
        self.playlist_combo.blockSignals(False)
        
        if sorted_playlists:
            self.emit_log("가장 최근에 업데이트된 재생목록을 불러옵니다.")
            self.playlist_combo.setCurrentIndex(0)
            self.load_playlist_data()

    def add_playlist_dialog(self):
        text, ok = QInputDialog.getText(self, '재생목록 추가', 'YouTube 재생목록 URL을 입력하세요:')
        if ok and text:
            playlist_id = backend.parse_playlist_id(text)
            if not playlist_id:
                QMessageBox.warning(self, "오류", "유효한 YouTube 재생목록 URL이 아닙니다.")
                return
            
            self.emit_log("재생목록 기본 이름을 유튜브에서 조회 중입니다...")
            default_name = backend.get_playlist_title(text)
            
            name, ok2 = QInputDialog.getText(self, '재생목록 이름 지정', '목록을 구별할 이름을 입력하세요:', text=default_name)
            if not ok2 or not name.strip():
                return

            backend.add_playlist_to_csv(name.strip(), text, playlist_id)
            self.emit_log(f"새로운 재생목록 '{name.strip()}' 추가 완료.")
            self.refresh_combo_box()

    def load_playlist_data(self):
        playlist_id = self.playlist_combo.currentData()
        if not playlist_id:
            self.emit_log("선택된 재생목록이 없습니다.")
            return

        self.table.setRowCount(0)
        self.videos_data.clear()
        
        self.fetcher = backend.PlaylistFetcher(playlist_id)
        self.fetcher.log_signal.connect(self.emit_log)
        self.fetcher.finished_signal.connect(self.populate_table)
        self.fetcher.error_signal.connect(lambda e: self.emit_log(f"로드 실패: {e}"))
        self.fetcher.start()

    def toggle_all_rows_smart(self):
        total = self.table.rowCount()
        if total == 0: return

        checked_count = sum(1 for row in range(total) 
                            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        
        new_state = Qt.CheckState.Unchecked if checked_count == total else Qt.CheckState.Checked
        
        self.table.blockSignals(True)
        for row in range(total):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(new_state)
        self.table.blockSignals(False)
        
        self.update_select_all_ui()

    def check_individual_row_state(self, item):
        if item.column() == 0:
            self.update_select_all_ui()

    def update_select_all_ui(self):
        total = self.table.rowCount()
        if total == 0: return
        checked_count = sum(1 for row in range(total) 
                            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        
        self.select_all_cb.blockSignals(True)
        if checked_count == total:
            self.select_all_cb.setChecked(True)
            self.select_all_cb.setText("전체 선택 해제")
        else:
            self.select_all_cb.setChecked(False)
            self.select_all_cb.setText("전체 선택")
        self.select_all_cb.blockSignals(False)
        
    def select_unextracted(self):
        self.table.blockSignals(True)
        for row, vid in enumerate(self.videos_data):
            item = self.table.item(row, 0)
            if item:
                if vid["extracted"] == "X" and bool(vid["prefix"]):
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.update_select_all_ui()

    def populate_table(self, videos):
        self.videos_data = videos
        
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        
        self.table.setRowCount(len(videos))
        playlist_id = self.playlist_combo.currentData()

        for row, vid in enumerate(videos):
            is_checked = (vid["extracted"] == "X" and bool(vid["prefix"]))
            chk_item = QTableWidgetItem("")
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, chk_item)
            
            self.table.setItem(row, 1, QTableWidgetItem(vid["title"]))
            
            prefix_item = QTableWidgetItem(vid["prefix"] if vid["prefix"] else "파싱 불가")
            prefix_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, prefix_item)
            
            len_item = QTableWidgetItem(vid["length"])
            len_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, len_item)
            
            item_status = QTableWidgetItem(vid["extracted"])
            item_status.setForeground(Qt.GlobalColor.transparent)
            self.table.setItem(row, 4, item_status)
            self.table.setCellWidget(row, 4, self.create_badge(vid["extracted"]))
            
            url = f"https://www.youtube.com/watch?v={vid['vid']}&list={playlist_id}"
            link_widget = self.create_link_button(url)
            self.table.setCellWidget(row, 5, link_widget)
            
            self.table.setRowHeight(row, 44)
            
        self.update_select_all_ui()
        
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.setSortingEnabled(True)
        
        self.emit_log(f"총 {len(videos)}개의 영상을 성공적으로 불러왔습니다.")

    def execute_upload(self):
        target_videos = []
        playlist_id = self.playlist_combo.currentData()
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                vid_info = self.videos_data[row]
                if not vid_info["prefix"]:
                    self.emit_log(f"경고: '{vid_info['title']}'은(는) 유효한 prefix 포맷이 아니어서 제외됩니다.")
                    continue
                    
                url = f"https://www.youtube.com/watch?v={vid_info['vid']}&list={playlist_id}"
                target_videos.append({"video_url": url, "prefix": vid_info["prefix"]})
                
        if not target_videos:
            self.emit_log("업로드 가능한 영상이 선택되지 않았습니다.")
            return

        self.upload_btn.setEnabled(False)
        self.emit_log(f"총 {len(target_videos)}개의 영상 추출 및 업로드를 시작합니다...")
        self.global_progress_signal.emit(0)
        
        self.upload_worker = backend.UploadWorker(target_videos)
        self.upload_worker.progress_signal.connect(self.emit_log)
        self.upload_worker.progress_val_signal.connect(self.global_progress_signal.emit)
        
        self.upload_worker.error_signal.connect(self.on_upload_error)
        self.upload_worker.finished_signal.connect(self.on_upload_finished)
        self.upload_worker.start()

    def on_upload_error(self, err_msg):
        self.emit_log(f"업로드 오류: {err_msg}")
        self.upload_btn.setEnabled(True)

    def on_upload_finished(self):
        self.emit_log("🎉 모든 업로드 작업이 완료되었습니다! '영상 새로고침'을 눌러 상태를 확인하세요.")
        self.upload_btn.setEnabled(True)

    def create_badge(self, text):
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: transparent; }")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        badge = QLabel("완료" if text == "O" else "미추출")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if text == "O":
            badge.setStyleSheet("background-color: #EDF3EC; color: #448361; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        else:
            badge.setStyleSheet("background-color: #FBE4E4; color: #C14C4C; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
            
        layout.addWidget(badge)
        return container

    def create_link_button(self, url):
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: transparent; }")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn = QPushButton("🔗 보기")
        btn.setStyleSheet("""
            QPushButton { color: #2383E2; border: none; font-weight: bold; text-decoration: underline; background: transparent; }
            QPushButton:hover { color: #1A6FB0; }
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        
        layout.addWidget(btn)
        return container