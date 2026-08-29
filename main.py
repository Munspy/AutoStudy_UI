import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QListWidget, QStackedWidget, QProgressBar, QTextEdit, 
                             QLabel, QSplitter)
from PyQt6.QtCore import Qt

# ---------------------------------------------------------
# 분리한 탭 모듈 임포트
# ---------------------------------------------------------

from ui.drive_sync_ui             import Tab1DriveSync
from ui.combine_notes_ui          import Tab2CombineNotes
from ui.pdf_merge_ui              import Tab3PdfMerge
from ui.pdf_split_ui              import Tab4PdfSplit
from ui.transcript_merge_split_ui import Tab5TranscriptMergeSplit
from ui.whisper_transcription_ui  import Tab6WhisperTranscription
from ui.gemini_processing_ui      import Tab7GeminiProcessing
from ui.youtube_playlist_ui       import Tab8YoutubePlaylist
from ui.json_editer_ui            import Tab9JsonEditer

class AutomationDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("스크립트본 생성 자동화 UI")
        self.resize(1200, 800)
        
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter, stretch=7)
        
        # ---------------------------------------------------------
        # 사이드바 메뉴 (총 8개 항목)
        # ---------------------------------------------------------
        self.sidebar = QListWidget()
        self.sidebar.setMaximumWidth(240)  # 긴 메뉴명을 위해 너비 소폭 조정
        self.sidebar.setSpacing(5)
        self.sidebar.addItems([
            "1. 드라이브 동기화 및 요약",
            "2. 줄필기 → 야붙필기 변환기",
            "3. PDF Merge",
            "4. PDF Split",
            "5. 전사문 Merge/Split",
            "6. Whisper 기반 음성 전사",
            "7. Gemini 기반 교정/요약/Anki",
            "8. Youtube 재생목록 관리",
            "9. Json 직접 수정"
        ])
        self.sidebar.setCurrentRow(0)
        self.splitter.addWidget(self.sidebar)
        
        self.stacked_widget = QStackedWidget()
        self.splitter.addWidget(self.stacked_widget)
        
        # ---------------------------------------------------------
        # 하단 진행률 및 로그 패널
        # ---------------------------------------------------------
        self.bottom_panel = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_panel)
        self.bottom_layout.setContentsMargins(0, 10, 0, 0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(100)
        self.bottom_layout.addWidget(QLabel("전체 진행률:"))
        self.bottom_layout.addWidget(self.progress_bar)
        
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumHeight(150)
        self.log_viewer.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        self.log_viewer.append("시스템이 초기화되었습니다. 대기 중...")
        self.bottom_layout.addWidget(self.log_viewer)
        
        self.main_layout.addWidget(self.bottom_panel, stretch=2)
        
        self.init_tabs()
        self.sidebar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

    def log_msg(self, message):
        self.log_viewer.append(f"> {message}")

    def init_tabs(self):
        # 탭 1: 드라이브 동기화 및 요약
        self.tab1 = Tab1DriveSync()
        if hasattr(self.tab1, 'log_signal'):
            self.tab1.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab1)
        
        # 탭 2: 줄필기 → 야붙필기 변환기
        self.tab2 = Tab2CombineNotes()
        if hasattr(self.tab2, 'log_signal'):
            self.tab2.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab2)
        
        # 탭 3: PDF Merge
        self.tab3 = Tab3PdfMerge()
        if hasattr(self.tab3, 'log_signal'):
            self.tab3.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab3)
        
        # 탭 4: PDF Split
        self.tab4 = Tab4PdfSplit()
        if hasattr(self.tab4, 'log_signal'):
            self.tab4.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab4)

        # 탭 5: 전사문 Merge/Split
        self.tab5 = Tab5TranscriptMergeSplit()
        if hasattr(self.tab5, 'log_signal'):
            self.tab5.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab5)

        # 탭 6: Whisper 기반 음성 전사
        self.tab6 = Tab6WhisperTranscription()
        if hasattr(self.tab6, 'log_signal'):
            self.tab6.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab6)

        # 탭 7: Gemini 기반 교정/요약/Anki
        self.tab7 = Tab7GeminiProcessing()
        if hasattr(self.tab7, 'log_signal'):
            self.tab7.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab7)
        
        # 탭 8: Youtube 재생목록 관리
        self.tab8 = Tab8YoutubePlaylist()
        if hasattr(self.tab8, 'log_signal'):
            self.tab8.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab8)

        # 탭 9: JSON 파일 직접 수정
        self.tab9 = Tab9JsonEditer()
        if hasattr(self.tab9, 'log_signal'):
            self.tab9.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab9)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = AutomationDashboard()
    window.show()
    sys.exit(app.exec())