"""Raw Data 편집기 탭의 백엔드 로직을 처리하는 컨트롤러 모듈입니다.

UI(RawDataEditorUi)와 연동되어 구글 드라이브 검색, 파일 다운로드, 
텍스트 파싱, PyMuPDF를 활용한 PDF 페이지 고속 렌더링 등을 제어합니다.
"""
import io
import re
import os
import pymupdf
from typing import Any, Optional, Dict
from PyQt6.QtCore import pyqtSignal, QObject

from base.base_controller import BaseController
from utils.auth_util import get_drive_service
from utils.config import Config
from worker.raw_data_worker import RawDataLoadWorker, RawDataApplyWorker

class RawDataEditorControllerSignals(QObject):
    """컨트롤러에서 UI로 보내는 시그널 정의."""
    log_signal = pyqtSignal(str)
    pdf_page_rendered = pyqtSignal(bytes, int, int) # image_bytes, current, total
    text_loaded = pyqtSignal(str)
    loading_started = pyqtSignal()
    loading_finished = pyqtSignal()
    apply_started = pyqtSignal()
    apply_finished = pyqtSignal(bool) # 성공 여부 반환
    

class RawDataEditorController(BaseController):
    """Raw Data 에디터 작업을 관리하는 컨트롤러 클래스."""
    
    def __init__(self, task_manager=None):
        super().__init__(task_manager)
        
        # 시그널 객체 초기화
        self.signals = RawDataEditorControllerSignals()
        
        # 내부 상태
        self.drive_service = get_drive_service()
        self.pdf_doc = None
        self.text_dict: Dict[int, str] = {}
        self.original_text_dict: Dict[int, str] = {}
        self.current_page = 1
        self.total_pages = 0
        
        self.text_file_id = None
        self.text_file_parent_id = None
        self.text_file_name = None

    # 시그널 프록시
    @property
    def log_signal(self): return self.signals.log_signal
    @property
    def pdf_page_rendered(self): return self.signals.pdf_page_rendered
    @property
    def text_loaded(self): return self.signals.text_loaded
    @property
    def loading_started(self): return self.signals.loading_started
    @property
    def loading_finished(self): return self.signals.loading_finished
    @property
    def apply_started(self): return self.signals.apply_started
    @property
    def apply_finished(self): return self.signals.apply_finished

    def log(self, message: str):
        self.log_signal.emit(message)

    def search_and_load(self, date_str: str, period_str: str):
        self.loading_started.emit()
        
        worker = RawDataLoadWorker(date_str, period_str, self.drive_service)
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(self._on_load_finished)
        worker.error_signal.connect(self._on_load_error)
        
        self.task_manager.add_task(worker)

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
                self.pdf_doc.close()
            
            self.pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            self.total_pages = len(self.pdf_doc)
            
            self._parse_text_content(text_str)
            self.log(f"✅ 로딩 완료! 총 {self.total_pages}장의 슬라이드 및 텍스트 매핑 완료.")
            
            self.current_page = 1
            self._render_and_emit_page(self.current_page)
        except Exception as e:
            self.log(f"❌ 데이터 파싱 중 오류: {str(e)}")
        finally:
            self.loading_finished.emit()

    def _on_load_error(self, error_msg: str):
        self.log(f"❌ 로딩 중 오류 발생: {error_msg}")
        self.loading_finished.emit()

    def _parse_text_content(self, text: str):
        from utils.text_util import parse_slide_text
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
            self.log("❌ 오류: 업로드할 원본 텍스트 파일 정보가 없습니다.")
            self.apply_finished.emit(False)
            return
            
        self.log("🚀 전체 텍스트 조합 및 구글 드라이브 업로드 준비 중...")
        self.apply_started.emit()
        
        worker = RawDataApplyWorker(
            self.text_dict, self.total_pages, 
            self.text_file_id, self.text_file_name, 
            self.text_file_parent_id, self.drive_service
        )
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(lambda res: self.apply_finished.emit(True))
        worker.error_signal.connect(self._on_apply_error)
        
        self.task_manager.add_task(worker)

    def _on_apply_error(self, error_msg: str):
        self.log(f"❌ 최종 반영 중 오류 발생: {error_msg}")
        self.apply_finished.emit(False)
