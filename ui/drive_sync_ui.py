from PyQt6.QtWidgets import QTableWidget, QHeaderView
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableWidgetItem, QLabel, QHeaderView,
                             QAbstractSpinBox, QFileDialog)
from PyQt6.QtCore import Qt, QDate

from base.base_ui import BaseUI
from base.base_ui_components import (LoadingButton, StyledButton, CardWidget, 
                                     StyledTableWidget, StyledCheckBox, StyledComboBox, 
                                     StyledDateEdit, StatusBadge)
from controller.drive_sync_controller import DriveSyncController  # 👈 이제 Thread가 아닌 Func만 바라봄

class DriveSyncUi(BaseUI):
    def __init__(self, task_manager=None):             # 처음 생성될 때의 초기값. UI다 보니 따로 변수를 받지는 않음
        super().__init__(task_manager=task_manager)        
        default_path = os.path.expanduser("~/Downloads")
            # 로컬 검색의 기본값은 Downloads 폴더, 윈도우에서는 카카오톡 폴더를 주로 쓸 것으로 보임
        self.local_download_path = self.load_setting("local_download_path", default_path)
            # QSettings을 뒤져서 local_download_path가 있으면 그걸 반환하고
            # 아니면 default_path를 사용 (BaseUI 메서드 활용)
        
        # 👈 UI를 위한 컨트롤러 생성 및 시그널 연결
        self.controller = DriveSyncController(task_manager=self.task_manager)
        self.controller.sync_completed.connect(self.update_table)
        self.controller.error_signal.connect(self.show_error)
        self.controller.sync_finished.connect(self.reset_search_btn)
        self.controller.log_signal.connect(self.emit_log)
        
        self.init_ui()      # __init__가 자동 실행되고 이어서 실행되는 기본 UI

    def init_ui(self):      # __init__가 자동 실행되고 이어서 실행되는 기본 UI
        # --- 배경에 흰색 칠하기 ---
        # QWidget, QLabel, QCheckBox 등에 사용할 기본 설정 정하기
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            DriveSyncUi {
                background-color: #FFFFFF;
            }
            QWidget {
                
                color: #37352f;
            }
            QLabel, QCheckBox {
                background-color: transparent;
                border: none;
            }
        """)

        # --- 전체적인 구조 설정  ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)   # 바깥쪽에 딱 붙지 않도록 살짝 여유
        layout.setSpacing(20)                       # 구조물들 사이 간격

        # --- 제목 레이아웃  ---
        header_label = QLabel("📚 강의 데이터 파이프라인 상태")
        header_label.setStyleSheet("""
            font-size: 24px; font-weight: 800; color: #111111; 
            padding: 5px 0px 10px 0px; 
            background: transparent; border: none;
        """)
        layout.addWidget(header_label)

        # --- 상단 필터 영역 (연한 회색 배경) ---
            # 이게 이번 프로젝트 기준 설정 부위 양식
        control_frame = CardWidget()

        # 프레임 위에는 수평 레이아웃(QHBoxLayout)을 배치하여 요소들을 좌에서 우로 정렬
            # 약간의 마진과 구조물들 사이 간격도 설정
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(15)

        # 1. 첫번째 구조물: "시험 기준:""
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("시험 기준:"))

        # 2. 두번째 구조물: 선택지가 있는 리본박스
        self.exam_combo = StyledComboBox()

            # 사용안함은 고정
            # 나머지는 드라이브의 전체 폴더 구조를 보고 정하는 것인데 현재는 목업 데이터
        self.exam_combo.addItems(["사용 안함", "Block 1 : 심혈관계/1차"])
            # ----- 수정 필요!!!!!!!!!!!!!!!! -----
            # 폴더 구조는 언제마다 읽어야 할까?

        # 1 + 2. 첫번쨰 구조물 바로 옆으로 두번쨰 구조물을 붙임
            # 왼쪽 정렬시킬 구조물들은 앞으로도 다 이런식으로 붙임
        filter_layout.addWidget(self.exam_combo)

        # 다음 구조물 전의 Seperator
        separator = QLabel("  |  ")
        separator.setStyleSheet("color: #D1D1CE; font-weight: normal; font-size: 16px;")
        filter_layout.addWidget(separator)

        # 3. 세번째 구조물: "날짜 범위:"
        self.date_label = QLabel("날짜 범위:")
        filter_layout.addWidget(self.date_label)

        # 4. 네번째 구조물: 날짜 범위 시작 ~ 날짜 범위 끝
        today = QDate.currentDate()     # 기본값: 오늘

        # 기본값으로 오늘 날짜를 사용
        self.start_date = StyledDateEdit()
        self.start_date.setDate(today)
        self.start_date.setDisplayFormat("MM-dd")
        self.start_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.start_date.setCalendarPopup(True)

        # 기본값으로 오늘 날짜를 사용
        self.end_date = StyledDateEdit()
        self.end_date.setDate(today)
        self.end_date.setDisplayFormat("MM-dd")
        self.end_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.end_date.setCalendarPopup(True)

        # 날짜 시작 ~ 날짜 끝
        # ex. 08-26 ~ 08-26
        filter_layout.addWidget(self.start_date)
        filter_layout.addWidget(QLabel("~"))
        filter_layout.addWidget(self.end_date)
        
        # 사용자가 '시험 기준' 드롭다운 목록에서 다른 항목을 선택하여 글자가 바뀌는 순간 발생하는 이벤트
            # self.exam_combo.currentTextChanged
        # 이벤트가 트리거하는 toggle_date_inputs
            # .connect(self.toggle_date_inputs)
                # toggle_date_inputs():
                # 현재 어떤 과목으로 설정되어 있는지 확인하고 날짜 선택을 활성화/비활성화 결정
        # 즉 과목을 바꿀 때마다 날짜 선택 허용/제한 토글하는 함수
        self.exam_combo.currentTextChanged.connect(self.toggle_date_inputs)
        
        # filter_layout에 차곡차곡 옆으로 쌓아놓은 구조물들을 control_layout에 통채로 오른쪽 정렬로 넣기
        control_layout.addLayout(filter_layout)

        # 가변 여백(스프링) 추가
        control_layout.addStretch()

        # 가변 여백 후 오른쪽으로 정렬된 버튼
        self.btn_set_folder = QPushButton("📂 LOCAL")

        # 버튼에 커서가 올라가면 모양이 바뀜
        self.btn_set_folder.setCursor(Qt.CursorShape.PointingHandCursor)

        # 버튼의 기본 스타일 + hover 상태(커서가 올라간)에서 색상이 바뀜
        self.btn_set_folder.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D1CE; 
                border-radius: 6px; padding: 6px 12px; color: #555555; font-weight: bold;
            }
            QPushButton:hover { background-color: #F8F9FA; }
        """)

        # 버튼이 눌리면 set_local_folder가 실행됨
            # set_local_folder: 로컬 path를 업데이트 하는 코드
            # 현재 사용하고 있는 'local_download_path' + 'setting의 local_download_path'를 업데이트
        self.btn_set_folder.clicked.connect(self.set_local_folder)

        # 이것저것 설정이 끝난 "btn_set_folder"을 마지막으로 붙이기
        control_layout.addWidget(self.btn_set_folder)

        # control_frame 위에 존재하던 control_layout 설정이 완료됐으니 통채로 슛~~
        layout.addWidget(control_frame)
        
        # --- 중간 액션바 ---
            # 1. 전체 선택/해제
            # 2. 데이터 동기화 및 조회
        
        # 비슷한 느낌으로 일단 박스 만들고 테두리 살짝 비워주기
        mid_bar_layout = QHBoxLayout()
        mid_bar_layout.setContentsMargins(5, 5, 5, 5)

        # 1. 전체 선택
        self.select_all_cb = StyledCheckBox("전체 선택")
        # 클릭되면 '알아서 잘' 전체선택/해제 : toggle_all_rows_smart
        self.select_all_cb.clicked.connect(self.toggle_all_rows_smart)

        # @@@ 1. 전체 선택 / 해제 배치 @@@
        mid_bar_layout.addWidget(self.select_all_cb)

        # @@@ 1과 2 사이의 빈 공간을 채울 가변 박스 배치 @@@
        mid_bar_layout.addStretch()

        # 2. 데이터 동기화 및 조회
        self.search_btn = LoadingButton(" 데이터 동기화 및 조회", "primary")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)    # 갖다대면 커서 모양이 바뀜
        # 기본 양식 + 커서 갖다댔을 때 색상 + 눌렸을 때 대기중인 색상 설정
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #2383E2; border: none; 
                border-radius: 8px; padding: 12px 28px; color: white; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background-color: #1A6FB0; }
            QPushButton:disabled { background-color: #A5C9F3; }
        """)
       
        # 누르면 execute_search_log 실행 (이제 Func를 부름)
        self.search_btn.clicked.connect(self.execute_search_log)

        # @@@ 2. 데이터 동기화 및 조회 배치 @@@
        mid_bar_layout.addWidget(self.search_btn)

        # 차곡차곡 쌓은 두 액션담당 버튼들을 가운데에 배치!
        layout.addLayout(mid_bar_layout)

        # --- 테이블 영역 ---

        # 초기 행(Row)은 0개, 열(Column)은 10개인 표 틀 만들기
        self.table = StyledTableWidget(0, 10)

        # 각 열의 상단 제목 일괄 등록
        self.table.setHorizontalHeaderLabels([
            "", "수업 교시", "교수", "강의명", "필기", "음성 스크립트", 
            "최종교정본", "요약본", "Anki", "스크립트 합본"
        ])

        # 원래 있는 기능으로 'alternate-background-color' 설정해놨으니 알아서 잘해줌 bb
        self.table.setAlternatingRowColors(True)

        # 대충 가로 사이즈들 지정, '강의명'은 남는 거 채우는 식이라 지정 안되어 있음!
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 180)
        for i in range(6, 10): self.table.setColumnWidth(i, 90)

        # 기타 설정들...
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # '강의명'이 가변적으로 늘어남
        self.table.verticalHeader().setVisible(False)                                           # 행 번호 (1,2,3...) 숨김
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)                     # 눌러도 수정 안됨
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)                     # 눌러도 선택 안됨(드래그)
        self.table.setShowGrid(False)                                                           # 선 숨김
        self.table.setSortingEnabled(True)                                                      # 헤더 선택 시 정렬 가능
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)            # 단, on_header_clicked을 통해 0번 열은 통제
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)                                 # 기본적으로는 날짜_교시 로 정렬

        # 체크박스가 변하면 자동으로 '전체선택'의 모습이 업데이트
        # self.update_select_all_ui() => '전체선택'의 모습이 업데이트
        self.table.itemChanged.connect(self.check_individual_row_state)

        # @@@ 이제 표도 넣었고 마지막으로 ㄱㄱ
        layout.addWidget(self.table)
        
        # --- 하단 액션 버튼 ---
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 큰 버튼들 모양 지정
        
        btn_run_local = StyledButton("누락 로컬 작업 실행", "save")
        
        
        btn_run_local.clicked.connect(self.controller.execute_local_tasks)
        actions_layout.addWidget(btn_run_local)

        btn_run_whisper = StyledButton("🎙️ Whisper AI 전사", "whisper")
        
        
        btn_run_whisper.clicked.connect(self.controller.execute_whisper_transcription)
        actions_layout.addWidget(btn_run_whisper)

        btn_dl_script = StyledButton("💾 스크립트 합본 다운로드", "important")
        
        
        btn_dl_script.clicked.connect(self.controller.download_script_merged)
        actions_layout.addWidget(btn_dl_script)
        
        actions_layout.addStretch() 

        # 작은 버튼들 모양 지정
        btn_dl_summary = StyledButton("📝 요약본 다운로드", "trivia")
        btn_dl_anki = StyledButton("🗂️ Anki 다운로드", "trivia")
        actions_layout.addWidget(btn_dl_summary)
        actions_layout.addWidget(btn_dl_anki)
        
        # 👈 컨트롤러 호출로 변경
        btn_dl_summary.clicked.connect(self.controller.download_summary)
        btn_dl_anki.clicked.connect(self.controller.download_anki)

        layout.addLayout(actions_layout)
        layout.addLayout(actions_layout)

    # --- 기능 메서드 ---
    def set_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "로컬 검색 폴더 선택", self.local_download_path)
        if folder:
            self.local_download_path = folder
            self.save_setting("local_download_path", folder)  # BaseUI의 save_setting 헬퍼 활용
            self.emit_log(f"설정 완료: 검색 폴더가 [{folder}] (으)로 변경되었습니다.")

    def toggle_date_inputs(self, text):
        is_disabled = (text != "사용 안함")
        self.start_date.setEnabled(not is_disabled)
        self.end_date.setEnabled(not is_disabled)

    def execute_search_log(self):
        """ 🔄 변경점: 직접 Thread를 부르는 대신 Controller(Func)에게 지시를 내립니다. """
        current_exam = self.exam_combo.currentText()
        self.search_btn.start_loading("조회 중")
        
        if current_exam == "사용 안함":
            start = self.start_date.date().toString("yyyy-MM-dd")
            end = self.end_date.date().toString("yyyy-MM-dd")
            display_start = self.start_date.date().toString("MM-dd")
            display_end = self.end_date.date().toString("MM-dd")
            
            search_mode = "DATE"
            filter_value = (start, end)
            self.emit_log(f"기간 [{display_start} ~ {display_end}] 기준으로 구글 드라이브 동기화 조회를 시작합니다...")
        else:
            search_mode = "EXAM"
            filter_value = current_exam
            self.emit_log(f"시험 기준 [{current_exam}] (으)로 최신 상태를 백그라운드에서 불러옵니다...")

        # 👈 매니저(Controller)야, 스레드 띄워서 일 좀 처리해 줘!
        self.controller.execute_sync(search_mode, filter_value, self.local_download_path)

    def reset_search_btn(self):
        self.search_btn.stop_loading()

    def handle_worker_error(self, err):
        self.emit_log(f"[오류 발생] {err}")

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

    def update_table(self, data_list):
        self.emit_log(f"총 {len(data_list)}건의 강의 데이터를 성공적으로 불러왔습니다.")
        
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