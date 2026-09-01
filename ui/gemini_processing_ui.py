"""Gemini AI를 활용한 스크립트 처리 UI 모듈.

이 모듈은 구글 드라이브의 강의록과 음성 스크립트를 기반으로 Gemini AI를 사용하여
교정 스크립트, 요약본, Anki 카드 생성 등의 파이프라인 작업을 일괄 수행하는 화면을 제공합니다.

Classes:
    KeyBadge: API 키와 모델의 사용 및 쿨타임 상태를 보여주는 커스텀 뱃지 위젯.
    GeminiProcessingUi: Gemini 파이프라인 처리를 제어하는 메인 탭 UI.
"""
from PyQt6.QtWidgets import QTableWidget, QCheckBox, QHeaderView
import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from base.base_ui import BaseUI
from base.base_ui_components import LoadingButton, CardWidget, StyledTableWidget, StyledCheckBox, StyledDateEdit

from controller.gemini_processing_controller import GeminiProcessingController
from service.api_key_tracker import api_mgr

# 키 상태 정의 상수
STATE_READY = "READY"        # 🟢 대기 중
STATE_BUSY = "BUSY"          # 🟡 사용 중
STATE_COOLDOWN = "COOLDOWN"  # 🩶 짧은 쿨타임
STATE_DAILY_LIMIT = "DAILY"  # 🔴 일일 한도 초과

class KeyBadge(QWidget):
    """쿨타임 애니메이션이 포함된 API 키 및 모델 상태 뱃지 클래스.
    
    API의 현재 상태(READY, BUSY, COOLDOWN, DAILY)에 따라 색상과 애니메이션을 변경하여
    UI 상단에 키 가용성을 시각적으로 표시합니다.
    
    Attributes:
        name (str): 모델 또는 키의 이름.
        state (str): 현재 상태.
        total_cd (float): 총 쿨타임(초).
        remaining_cd (float): 남은 쿨타임(초).
    """
    def __init__(self, name):
        """KeyBadge 인스턴스를 초기화합니다.
        
        Args:
            name (str): 뱃지에 표시될 모델 또는 키의 이름.
        """
        super().__init__()
        self.name = name
        self.state = STATE_READY
        self.total_cd = 15.0
        self.remaining_cd = 0.0
        self.setFixedSize(36, 36) 

    def set_cooldown(self, remaining, total=15.0):
        self.state = STATE_COOLDOWN
        self.remaining_cd = remaining
        self.total_cd = total
        self.update()

    def set_state(self, state):
        self.state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.state == STATE_READY:
            bg_color, border_color, text_color = QColor("#B7EB8F"), QColor("#52C41A"), QColor("#135200")
        elif self.state == STATE_BUSY:
            bg_color, border_color, text_color = QColor("#FFE58F"), QColor("#FAAD14"), QColor("#873800")
        elif self.state == STATE_DAILY_LIMIT:
            bg_color, border_color, text_color = QColor("#FFA39E"), QColor("#FF4D4F"), QColor("#820014")
        else: # STATE_COOLDOWN
            bg_color, border_color, text_color = QColor("#595959"), QColor("#262626"), QColor("#FFFFFF")

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(rect)

        if self.state == STATE_COOLDOWN and self.total_cd > 0:
            ratio = max(0.0, min(1.0, self.remaining_cd / self.total_cd))
            start_angle = 90 * 16
            span_angle = int(ratio * 360 * 16) 

            painter.save()
            painter.setClipRect(rect)
            diag = int((rect.width()**2 + rect.height()**2)**0.5) + 2
            dx, dy = (diag - rect.width()) / 2, (diag - rect.height()) / 2
            large_rect = rect.adjusted(int(-dx), int(-dy), int(dx), int(dy))

            painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(large_rect, start_angle, span_angle)
            painter.restore()

        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(text_color)

        if self.state == STATE_COOLDOWN:
            display_text = f"{self.remaining_cd:.1f}s"
        else:
            # 뱃지 공간 제약으로 인해 화면 표시용으로 텍스트 축약
            display_text = self.name.replace("gemini-", "").replace("-flash", "")

        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, display_text)

class GeminiProcessingUi(BaseUI):
    """Gemini AI 파이프라인 처리를 제어하는 탭 UI 클래스.
    
    작업 목록 테이블을 통해 드라이브 데이터 상태를 확인하고, API 상태 표시와
    병렬 처리 작업을 스케줄링하는 역할을 합니다.
    
    Attributes:
        controller (GeminiProcessingController): 작업을 처리할 컨트롤러 인스턴스.
        api_keys (list): 등록된 API 키 목록.
        models (list): 사용 가능한 모델 목록.
        badge_widgets (dict): API 키와 모델 조합에 따른 상태 뱃지 위젯 매핑.
    """

    def __init__(self, task_manager=None):
        """GeminiProcessingUi 인스턴스를 초기화합니다.
        
        Args:
            task_manager (optional): 백그라운드 작업을 관리하는 태스크 매니저. 기본값은 None.
        """
        super().__init__(task_manager=task_manager)
        self.controller = GeminiProcessingController(task_manager=self.task_manager)
        self.controller.ui = self
        self.controller.scan_completed.connect(self.handle_scan_result)
        self.controller.cell_update_signal.connect(self.update_task_cell)
        self.controller.error_signal.connect(self.handle_scan_error)
        self.controller.loading_signal.connect(self.handle_loading_state)

        self.api_keys = ["KEY_1", "KEY_2", "KEY_3"]
        self.models = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.7-flash"] 
        
        self.badge_widgets = {}
        self.init_ui()

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(100)
        self.status_timer.timeout.connect(self.update_token_status_ui)
        self.status_timer.start()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            GeminiProcessingUi { background-color: #FFFFFF; }
            QWidget {  color: #37352f; }
            QLabel { background-color: transparent; }
            QCheckBox { background-color: transparent; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        header_label = QLabel("🧠 Gemini AI 스크립트 교정 / 요약 / Anki 생성")
        header_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #111111; padding-bottom: 5px;")
        layout.addWidget(header_label)

        # ===========================
        # [상단 키 상태 및 조회 영역]
        # ===========================
        top_frame = CardWidget()
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(20, 16, 20, 16)
        
        keys_layout = QVBoxLayout()
        keys_layout.setSpacing(10)

        for key_name in self.api_keys:
            key_group = QHBoxLayout()
            key_group.setSpacing(6)
            
            title_lbl = QLabel(f"🔑 {key_name}")
            title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #111111;")
            title_lbl.setFixedWidth(60)
            key_group.addWidget(title_lbl)
            
            self.badge_widgets[key_name] = {}
            for model_name in self.models:
                badge = KeyBadge(model_name)
                key_group.addWidget(badge)
                self.badge_widgets[key_name][model_name] = badge
                
            key_group.addStretch()
            keys_layout.addLayout(key_group)

        top_layout.addLayout(keys_layout)
        top_layout.addStretch()
        
        right_action_layout = QVBoxLayout()
        right_action_layout.setSpacing(8)

        self.force_rerun_cb = StyledCheckBox("강제 재실행", theme="danger")
        self.force_rerun_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.force_rerun_cb.toggled.connect(self.toggle_force_rerun)
        
        scan_row_layout = QHBoxLayout()
        scan_row_layout.setSpacing(10)
        
        self.date_picker = StyledDateEdit(QDate.currentDate())
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setVisible(False)
        
        self.scan_btn = LoadingButton("🔄 작업 상태 및 파일 조회", "primary")
        self.scan_btn.clicked.connect(self.scan_tasks)
        
        scan_row_layout.addWidget(self.date_picker)
        scan_row_layout.addWidget(self.scan_btn)

        right_action_layout.addWidget(self.force_rerun_cb, alignment=Qt.AlignmentFlag.AlignRight)
        right_action_layout.addLayout(scan_row_layout)
        
        top_layout.addLayout(right_action_layout)
        layout.addWidget(top_frame)

        # ===========================
        # [중간 컨트롤 바]
        # ===========================
        mid_bar_layout = QHBoxLayout()
        self.select_all_cb = StyledCheckBox("전체 선택 (All)")
        self.select_all_cb.clicked.connect(self.toggle_all_items)
        mid_bar_layout.addWidget(self.select_all_cb)
        mid_bar_layout.addStretch()
        layout.addLayout(mid_bar_layout)

        # ===========================
        # [작업 테이블 영역]
        # ===========================
        self.table = StyledTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["행 선택", "수업 교시", "강의록", "음성스크립트", "📝 스크립트 교정", "📑 요약본 생성", "🗂️ Anki 카드 생성"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 90)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.table, stretch=1)

        # ===========================
        # [하단 버튼 영역]
        # ===========================
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch() 
        
        self.auto_run_btn = LoadingButton("선택 작업 진행하기", "primary")
        self.auto_run_btn.clicked.connect(self.execute_auto_run)
        bottom_layout.addWidget(self.auto_run_btn)
        
        layout.addLayout(bottom_layout)
        self.populate_real_data()

    def toggle_force_rerun(self, checked):
        self.date_picker.setVisible(checked)

    def update_token_status_ui(self):
        for key_name in self.api_keys:
            for model_name in self.models:
                badge = self.badge_widgets[key_name][model_name]
                
                # 정규식이나 이름 매핑 없이 백엔드의 반환값을 직관적으로 사용
                status, extra = api_mgr.check_combo_status(key_name, model_name)
                
                if status == "COOLDOWN":
                    badge.set_cooldown(extra, total=api_mgr.cooldown_seconds)
                elif status in [STATE_READY, STATE_BUSY, STATE_DAILY_LIMIT]:
                    badge.set_state(status)
                else:
                    # ERROR 또는 NOT_FOUND 등 예외 상태 처리
                    badge.set_state(STATE_READY) 

    def scan_tasks(self):
        if self.force_rerun_cb.isChecked():
            target_date = self.date_picker.date().toString("yyyy-MM-dd")
            self.emit_log(f"[강제 재실행 모드] {target_date} 기준으로 완료 여부와 무관하게 모든 파일을 조회합니다.")
        else:
            self.emit_log("작업 대기열을 스캔했습니다.")
            
        self.populate_real_data()

    # ---------------------------------------------------------
    # 공통 테이블 렌더링 함수
    # ---------------------------------------------------------
    def render_table_data(self, data_list, is_force_rerun):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        for row, data in enumerate(data_list):
            self.table.insertRow(row)
            
            row_chk = self.create_centered_checkbox()
            row_chk.findChild(QCheckBox).stateChanged.connect(lambda state, r=row: self.toggle_row(r, state))
            self.table.setCellWidget(row, 0, row_chk)
            
            item_교시 = QTableWidgetItem(data["교시"])
            item_교시.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item_교시)
            
            self.table.setCellWidget(row, 2, self.create_check_label(data["강의록"], color="#8C8C8C"))
            self.table.setCellWidget(row, 3, self.create_check_label(data["음성스크립트"], color="#8C8C8C"))
            
            self.table.setCellWidget(row, 4, self.create_task_checkbox(data["교정"], data["음성스크립트"], row, 4, is_force_rerun))
            self.table.setCellWidget(row, 5, self.create_task_checkbox(data["요약"], True, row, 5, is_force_rerun))
            self.table.setCellWidget(row, 6, self.create_task_checkbox(data["Anki"], True, row, 6, is_force_rerun))
            
            self.update_row_dependencies(row)
                
        self.table.blockSignals(False)

    # ---------------------------------------------------------
    # [추후 활성화] 실제 데이터를 백엔드(func7)에 요청하고 테이블 갱신
    # ---------------------------------------------------------
    def populate_real_data(self):
        self.emit_log("구글 드라이브에서 실제 데이터를 스캔하는 중입니다. 잠시만 기다려주세요...")
        self.scan_btn.start_loading("조회 중")
                
        is_force_rerun = self.force_rerun_cb.isChecked()
        target_date = self.date_picker.date()
        target_mmdd = target_date.toString("MMdd") # 예: "0409"
        
        self.controller.start_scan(is_force_rerun, target_mmdd)

    def handle_scan_result(self, real_data, is_force_rerun):
        # UI 상태 복구 및 테이블 렌더링
        self.scan_btn.stop_loading()
        self.render_table_data(real_data, is_force_rerun)
        
        if is_force_rerun:
            target_mmdd = self.date_picker.date().toString("MMdd")
            self.emit_log(f"[{target_mmdd}] 일자 드라이브 데이터 스캔 완료! (총 {len(real_data)}건 조회됨)")
        else:
            self.emit_log(f"미완료 드라이브 데이터 전체 스캔 완료! (총 {len(real_data)}건 조회됨)")

    def handle_scan_error(self, err_msg):
        self.scan_btn.stop_loading()
        self.emit_log(f"데이터 스캔 중 오류 발생: {err_msg}")

    def create_check_label(self, is_exist, color="#1890FF"):
        """체크박스 대신 표시할 라벨 생성"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("✔️" if is_exist else "")
        lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;" if is_exist else "")
        layout.addWidget(lbl)
        return container

    def create_centered_checkbox(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb = StyledCheckBox("")
        layout.addWidget(cb)
        return container

    def create_task_checkbox(self, status, has_dependency, row, col, is_force_rerun):
        is_originally_done = (status == "완료")
        
        if is_originally_done and not is_force_rerun:
            return self.create_check_label(True, color="#1890FF")
            
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if is_originally_done and is_force_rerun:
            cb = StyledCheckBox("", theme="danger")
            cb.setEnabled(True)
            cb.setChecked(False) 
        else:
            cb = StyledCheckBox("")
            if not has_dependency:
                cb.setEnabled(False)
        
        cb.setProperty("is_originally_done", is_originally_done)
            
        if col == 4:
            cb.stateChanged.connect(lambda state, r=row: self.update_row_dependencies(r))
            
        layout.addWidget(cb)
        return container

    def update_row_dependencies(self, row):
        w_교정 = self.table.cellWidget(row, 4)
        w_요약 = self.table.cellWidget(row, 5)
        w_anki = self.table.cellWidget(row, 6)
        
        is_교정_ready = False
        if w_교정:
            cb_교정 = w_교정.findChild(QCheckBox)
            if cb_교정:
                if cb_교정.property("is_originally_done"):
                    is_교정_ready = True
                else:
                    is_교정_ready = cb_교정.isChecked()
            else:
                lbl = w_교정.findChild(QLabel)
                if lbl and "✔️" in lbl.text():
                    is_교정_ready = True

        for w in [w_요약, w_anki]:
            if not w: continue
            cb = w.findChild(QCheckBox)
            if not cb: continue 
            
            cb.setEnabled(is_교정_ready)
            if not is_교정_ready: 
                cb.setChecked(False)

    def toggle_row(self, row, state):
        is_checked = (state == 2)
        for col in range(4, 7):
            widget = self.table.cellWidget(row, col)
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb and cb.isEnabled():
                    cb.setChecked(is_checked)

    def toggle_all_items(self):
        is_checked = self.select_all_cb.isChecked()
        for row in range(self.table.rowCount()):
            row_widget = self.table.cellWidget(row, 0)
            if row_widget:
                row_cb = row_widget.findChild(QCheckBox)
                if row_cb: row_cb.setChecked(is_checked)

    def execute_auto_run(self):
        self.emit_log("선택된 작업을 시작합니다. (상태는 api_manager에 의해 제어됩니다)")
        
        available_keys = []
        for k in self.api_keys:
            for m in self.models:
                available_keys.append((k, m))
                
        key_idx = 0
        task_queue = [] # 백그라운드에 넘길 작업 목록
        
        for row in range(self.table.rowCount()):
            # 1열에서 수업 교시(base_name) 가져오기
            base_name_item = self.table.item(row, 1)
            base_name = base_name_item.text() if base_name_item else f"unknown_{row}"

            for col, task_name in zip([4, 5, 6], ["교정", "요약", "Anki"]):
                widget = self.table.cellWidget(row, col)
                if widget:
                    cb = widget.findChild(QCheckBox)
                    if cb and cb.isEnabled() and cb.isChecked():
                        if key_idx < len(available_keys):
                            k_name, m_name = available_keys[key_idx]
                            key_idx = (key_idx + 1) % len(available_keys) # 키 순환
                            
                            # UI를 사용 중(노란 뱃지) 상태로 변경
                            container = QWidget()
                            layout = QHBoxLayout(container)
                            layout.setContentsMargins(0, 0, 0, 0)
                            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                            
                            display_name = f"{k_name.replace('_', '')}_{m_name.replace('gemini-', '').replace('-flash', '')}"
                            lbl = QLabel(display_name)
                            lbl.setStyleSheet("color: #873800; font-weight: bold; font-size: 11px; background-color: #FFE58F; padding: 4px 6px; border-radius: 4px;")
                            layout.addWidget(lbl)
                            
                            self.table.setCellWidget(row, col, container)
                            
                            # 워커가 처리할 작업 정보 저장
                            task_queue.append({
                                'row': row,
                                'col': col,
                                'task_type': task_name,
                                'model': m_name,
                                'base_name': base_name
                            })
                            
        # 워커 스레드를 실행하여 UI 멈춤 방지
        if task_queue:
            self.auto_run_btn.start_loading("작업 진행 중")
            self.controller.start_tasks(task_queue)
        else:
            self.emit_log("실행할 작업이 선택되지 않았습니다.")

    def handle_loading_state(self, is_loading):
        if not is_loading:
            self.auto_run_btn.stop_loading()

    def update_task_cell(self, row, col, status):
        """작업이 끝난 후 테이블 셀을 파란색 체크(완료)로 업데이트"""
        if status == "DONE":
            # 이전에 만들어둔 create_check_label 메서드 재사용
            self.table.setCellWidget(row, col, self.create_check_label(True, color="#1890FF"))
        else:
            self.emit_log(f"[{row}행 {col}열] 작업 실패")

    def emit_log(self, message):
        self.log_signal.emit(message)
        print(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GeminiProcessingUi()
    window.resize(980, 650)
    window.show()
    sys.exit(app.exec())