"""구글 드라이브 동기화 상태 관리 UI 모듈.

이 모듈은 로컬 작업 폴더와 구글 드라이브 간의 파일 동기화 상태를 조회하고
제어하는 UI 화면을 제공합니다. 필기 스크립트, 요약본, Anki 카드 등 파이프라인의
진행 상태를 테이블 형태로 시각화하며, 누락된 작업 실행이나 Whisper 전사 요청 등을 
수행할 수 있습니다.

Classes:
    DriveSyncUi: 동기화 상태 테이블과 제어 버튼을 포함하는 메인 탭 UI 클래스.
"""
import os
from core.logger import GlobalLogger


from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (QAbstractSpinBox, QFileDialog, QHBoxLayout,
                             QHeaderView, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from base.base_ui import BaseUI
from base.base_ui_components import (COLORS, CardWidget, LoadingButton, StatusBadge,
                                     StyledButton, StyledCheckBox,
                                     StyledComboBox, StyledDateEdit,
                                     StyledTableWidget, HeaderLabel)
from viewmodel.drive_sync_viewmodel import DriveSyncViewModel



class DriveSyncUi(BaseUI):
    """로컬과 구글 드라이브의 동기화 상태를 모니터링하고 제어하는 메인 화면 클래스.
    
    데이터 파이프라인의 상태(필기, 음성 스크립트, 요약본 등)를 테이블로 표시하고,
    DriveSyncViewModel와 협력하여 백그라운드 동기화 및 파일 다운로드 작업을 수행합니다.
    
    Attributes:
        local_download_path (str): 로컬 검색의 기준이 되는 다운로드 폴더 경로.
        viewmodel (DriveSyncViewModel): 동기화 작업을 처리할 컨트롤러 인스턴스.
    """
    def __init__(self, parent=None):
        super().__init__(app_name="DriveSync", parent=parent)        
        
        default_path = os.path.expanduser("~/Downloads")
        self.local_download_path = self.load_setting("local_download_path", default_path)
        
        self.viewmodel = DriveSyncViewModel()
        
        # 1. 변경된 알람(Trigger) 시그널 연결 (파라미터 없음)
        self.viewmodel.sync_data_changed.connect(self.update_table)
        self.viewmodel.categories_changed.connect(self.populate_exam_categories)
        self.viewmodel.error_occurred.connect(self.show_error)
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            DriveSyncUi { background-color: #FFFFFF; }
            QWidget { color: #37352f; }
            QLabel, QCheckBox { background-color: transparent; border: none; }
        """)

        # ===========================
        # [메인 레이아웃 설정]
        # ===========================
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(20)

        self.init_top_panel()
        self.init_action_bar()
        self.init_table_area()
        self.init_bottom_panel()
        
        self.refresh_exam_categories()

    def init_top_panel(self):
        """상단 헤더 및 시험/날짜 필터, 로컬 폴더 설정 프레임을 조립합니다."""
        header_label = HeaderLabel("📚 강의 데이터 파이프라인 상태")
        self.main_layout.addWidget(header_label)

        control_frame = CardWidget()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(15)

        # 1. 시험 기준 필터
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("시험 기준:"))

        self.exam_combo = StyledComboBox()
        self.exam_combo.addItem("사용 안함", None)
        filter_layout.addWidget(self.exam_combo)

        self.btn_refresh_exam = QPushButton("🔄")
        self.btn_refresh_exam.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_exam.setToolTip("시험 기준 폴더 새로고침")
        self.btn_refresh_exam.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 6px 8px; color: #555555; font-weight: bold; }
            QPushButton:hover { background-color: #F7F7F5; border-color: #BCBCB8; }
        """)
        self.btn_refresh_exam.clicked.connect(lambda: self.refresh_exam_categories(force_refresh=True))
        filter_layout.addWidget(self.btn_refresh_exam)

        separator = QLabel("  |  ")
        separator.setStyleSheet(f"color: {COLORS['border_input']}; font-weight: normal; font-size: 16px;")
        filter_layout.addWidget(separator)

        # 2. 날짜 범위 필터
        self.date_label = QLabel("날짜 범위:")
        filter_layout.addWidget(self.date_label)

        today = QDate.currentDate()
        self.start_date = StyledDateEdit()
        self.start_date.setDate(today)
        self.start_date.setDisplayFormat("MM-dd")
        self.start_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.start_date.setCalendarPopup(True)

        self.end_date = StyledDateEdit()
        self.end_date.setDate(today)
        self.end_date.setDisplayFormat("MM-dd")
        self.end_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.end_date.setCalendarPopup(True)

        filter_layout.addWidget(self.start_date)
        filter_layout.addWidget(QLabel("~"))
        filter_layout.addWidget(self.end_date)
        
        self.exam_combo.currentTextChanged.connect(self.toggle_date_inputs)
        control_layout.addLayout(filter_layout)
        control_layout.addStretch()

        # 3. 로컬 폴더 설정 버튼
        self.btn_set_folder = QPushButton("📂 LOCAL")
        self.btn_set_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_set_folder.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; border: 1px solid #D1D1CE; border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold; }
            QPushButton:hover { background-color: #F8F9FA; }
        """)
        self.btn_set_folder.clicked.connect(self.set_local_folder)
        control_layout.addWidget(self.btn_set_folder)

        self.main_layout.addWidget(control_frame)

    def init_action_bar(self):
        """전체 선택 체크박스와 데이터 조회 버튼 영역을 조립합니다."""
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)

        self.select_all_cb = StyledCheckBox("전체 선택")
        self.select_all_cb.clicked.connect(self.toggle_all_rows_smart)
        mid_bar_layout.addWidget(self.select_all_cb)

        mid_bar_layout.addStretch()

        self.search_btn = LoadingButton(" 데이터 동기화 및 조회", "primary")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setStyleSheet("""
            QPushButton { background-color: #2383E2; border: none; border-radius: 8px; padding: 12px 28px; color: white; font-weight: bold; font-size: 15px; }
            QPushButton:hover { background-color: #1A6FB0; }
            QPushButton:disabled { background-color: #A5C9F3; }
        """)
        self.search_btn.clicked.connect(self.execute_search_log)
        mid_bar_layout.addWidget(self.search_btn)

        self.main_layout.addLayout(mid_bar_layout)

    def init_table_area(self):
        """메인 데이터가 표시되는 테이블 영역을 조립합니다."""
        self.table = StyledTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "", "수업 교시", "교수", "강의명", "필기", "음성 스크립트", 
            "최종교정본", "요약본", "Anki", "스크립트 합본"
        ])

        self.table.setAlternatingRowColors(True)
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 180)
        for i in range(6, 10): 
            self.table.setColumnWidth(i, 90)

        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.itemChanged.connect(self.check_individual_row_state)

        self.main_layout.addWidget(self.table)
        
    def init_bottom_panel(self):
        """하단 누락 작업 실행 및 다운로드 액션 버튼 영역을 조립합니다."""
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        btn_run_local = StyledButton("누락 로컬 작업 실행", "save")
        btn_run_local.clicked.connect(self.viewmodel.execute_local_tasks)
        actions_layout.addWidget(btn_run_local)

        btn_run_whisper = StyledButton("🎙️ Whisper AI 전사", "whisper")
        btn_run_whisper.clicked.connect(self.viewmodel.execute_whisper_transcription)
        actions_layout.addWidget(btn_run_whisper)

        btn_dl_script = StyledButton("💾 스크립트 합본 다운로드", "important")
        btn_dl_script.clicked.connect(self.download_script_merged)
        actions_layout.addWidget(btn_dl_script)
        
        actions_layout.addStretch() 

        btn_dl_summary = StyledButton("📝 요약본 다운로드", "trivia")
        btn_dl_anki = StyledButton("🗂️ Anki 다운로드", "trivia")
        btn_dl_summary.clicked.connect(self.download_summary)
        btn_dl_anki.clicked.connect(self.download_anki)
        
        actions_layout.addWidget(btn_dl_summary)
        actions_layout.addWidget(btn_dl_anki)

        self.main_layout.addLayout(actions_layout)

        self.binder.bind_loading_button(self.search_btn, self.viewmodel, 'is_loading', '조회 중')
        self.binder.bind_enabled(self.exam_combo, self.viewmodel, 'is_loading', invert=True)
        self.binder.bind_enabled(self.start_date, self.viewmodel, 'is_loading', invert=True)
        self.binder.bind_enabled(self.end_date, self.viewmodel, 'is_loading', invert=True)
        self.binder.bind_enabled(self.table, self.viewmodel, 'is_loading', invert=True)

    # ===========================
    # [기능 메서드]
    # ===========================
    def get_checked_lessons(self) -> list[str]:
        """테이블에서 선택(체크)된 행들의 수업 교시(Lesson ID) 리스트를 추출합니다."""
        checked_lessons = []
        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                lesson_item = self.table.item(row, 1)
                if lesson_item and lesson_item.text().strip():
                    checked_lessons.append(lesson_item.text().strip())
        return checked_lessons

    def download_summary(self):
        checked_lessons = self.get_checked_lessons()
        if not checked_lessons:
            GlobalLogger.info("⚠️ [오류] 요약본을 다운로드할 수업이 선택되지 않았습니다.")
            return

        sorted_checked = sorted(checked_lessons)
        default_filename = f"요약본합본_{sorted_checked[0]}.pdf" if len(sorted_checked) == 1 else f"요약본합본_{sorted_checked[0]}_{sorted_checked[-1]}.pdf"
        output_path, _ = QFileDialog.getSaveFileName(self, "요약본 PDF 저장 위치 선택", os.path.join(self.local_download_path, default_filename), "PDF Files (*.pdf)")
        if not output_path:
            GlobalLogger.info("ℹ️ 요약본 다운로드가 취소되었습니다.")
            return
        self.viewmodel.download_summary(checked_lessons, output_path)

    def download_anki(self):
        checked_lessons = self.get_checked_lessons()
        if not checked_lessons:
            GlobalLogger.info("⚠️ [오류] Anki 덱을 다운로드할 수업이 선택되지 않았습니다.")
            return

        sorted_checked = sorted(checked_lessons)
        default_filename = f"안키합본_{sorted_checked[0]}.apkg" if len(sorted_checked) == 1 else f"안키합본_{sorted_checked[0]}_{sorted_checked[-1]}.apkg"
        output_path, _ = QFileDialog.getSaveFileName(self, "Anki 합본 저장 위치 선택", os.path.join(self.local_download_path, default_filename), "Anki Deck (*.apkg)")
        if not output_path:
            GlobalLogger.info("ℹ️ Anki 다운로드가 취소되었습니다.")
            return
        self.viewmodel.download_anki(checked_lessons, output_path)

    def download_script_merged(self):
        """체크된 수업들의 _scripted.pdf 파일 합본 다운로드를 시작합니다."""
        checked_lessons = self.get_checked_lessons()
        if not checked_lessons:
            GlobalLogger.info("⚠️ [오류] 스크립트 합본을 다운로드할 수업이 선택되지 않았습니다. 테이블에서 체크박스를 선택해주세요.")
            return

        sorted_checked = sorted(checked_lessons)
        if len(sorted_checked) > 1:
            default_filename = f"스크립트합본_{sorted_checked[0]}_{sorted_checked[-1]}.pdf"
        else:
            default_filename = f"스크립트합본_{sorted_checked[0]}.pdf"

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "스크립트 합본 PDF 저장 위치 선택",
            os.path.join(self.local_download_path, default_filename),
            "PDF Files (*.pdf)"
        )
        if not output_path:
            GlobalLogger.info("ℹ️ 스크립트 합본 다운로드가 취소되었습니다.")
            return

        GlobalLogger.info(f"💾 총 {len(checked_lessons)}개 수업에 대한 스크립트 합본 다운로드를 요청합니다. (저장 위치: {output_path})")
        self.viewmodel.download_script_merged(checked_lessons=checked_lessons, output_path=output_path)

    def refresh_exam_categories(self, force_refresh: bool = False):
        """구글 드라이브에서 시험 기준(과목/차수) 폴더 목록을 비동기 조회합니다."""
        GlobalLogger.info("구글 드라이브에서 시험 기준 폴더 목록을 조회합니다...")
        self.viewmodel.fetch_categories(force_refresh=force_refresh)

    def populate_exam_categories(self):
        """뷰모델의 시험 기준 목록을 훔쳐와 콤보박스에 반영합니다."""
        # 파라미터(categories)가 사라졌습니다! 뷰모델 데이터를 직접 참조합니다.
        categories = self.viewmodel.categories 
        
        self.exam_combo.blockSignals(True)
        current_data = self.exam_combo.currentData()
        self.exam_combo.clear()
        self.exam_combo.addItem("사용 안함", None)
        
        selected_idx = 0
        for idx, (name, folder_id) in enumerate(categories, start=1):
            self.exam_combo.addItem(name, folder_id)
            if current_data and current_data == folder_id:
                selected_idx = idx
                
        self.exam_combo.setCurrentIndex(selected_idx)
        self.exam_combo.blockSignals(False)
        self.toggle_date_inputs(self.exam_combo.currentText())
        
        if categories:
            GlobalLogger.info(f"총 {len(categories)}개의 시험 기준(과목/차수) 폴더를 불러왔습니다.")

    def set_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "로컬 검색 폴더 선택", self.local_download_path)
        if folder:
            self.local_download_path = folder
            self.save_setting("local_download_path", folder)  # BaseUI의 save_setting 헬퍼 활용
            GlobalLogger.info(f"설정 완료: 검색 폴더가 [{folder}] (으)로 변경되었습니다.")

    def toggle_date_inputs(self, text):
        is_disabled = (text != "사용 안함")
        self.start_date.setEnabled(not is_disabled)
        self.end_date.setEnabled(not is_disabled)

    def execute_search_log(self):
        """선택된 시험 기준(또는 날짜 범위)으로 구글 드라이브 동기화 조회를 실행합니다."""
        current_exam = self.exam_combo.currentText()
        selected_folder_id = self.exam_combo.currentData()
        
        if current_exam == "사용 안함" or not selected_folder_id:
            start = self.start_date.date().toString("yyyy-MM-dd")
            end = self.end_date.date().toString("yyyy-MM-dd")
            display_start = self.start_date.date().toString("MM-dd")
            display_end = self.end_date.date().toString("MM-dd")
            
            self.viewmodel.search_mode = "DATE"
            self.viewmodel.filter_value = (start, end)
            GlobalLogger.info(f"기간 [{display_start} ~ {display_end}] 기준으로 구글 드라이브 동기화 조회를 시작합니다...")
        else:
            self.viewmodel.search_mode = "EXAM"
            self.viewmodel.filter_value = selected_folder_id
            GlobalLogger.info(f"시험 기준 [{current_exam}] (으)로 해당 폴더의 최신 상태를 불러옵니다...")

        self.viewmodel.local_path = self.local_download_path
        self.viewmodel.execute_sync()


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
        if item.column() != 0:
            return

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

    def create_badge(self, text):
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: transparent; }")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        state_map = {
            "완료": "success",
            "줄": "warning",
            "없음": "warning",
            "O (완료)": "primary",
            "Whisper AI 전사 필요": "secondary",
            "Youtube 동기화 필요": "danger",
            "영상 없음": "danger",
        }
        
        state = state_map.get(text, "primary")
        badge = StatusBadge(text, state)
        
        layout.addWidget(badge)
        return container

    def create_readonly_checkbox(self, checked):
        container = QWidget()
        container.setStyleSheet("QWidget { background-color: transparent; }")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        cb = StyledCheckBox()
        cb.setChecked(checked)
        cb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        layout.addWidget(cb)
        return container

    def update_table(self):
        """뷰모델의 동기화 데이터를 훔쳐와 테이블을 다시 그립니다."""
        # 파라미터(data_list)가 사라졌습니다! 뷰모델 데이터를 직접 참조합니다.
        data_list = self.viewmodel.sync_data
        GlobalLogger.info(f"총 {len(data_list)}건의 강의 데이터를 성공적으로 불러왔습니다.")
        
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        
        self.table.setRowCount(0)
        
        checkbox_columns = ["교정 스크립트", "요약본", "Anki", "스크립트 합본"]
        
        for row_idx, data in enumerate(data_list):
            self.table.insertRow(row_idx)
            
            chk_item = QTableWidgetItem("")
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row_idx, 0, chk_item)
            
            self.table.setItem(row_idx, 1, QTableWidgetItem(data.get("수업교시", "")))
            self.table.setItem(row_idx, 2, QTableWidgetItem(data.get("교수", "")))
            self.table.setItem(row_idx, 3, QTableWidgetItem(data.get("강의명", "")))
            
            item_status1 = QTableWidgetItem("")
            item_status1.setForeground(Qt.GlobalColor.transparent)
            self.table.setItem(row_idx, 4, item_status1)
            self.table.setCellWidget(row_idx, 4, self.create_badge(data.get("필기 상태", "없음")))
            
            item_status2 = QTableWidgetItem("")
            item_status2.setForeground(Qt.GlobalColor.transparent)
            self.table.setItem(row_idx, 5, item_status2)
            self.table.setCellWidget(row_idx, 5, self.create_badge(data.get("음성 스크립트 상태", "없음")))
            
            for col_offset, key in enumerate(checkbox_columns):
                is_checked = bool(data.get(key, False))
                item_chk = QTableWidgetItem("")
                item_chk.setForeground(Qt.GlobalColor.transparent)
                self.table.setItem(row_idx, 6 + col_offset, item_chk)
                
                readonly_cb_widget = self.create_readonly_checkbox(is_checked)
                self.table.setCellWidget(row_idx, 6 + col_offset, readonly_cb_widget)
            
            self.table.setRowHeight(row_idx, 44)
            
        self.update_select_all_ui()
        
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.setSortingEnabled(True)


    def on_header_clicked(self, logical_index):
        if logical_index == 0:
            self.table.setSortingEnabled(False) # 0번 열 클릭 시 정렬 기능 OFF
        else:
            self.table.setSortingEnabled(True)  # 다른 열 클릭 시 정렬 기능 ON