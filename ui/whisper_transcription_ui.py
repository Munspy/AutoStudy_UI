from base.base_ui import BaseUI
from base.base_ui_components import LoadingButton, CardWidget, StyledListWidget, StyledCheckBox

from PyQt6.QtWidgets import QListWidgetItem

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QListWidgetItem, 
                             QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt
from controller.whisper_transcription_controller import WhisperTranscriptionController


class WhisperTranscriptionUi(BaseUI):

    def __init__(self, task_manager=None):
        super().__init__(task_manager=task_manager)
        self.controller = WhisperTranscriptionController(task_manager=self.task_manager)
        self.controller.ui = self
        self.init_ui()
        self.check_macmini_connection()
        self.scan_drive_for_audio()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            WhisperTranscriptionUi { background-color: #FFFFFF; }
            QWidget {  color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # ===========================
        # [상단 헤더 구성]
        # ===========================
        header_label = QLabel("🎙️ Whisper AI 음성 전사 (Mac Mini 연동)")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # ===========================
        # [상단 컨트롤 박스 (상태 및 조회)]
        # ===========================
        control_frame = CardWidget()
        control_frame.setStyleSheet("QLabel { font-weight: bold; color: #37352f; }")
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        
        # 좌측 상단 맥미니 연결 표시란
        self.mac_status_label = QLabel("🖥️ Mac Mini 연결 상태: 확인 중...")
        self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555555;")
        control_layout.addWidget(self.mac_status_label)
        
        control_layout.addStretch()
        
        # 우측 상단 드라이브 조회 버튼
        self.scan_btn = LoadingButton("🔄 드라이브 조회", "sync")
        self.scan_btn.clicked.connect(self.scan_drive_for_audio)
        control_layout.addWidget(self.scan_btn)
        
        layout.addWidget(control_frame)

        # ===========================
        # [중앙부 미완료 리스트업]
        # ===========================
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)
        
        self.select_all_cb = StyledCheckBox("전체 선택")
        self.select_all_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_cb.clicked.connect(self.toggle_all_items)
        mid_bar_layout.addWidget(self.select_all_cb)
        mid_bar_layout.addStretch()
        layout.addLayout(mid_bar_layout)
        
        # 리스트 (오직 파일 이름으로 리스트업)
        self.file_list = StyledListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.itemChanged.connect(self.update_select_all_ui)
        layout.addWidget(self.file_list, stretch=1)

        # 진행 상태 바 (다운로드 및 전사 진행사항 확인용)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #EAEAEA; border-radius: 6px; text-align: center; font-weight: bold; color: #37352f; background-color: #F4F5F7; height: 18px; }
            QProgressBar::chunk { background-color: #A374DB; border-radius: 6px; }
        """)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # ===========================
        # [하단 실행 버튼]
        # ===========================
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        # 우측 하단 보라색 실행 버튼
        self.run_whisper_btn = LoadingButton("🎙️ Whisper 전사 실행", "whisper")
        self.run_whisper_btn.clicked.connect(self.execute_transcription)
        bottom_layout.addWidget(self.run_whisper_btn)
        
        layout.addLayout(bottom_layout)

    # ================= UI 및 로직 헬퍼 함수 =================

    def emit_log(self, message):
        self.log_signal.emit(message)

    def check_macmini_connection(self):
        # 실제 연결 체크 로직 백엔드 연결 필요
        is_connected = True 
        if is_connected:
            self.mac_status_label.setText("🖥️ Mac Mini 연결 상태: 연결됨 🟢")
            self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2EA043;")
        else:
            self.mac_status_label.setText("🖥️ Mac Mini 연결 상태: 연결 안됨 🔴")
            self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E03E3E;")

    def scan_drive_for_audio(self):
        self.scan_btn.start_loading("조회 중")
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.emit_log("드라이브 스캔: 전사가 필요한 음성 파일을 조회합니다...")
        self.controller.scan_drive()

    def populate_list(self, incomplete_files):
        for file_name in incomplete_files:
            item = QListWidgetItem(file_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.file_list.addItem(item)
            
        self.file_list.blockSignals(False)
        self.update_select_all_ui()
        self.scan_btn.stop_loading()
        self.emit_log(f"스캔 완료: 총 {len(incomplete_files)}개의 미전사 음성 파일이 발견되었습니다.")

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

    def update_select_all_ui(self):
        total = self.file_list.count()
        if total == 0: 
            self.select_all_cb.setChecked(False)
            self.select_all_cb.setText("전체 선택")
            return
            
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

    def execute_transcription(self):
        """
        3. 맥미니에 연결하여 다운로드 후 전사 실행. 진행사항 확인.
        """
        selected_items = [self.file_list.item(i) for i in range(self.file_list.count()) 
                          if self.file_list.item(i).checkState() == Qt.CheckState.Checked]
        
        if not selected_items:
            QMessageBox.warning(self, "경고", "전사를 실행할 오디오 파일을 선택해주세요.")
            return

        self.run_whisper_btn.start_loading("전사 중")
        self.scan_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
        file_names = [item.text() for item in selected_items]
        self.emit_log(f"Mac Mini로 작업 전송: {len(file_names)}개 파일의 Whisper 전사를 요청합니다...")
        
        self.controller.execute_whisper(file_names)

    def update_progress(self, progress, message=""):
        self.progress_bar.setValue(progress)
        # emit_log(message) if needed, but progress_bar is enough

    def on_transcription_finished(self):
        self.run_whisper_btn.stop_loading()
        self.scan_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.emit_log("🎉 Whisper 전사 작업이 완료되었습니다!")
        # 완료된 후 목록 재갱신
        self.scan_drive_for_audio()
    def show_error(self, message):
        self.emit_log(f"오류 발생: {message}")
        self.run_whisper_btn.stop_loading()
        if self.scan_btn.is_loading:
            self.scan_btn.stop_loading()
        else:
            self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "오류", message)
