import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QTextEdit, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from base.base_ui import BaseTab
from controller.json_editer_controller import JsonEditerController

class Tab9JsonEditer(BaseTab):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.controller = JsonEditerController(self)
        self.init_ui()
        self.load_selected_file()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            Tab9JsonEditer { background-color: #FFFFFF; }
            QWidget { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; color: #37352f; }
            QLabel { background-color: transparent; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)

        # 1. 상단 타이틀
        header_label = QLabel("⚙️ 설정 파일 직접 수정 (.env / JSON)")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # 2. 제어 바 (선택 및 리로드)
        control_frame = QFrame()
        control_frame.setObjectName("ControlBox")
        control_frame.setStyleSheet("""
            #ControlBox { background-color: #F4F5F7; border-radius: 12px; border: 1px solid #EAEAEA; }
            QLabel { font-weight: bold; color: #37352f; }
        """)
        
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        
        control_layout.addWidget(QLabel("파일 선택:"))
        
        self.file_combo = QComboBox()
        self.file_combo.addItem("API Key 가용 상태 파일 (api_key_state.json)", "json")
        self.file_combo.addItem("애플리케이션 환경 변수 (.env)", "env")
        self.file_combo.setStyleSheet("""
            QComboBox { padding: 6px 12px; border: 1px solid #D1D1CE; border-radius: 6px; background-color: #FFFFFF; font-size: 13px; }
        """)
        self.file_combo.currentIndexChanged.connect(self.load_selected_file)
        control_layout.addWidget(self.file_combo)
        
        control_layout.addStretch()
        
        self.reload_btn = QPushButton("🔄 다시 불러오기")
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 8px 14px; color: #555555; font-weight: bold; }
            QPushButton:hover { background-color: #F8F9FA; color: #111111; }
        """)
        self.reload_btn.clicked.connect(self.load_selected_file)
        control_layout.addWidget(self.reload_btn)
        
        layout.addWidget(control_frame)

        # 3. 에디터 텍스트 영역
        self.editor = QTextEdit()
        # 고정폭 폰트 설정
        mono_font = QFont("Courier New", 11)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(mono_font)
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #F9F9FB;
                border: 1px solid #EAEAEA;
                border-radius: 8px;
                padding: 15px;
                color: #24292e;
            }
        """)
        layout.addWidget(self.editor, stretch=1)

        # 4. 하단 버튼 영역
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        self.save_btn = QPushButton("💾 변경 사항 저장")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2EA043; color: white; 
                font-weight: bold; font-size: 14px; padding: 12px 28px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #238636; }
        """)
        self.save_btn.clicked.connect(self.save_current_file)
        bottom_layout.addWidget(self.save_btn)
        
        layout.addLayout(bottom_layout)

    def load_selected_file(self):
        file_type = self.file_combo.currentData()
        self.log_signal.emit(f"🔄 {file_type} 파일을 불러오는 중...")
        content = self.controller.load_file_content(file_type)
        self.editor.setPlainText(content)
        self.log_signal.emit(f"✅ {file_type} 파일을 성공적으로 로드했습니다.")

    def save_current_file(self):
        file_type = self.file_combo.currentData()
        content = self.editor.toPlainText()
        
        self.log_signal.emit(f"💾 {file_type} 파일 저장 검증 및 기록 중...")
        success, message = self.controller.save_file_content(file_type, content)
        
        if success:
            QMessageBox.information(self, "저장 완료", message)
            self.log_signal.emit(f"✅ {file_type} 파일이 정상 저장 및 검증되었습니다.")
            # 성공했을 때 다시 한번 불러와서 정돈된 포맷으로 동기화
            self.load_selected_file()
        else:
            QMessageBox.critical(self, "저장 실패", message)
            self.log_signal.emit(f"❌ {file_type} 저장 실패: {message}")