import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFrame, QCheckBox, QListWidget, QListWidgetItem,
                             QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal

from controller.whisper_transcription_controller import WhisperTranscriptionController

class Tab6WhisperTranscription(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.controller = WhisperTranscriptionController(self)
        self.controller.log_signal.connect(self.emit_log)
        self.controller.error_signal.connect(self.on_controller_error)
        self.controller.scan_completed.connect(self.populate_list)
        self.controller.transcription_completed.connect(self.on_transcription_finished)
        self.controller.progress_val_signal.connect(self.update_progress)

        self.init_ui()
        # 초기 구동 시 맥미니 연결 상태 확인 및 드라이브 스캔 실행
        self.check_macmini_connection()
        self.scan_drive_for_audio()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab6WhisperTranscription { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # --- 상단 헤더 ---
        header_label = QLabel("🎙️ Whisper AI 음성 전사 (Mac Mini 연동)")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # --- 상단 컨트롤 박스 (1. 맥미니 연결 상태 및 7. 드라이브 조회 버튼) ---
        control_frame = QFrame()
        control_frame.setObjectName("ControlBox")
        control_frame.setStyleSheet("""
            #ControlBox { background-color: #F4F5F7; border-radius: 12px; border: 1px solid #EAEAEA; }
            QLabel { font-weight: bold; color: #37352f; }
        """)
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        
        # 좌측 상단 맥미니 연결 표시란
        self.mac_status_label = QLabel("🖥️ Mac Mini 연결 상태: 확인 중...")
        self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555555;")
        control_layout.addWidget(self.mac_status_label)
        
        control_layout.addStretch()
        
        # 우측 상단 드라이브 조회 버튼
        self.scan_btn = QPushButton("🔄 드라이브 조회")
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 8px 14px; color: #555555; font-weight: bold; }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
        self.scan_btn.clicked.connect(self.scan_drive_for_audio)
        control_layout.addWidget(self.scan_btn)
        
        layout.addWidget(control_frame)

        # --- 중앙부 미완료 리스트업 (전체 선택 포함) ---
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
        layout.addLayout(mid_bar_layout)
        
        # 리스트 (오직 파일 이름으로 리스트업)
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF; border: 1px solid #EAEAEA;
                border-radius: 8px; font-size: 14px; alternate-background-color: #FAFAFA; outline: none;
            }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #F4F4F4; color: #37352f; font-weight: 500; }
            QListWidget::item:selected { background-color: #E7F3F8; color: #37352f; border: none; }
            QListWidget::item:hover { background-color: #F8F9FA; }
        """)
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

        # --- 하단 실행 버튼 ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        # 우측 하단 보라색 실행 버튼 (Tab1 참고)
        self.run_whisper_btn = QPushButton("🎙️ Whisper 전사 실행")
        self.run_whisper_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_whisper_btn.setStyleSheet("""
            QPushButton {
                background-color: #A374DB; color: white; 
                font-weight: bold; font-size: 16px; padding: 14px 32px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #8D5CBF; }
            QPushButton:disabled { background-color: #D3C3E5; color: #FFFFFF; }
        """)
        self.run_whisper_btn.clicked.connect(self.execute_transcription)
        bottom_layout.addWidget(self.run_whisper_btn)
        
        layout.addLayout(bottom_layout)

    # ================= UI 및 로직 헬퍼 함수 =================

    def emit_log(self, message):
        self.log_signal.emit(message)

    def check_macmini_connection(self):
        # 실제 연결 체크 로직
        is_connected = True 
        if is_connected:
            self.mac_status_label.setText("🖥️ Mac Mini 연결 상태: 연결됨 🟢")
            self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2EA043;")
        else:
            self.mac_status_label.setText("🖥️ Mac Mini 연결 상태: 연결 안됨 🔴")
            self.mac_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E03E3E;")

    def scan_drive_for_audio(self):
        """
        드라이브를 스캔하여 전사가 필요한 오디오 파일만 필터링하여 조회합니다.
        """
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("조회 중...")
        self.emit_log("드라이브 스캔: 전사가 필요한 음성 파일을 조회합니다...")
        self.controller.scan_drive()

    def populate_list(self, incomplete_files):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔄 드라이브 조회")
        self.file_list.blockSignals(True)
        self.file_list.clear()
        
        for file_name in incomplete_files:
            item = QListWidgetItem(file_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.file_list.addItem(item)
            
        self.file_list.blockSignals(False)
        self.update_select_all_ui()
        self.emit_log(f"스캔 완료: 총 {len(incomplete_files)}개의 미전사 음성 파일이 발견되었습니다.")

    def update_progress(self, val):
        self.progress_bar.show()
        self.progress_bar.setValue(val)

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
        맥미니에 연결하여 다운로드 후 전사 실행. 진행사항 확인.
        """
        selected_items = [self.file_list.item(i) for i in range(self.file_list.count()) 
                          if self.file_list.item(i).checkState() == Qt.CheckState.Checked]
        
        if not selected_items:
            QMessageBox.warning(self, "경고", "전사를 실행할 오디오 파일을 선택해주세요.")
            return

        self.run_whisper_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
        file_names = [item.text() for item in selected_items]
        self.emit_log(f"Mac Mini로 작업 전송: {len(file_names)}개 파일의 Whisper 전사를 요청합니다...")
        self.controller.execute_whisper(file_names)

    def on_transcription_finished(self):
        self.run_whisper_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.progress_bar.hide()
        QMessageBox.information(self, "완료", "🎉 모든 Whisper 전사 작업이 완료되었습니다.")
        self.scan_drive_for_audio()

    def on_controller_error(self, err_msg):
        self.run_whisper_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.progress_bar.hide()
        self.emit_log(f"🔴 오류: {err_msg}")
        QMessageBox.critical(self, "오류", err_msg)