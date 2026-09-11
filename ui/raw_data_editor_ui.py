"""Raw Data를 직접 수정하는 UI 모듈.

이 모듈은 구글 드라이브에 저장된 원본 PDF 파일과 `_최종교정본.txt` 파일을 불러와서
좌/우 또는 상/하로 분할된 뷰에서 텍스트를 검토하고 수정할 수 있는 기능을 제공합니다.
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QAbstractSpinBox, QHBoxLayout, QLabel, QSplitter,
                             QTextEdit, QVBoxLayout, QWidget)

from base.base_ui import BaseUI
from base.base_ui_components import (CardWidget, LabeledInput, LoadingButton,
                                     SearchLineEdit, StyledButton,
                                     StyledDateEdit)
from controller.raw_data_editor_controller import RawDataEditorController


class ResizablePixmapLabel(QLabel):
    """창 크기에 맞춰 이미지를 꽉 차게(비율 유지) 줄이거나 늘려주는 라벨입니다."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 100) # 줄어들 때 사라짐 방지

    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        super().setPixmap(self._scaled_pixmap())

    def resizeEvent(self, event):
        if self._pixmap:
            super().setPixmap(self._scaled_pixmap())
        super().resizeEvent(event)
        
    def _scaled_pixmap(self):
        if not self._pixmap:
            return QPixmap()
        return self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class RawDataEditorUi(BaseUI):
    """raw data 직접수정을 위한 UI 클래스."""
    
    def __init__(self, task_manager=None, parent=None):
        super().__init__(task_manager=task_manager)
        
        self.controller = RawDataEditorController(task_manager=self.task_manager)
        
        # 컨트롤러 시그널 연결
        self.controller.log_signal.connect(self.emit_log)
        self.controller.pdf_page_rendered.connect(self.update_pdf_viewer)
        self.controller.text_loaded.connect(self.update_text_editor)
        self.controller.loading_started.connect(lambda: self.btn_search.start_loading())
        self.controller.loading_finished.connect(lambda: self.btn_search.stop_loading())
        self.controller.apply_started.connect(lambda: self.btn_apply.start_loading())
        self.controller.apply_finished.connect(lambda success: self.btn_apply.stop_loading())
        
        self.init_ui()

    def init_ui(self):
        """UI 기본 속성 및 레이아웃을 설정합니다."""
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            RawDataEditorUi { background-color: #FFFFFF; }
            QWidget { color: #37352f; }
            QLabel { background-color: transparent; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)

        # 제목
        header_label = QLabel("📝 Raw Data 편집 (드라이브 연동)")
        header_label.setStyleSheet("font-size: 24px; font-weight: 800; color: #111111; padding: 5px 0px 10px 0px;")
        layout.addWidget(header_label)

        # ===========================
        # [상단 컨트롤 영역 (날짜, 교시 입력)]
        # ===========================
        control_frame = CardWidget()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(20, 16, 20, 16)
        control_layout.setSpacing(15)

        # 검색 날짜 컴포넌트
        self.input_date = StyledDateEdit(QDate.currentDate())
        self.input_date.setDisplayFormat("MM-dd")
        self.input_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.input_date.setCalendarPopup(True)
        self.input_date.setFixedWidth(120)
        
        # 교시 입력 컴포넌트
        self.input_period = SearchLineEdit(placeholder="12")
        self.input_period.setFixedWidth(120)

        # LabeledInput으로 래핑
        control_layout.addWidget(LabeledInput("검색 날짜", self.input_date))
        control_layout.addWidget(LabeledInput("교시 입력", self.input_period))

        self.btn_search = LoadingButton("불러오기")
        self.btn_search.clicked.connect(self.search_and_load)
        
        # 버튼 위아래 여백을 맞추기 위해 래퍼를 사용하거나 수직 정렬을 맞춤
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(0, 18, 0, 0)
        btn_layout.addWidget(self.btn_search)
        
        control_layout.addLayout(btn_layout)
        control_layout.addStretch()

        layout.addWidget(control_frame)

        # ===========================
        # [메인 에디터 영역 (Splitter)]
        # ===========================
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, stretch=1)

        # 1. 좌측 PDF 뷰어 영역 (꽉 차게 보이도록 설정)
        pdf_container = QWidget()
        pdf_container.setStyleSheet("background-color: #F8F9FA; border: 1px solid #EAEAEA; border-radius: 8px;")
        pdf_layout = QVBoxLayout(pdf_container)
        pdf_layout.setContentsMargins(10, 10, 10, 10)
        
        self.pdf_label = ResizablePixmapLabel("PDF 페이지가 이곳에 꽉 차게 표시됩니다.")
        pdf_layout.addWidget(self.pdf_label)
        
        self.splitter.addWidget(pdf_container)

        # 2. 우측 텍스트 에디터 영역
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("선택한 슬라이드의 추출 텍스트가 표시됩니다.")
        self.text_edit.setStyleSheet("border: 1px solid #EAEAEA; border-radius: 8px; padding: 10px; font-size: 14px;")
        self.text_edit.textChanged.connect(self.on_text_changed)
        text_layout.addWidget(self.text_edit)
        
        self.splitter.addWidget(text_container)
        
        # Splitter 비율 설정 (5:5)
        self.splitter.setSizes([600, 600])

        # ===========================
        # [하단 네비게이션 및 액션 버튼]
        # ===========================
        bottom_layout = QHBoxLayout()
        
        self.btn_prev = StyledButton("◀ 이전", btn_type="secondary")
        self.btn_prev.clicked.connect(self.on_prev_page)
        
        self.lbl_page = QLabel("Page: - / -")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page.setFixedWidth(100)
        
        self.btn_next = StyledButton("다음 ▶", btn_type="secondary")
        self.btn_next.clicked.connect(self.on_next_page)
        
        bottom_layout.addWidget(self.btn_prev)
        bottom_layout.addWidget(self.lbl_page)
        bottom_layout.addWidget(self.btn_next)
        bottom_layout.addStretch()
        
        self.btn_discard = StyledButton("복구(버리기)", btn_type="danger")
        self.btn_discard.setEnabled(False)
        self.btn_discard.clicked.connect(self.on_discard)
        
        self.btn_save_local = StyledButton("임시 저장", btn_type="primary")
        self.btn_save_local.setEnabled(False)
        self.btn_save_local.clicked.connect(self.on_save_local)
        
        self.btn_apply = LoadingButton("최종 반영")
        self.btn_apply.clicked.connect(self.on_apply)
        
        bottom_layout.addWidget(self.btn_discard)
        bottom_layout.addWidget(self.btn_save_local)
        bottom_layout.addWidget(self.btn_apply)
        
        layout.addLayout(bottom_layout)

    def search_and_load(self):
        """입력된 날짜와 교시로 파일 검색 및 로딩을 시작합니다."""
        date_str = self.input_date.date().toString("MMdd")
        period_str = self.input_period.text().strip()
        if not date_str or not period_str:
            self.emit_log("날짜와 교시를 모두 입력해주세요.")
            return
            
        self.controller.search_and_load(date_str, period_str)
        self.text_edit.clear()
        self.pdf_label.setPixmap(QPixmap())
        self.pdf_label.setText("로딩 중...")

    def update_pdf_viewer(self, image_data, current_page, total_pages):
        """컨트롤러에서 전달받은 렌더링된 이미지로 PDF 뷰어를 업데이트합니다."""
        if image_data:
            image = QImage.fromData(image_data)
            pixmap = QPixmap.fromImage(image)
            self.pdf_label.setPixmap(pixmap)
        else:
            self.pdf_label.setPixmap(QPixmap())
            self.pdf_label.setText("PDF 이미지가 없습니다.")
            
        self.lbl_page.setText(f"Page: {current_page} / {total_pages}")
        
    def update_text_editor(self, text):
        """컨트롤러에서 전달받은 텍스트로 에디터를 업데이트합니다."""
        self.text_edit.blockSignals(True)
        self.text_edit.setPlainText(text)
        self.text_edit.blockSignals(False)
        self.btn_save_local.setEnabled(True)
        self.btn_discard.setEnabled(True)

    def on_text_changed(self):
        """텍스트 에디터 내용 변경 이벤트 처리."""

    def on_prev_page(self):
        if self.controller.pdf_doc:
            self.on_save_local(silent=True)
            self.controller.change_page(-1)

    def on_next_page(self):
        if self.controller.pdf_doc:
            self.on_save_local(silent=True)
            self.controller.change_page(1)

    def on_save_local(self, silent=False):
        """수정된 텍스트를 컨트롤러 메모리에 임시 저장합니다."""
        text = self.text_edit.toPlainText()
        self.controller.save_current_page_text(text)
        if not silent:
            self.emit_log("현재 페이지 변경사항이 임시 저장되었습니다.")

    def on_discard(self):
        """가장 처음 드라이브에서 가져왔던 원본 텍스트 상태로 복구합니다."""
        self.controller.reload_current_page_text()
        self.emit_log("가장 처음 다운로드 받은 원본 상태로 복구되었습니다.")

    def on_apply(self):
        """모든 변경사항을 하나로 합쳐 드라이브에 업로드합니다."""
        if not self.controller.pdf_doc:
            self.emit_log("먼저 파일을 불러오세요.")
            return
            
        # 현재 화면에 수정 중인 사항도 저장
        self.on_save_local(silent=True)
            
        self.controller.apply_all_changes()
