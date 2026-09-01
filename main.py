"""이 모듈은 자동화 대시보드(Automation Dashboard)의 메인 엔트리 포인트입니다.

전체 애플리케이션의 메인 윈도우를 정의하고, 여러 하위 UI 모듈들을 탭 형태로 
통합하여 관리하는 역할을 수행합니다. 내부적으로 단일 `BaseTaskManager`를 
생성하여 모든 탭에서 작업을 공유할 수 있도록 합니다.

Dependencies:
    - PyQt6 (GUI 프레임워크)
    - 각종 ui 모듈 (DriveSyncUi, CombineNotesUi 등)
    - base.base_task_manager (작업 관리)
"""
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QListWidget, QStackedWidget, QProgressBar, QTextEdit, 
                             QLabel, QSplitter)
from PyQt6.QtCore import Qt

# ---------------------------------------------------------
# 분리한 탭 모듈 임포트
# ---------------------------------------------------------

from ui.drive_sync_ui             import DriveSyncUi
from ui.combine_notes_ui          import CombineNotesUi
from ui.pdf_merge_ui              import PdfMergeUi
from ui.pdf_split_ui              import PdfSplitUi
from ui.transcript_merge_split_ui import TranscriptMergeSplitUi
from ui.whisper_transcription_ui  import WhisperTranscriptionUi
from ui.gemini_processing_ui      import GeminiProcessingUi
from ui.youtube_playlist_ui       import YoutubePlaylistUi
from ui.json_editer_ui            import JsonEditerUi

from base.base_task_manager import BaseTaskManager

class AutomationDashboard(QMainWindow):
    """스크립트본 생성 자동화 UI의 메인 윈도우 클래스.
    
    QSplitter를 활용하여 좌측에는 각 기능별 탭을 선택할 수 있는 사이드바 메뉴를 배치하고,
    우측에는 선택된 탭의 UI를 보여줍니다. 하단에는 모든 탭에서 발생하는 
    로그와 진행률을 보여주는 패널이 존재합니다.
    
    Attributes:
        global_task_manager (BaseTaskManager): 애플리케이션 전역에서 사용되는 비동기 작업 관리자.
    """
    def __init__(self):
        """AutomationDashboard의 초기화를 수행합니다.
        
        메인 윈도우의 크기와 레이아웃을 설정하고, 사이드바, 상태 패널(진행률/로그), 
        그리고 각 탭 화면들을 구성합니다. 또한 전역 작업 관리자를 생성하여 초기화합니다.
        """
        super().__init__()
        
        # ===========================
        # [1. 메인 윈도우 기본 설정]
        # ===========================
        # 윈도우 제목 및 크기 지정
        self.setWindowTitle("스크립트본 생성 자동화 UI")
        self.resize(1200, 800)
        
        # 메인 위젯을 생성하고 윈도우의 중앙 위젯으로 설정
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        # 메인 위젯을 위한 수직 레이아웃 설정
        self.main_layout = QVBoxLayout(self.main_widget)
        
        # 수평 분할기를 생성하여 좌우 레이아웃을 구분 (비중 7 설정)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter, stretch=7)
        
        # ===========================
        # [2. 사이드바 메뉴 구성]
        # ===========================
        # 메뉴 리스트를 표시할 QListWidget 생성
        self.sidebar = QListWidget()
        self.sidebar.setMaximumWidth(240)  # 긴 메뉴명을 위해 너비 소폭 조정
        self.sidebar.setSpacing(5) # 메뉴 항목 간의 간격 설정
        
        # 사이드바에 메뉴 항목들을 추가
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
        # 기본으로 첫 번째 메뉴가 선택되도록 설정
        self.sidebar.setCurrentRow(0)
        # 생성된 사이드바를 분할기에 추가
        self.splitter.addWidget(self.sidebar)
        
        # 우측 화면에 탭 별 UI를 보여줄 스택 위젯 생성 및 추가
        self.stacked_widget = QStackedWidget()
        self.splitter.addWidget(self.stacked_widget)
        
        # ===========================
        # [3. 하단 상태 패널 구성]
        # ===========================
        # 하단 진행률 및 로그 패널용 위젯과 레이아웃 생성
        self.bottom_panel = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_panel)
        # 위쪽 마진을 주어 상단 영역과의 간격 확보
        self.bottom_layout.setContentsMargins(0, 10, 0, 0)
        
        # 전체 진행률을 나타내는 프로그레스 바 생성 및 추가
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0) # 진행률 100으로 초기화
        self.bottom_layout.addWidget(self.progress_bar)
        
        # 시스템 로그를 출력할 텍스트 에디터 생성
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True) # 읽기 전용으로 설정
        self.log_viewer.setMaximumHeight(150) # 높이 제한 설정
        # 시스템 콘솔과 같은 스타일 적용
        self.log_viewer.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Menlo;")
        self.log_viewer.append("시스템이 초기화되었습니다. 대기 중...")
        self.bottom_layout.addWidget(self.log_viewer)
        
        # 구성된 하단 패널을 메인 레이아웃에 추가 (비중 2 설정)
        self.main_layout.addWidget(self.bottom_panel, stretch=2)

        # ===========================
        # [4. 글로벌 태스크 매니저 및 탭 초기화]
        # ===========================
        # 1. 단 하나의 글로벌 태스크 매니저 생성 (최대 동시 작업 3개)
        self.global_task_manager = BaseTaskManager(max_concurrent_tasks=3)
        
        # 내부 탭들 생성 및 초기화
        self.init_tabs()
        # 사이드바 아이템 선택 시 스택 위젯의 활성 페이지가 전환되도록 연결
        self.sidebar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

    def log_msg(self, message):
        """메인 윈도우 하단 로그 패널에 메시지를 추가합니다.
        
        각 탭에서 발생하는 로그 이벤트를 수신하여 화면에 표시할 때 사용됩니다.
        
        Args:
            message (str): 출력할 로그 메시지 문자열.
        """
        self.log_viewer.append(f"> {message}")

    def init_tabs(self):
        """애플리케이션 내의 모든 탭 UI를 생성하고 Stacked Widget에 추가합니다.
        
        전역 task_manager를 각 탭에 주입하고, 각 탭의 로그 시그널을 메인 윈도우의
        log_msg 슬롯과 연결합니다. 앱 초기화 시 전체 UI 구성을 완료하기 위해 호출됩니다.
        """
        # 탭 1: 드라이브 동기화 및 요약
        self.tab1 = DriveSyncUi(self.global_task_manager)
        self.tab1.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab1)
        
        # 탭 2: 줄필기 → 야붙필기 변환기
        self.tab2 = CombineNotesUi(self.global_task_manager)
        self.tab2.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab2)
        
        # 탭 3: PDF Merge
        self.tab3 = PdfMergeUi(self.global_task_manager)
        self.tab3.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab3)
        
        # 탭 4: PDF Split
        self.tab4 = PdfSplitUi(self.global_task_manager)
        self.tab4.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab4)

        # 탭 5: 전사문 Merge/Split
        self.tab5 = TranscriptMergeSplitUi(self.global_task_manager)
        self.tab5.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab5)

        # 탭 6: Whisper 기반 음성 전사
        self.tab6 = WhisperTranscriptionUi(self.global_task_manager)
        self.tab6.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab6)

        # 탭 7: Gemini 기반 교정/요약/Anki
        self.tab7 = GeminiProcessingUi(self.global_task_manager)
        self.tab7.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab7)
        
        # 탭 8: Youtube 재생목록 관리
        self.tab8 = YoutubePlaylistUi(self.global_task_manager)
        self.tab8.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab8)

        # 탭 9: JSON 파일 직접 수정
        self.tab9 = JsonEditerUi(self.global_task_manager)
        # self.tab9.log_signal.connect(self.log_msg)
        self.stacked_widget.addWidget(self.tab9)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    
    # OS별 폰트 동적 적용 (맥은 Apple SD, 윈도우는 맑은 고딕)
    from PyQt6.QtGui import QFont
    if sys.platform == "darwin":
        font_family = "Apple SD Gothic Neo"
        font_size = 13
    elif sys.platform == "win32":
        font_family = "Malgun Gothic"
        font_size = 10
    else:
        font_family = "sans-serif"
        font_size = 10

    app.setFont(QFont(font_family, font_size))
    # 스타일시트에서도 폰트 패밀리를 명시해주어야 개별 위젯의 QSS 때문에 기본 폰트가 풀리는 현상을 방지합니다.
    app.setStyleSheet(f"QWidget {{ font-family: '{font_family}'; font-size: {font_size}pt; }}")

    window = AutomationDashboard()
    window.show()
    sys.exit(app.exec())