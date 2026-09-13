"""Raw Data 편집기 탭의 백엔드 로직을 처리하는 ViewModel 모듈입니다.

UI(RawDataEditorUi)와 연동되어 구글 드라이브 검색, 파일 다운로드, 
텍스트 파싱, PyMuPDF를 활용한 PDF 페이지 고속 렌더링 등을 제어하고 상태를 관리합니다.
"""
from typing import Dict

import pymupdf
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from core.config import Config
from utils.text_util import parse_slide_text
from worker.raw_data_worker import RawDataApplyWorker, RawDataLoadWorker


class RawDataEditorViewModel(BaseViewModel):
    """Raw Data 에디터 상태 및 작업을 관리하는 ViewModel 클래스."""

    # 고유 시그널 정의
    pdf_page_rendered = pyqtSignal(bytes, int, int)  # image_bytes, current, total
    text_loaded = pyqtSignal(str)
    apply_completed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 내부 상태
        self.pdf_doc = None
        self.text_dict: Dict[int, str] = {}
        self.original_text_dict: Dict[int, str] = {}
        self.current_page = 1
        self.total_pages = 0
        
        self.text_file_id = None
        self.text_file_parent_id = None
        self.text_file_name = None

    def log(self, message: str):
        GlobalLogger.info(message)

    def search_and_load(self, date_str: str, period_str: str):
        worker = RawDataLoadWorker(date_str, period_str)
        worker.finished_signal.connect(self._on_load_finished)
        self.start_worker(worker)

    def _on_load_finished(self, result: dict):
        try:
            pdf_bytes = result["pdf_bytes"]
            text_str = result["text_str"]
            text_file = result["text_file"]
            
            self.text_file_id = text_file['id']
            parents = text_file.get('parents', [])
            self.text_file_parent_id = parents[0] if parents else Config.TARGET_DRIVE_DIR
            self.text_file_name = text_file['name']
            
            if self.pdf_doc:
                try:
                    self.pdf_doc.close()
                except Exception:
                    pass
            
            self.pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            self.total_pages = len(self.pdf_doc)
            
            self._parse_text_content(text_str)
            self.log(f"✅ 로딩 완료! 총 {self.total_pages}장의 슬라이드 및 텍스트 매핑 완료.")
            
            self.current_page = 1
            self._render_and_emit_page(self.current_page)
        except Exception as e:
            self.log(f"❌ 데이터 파싱 중 오류: {str(e)}")
            self.emit_error("오류", f"데이터 파싱 중 오류: {str(e)}")

    def _parse_text_content(self, text: str):
        self.text_dict = parse_slide_text(text)
        self.original_text_dict = self.text_dict.copy()
            
    def _render_and_emit_page(self, page_num: int):
        if not self.pdf_doc or page_num < 1 or page_num > self.total_pages:
            return
            
        try:
            page = self.pdf_doc[page_num - 1]
            pix = page.get_pixmap(dpi=144)
            img_bytes = pix.tobytes("png")
            
            self.pdf_page_rendered.emit(img_bytes, page_num, self.total_pages)
            text = self.text_dict.get(page_num, "(내용 없음)")
            self.text_loaded.emit(text)
        except Exception as e:
            self.log(f"❌ 페이지 렌더링 오류: {str(e)}")

    def change_page(self, delta: int):
        if not self.pdf_doc: return
        new_page = self.current_page + delta
        if 1 <= new_page <= self.total_pages:
            self.current_page = new_page
            self._render_and_emit_page(self.current_page)

    def save_current_page_text(self, text: str):
        self.text_dict[self.current_page] = text

    def reload_current_page_text(self):
        text = self.original_text_dict.get(self.current_page, "(내용 없음)")
        self.text_dict[self.current_page] = text
        self.text_loaded.emit(text)

    def apply_all_changes(self):
        if not self.text_file_id:
            self.emit_error("오류", "업로드할 원본 텍스트 파일 정보가 없습니다.")
            self.apply_completed.emit(False)
            return
            
        self.log("🚀 전체 텍스트 조합 및 구글 드라이브 업로드 준비 중...")
        worker = RawDataApplyWorker(
            self.text_dict, self.total_pages, 
            self.text_file_id, self.text_file_name, 
            self.text_file_parent_id
        )
        
        def _on_apply_success(res):
            if isinstance(res, str):
                self.text_file_id = res
            self.apply_completed.emit(True)
            
        worker.finished_signal.connect(_on_apply_success)
        self.start_worker(worker)
