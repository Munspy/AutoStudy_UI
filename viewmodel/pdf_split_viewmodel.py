"""PDF 파일 분할 작업을 관리하는 ViewModel 모듈입니다.

UI(PdfSplitUi)와 연동하여 분할할 PDF 파일 목록 조회,
미리보기 준비 및 렌더링, 실제 파일 분할 저장을 처리하는 워커를 제어하고 상태를 소유합니다.
"""
import os
import re
import shutil
import tempfile
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from worker.pdf import (PdfFileListWorker, PdfPreviewPrepareWorker,
                        PdfSplitPreviewRenderWorker, PdfSplitWorker)


class PdfSplitViewModel(BaseViewModel):
    """PDF 파일 분할 제어 및 상태를 관리하는 ViewModel 클래스."""

    # ===========================
    # [시그널 정의]
    # ===========================
    file_list_ready = pyqtSignal()
    preview_ready = pyqtSignal()
    page_rendered = pyqtSignal(int, bytes)
    split_completed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.temp_dir = tempfile.mkdtemp()
        
        # 비즈니스 상태
        self.file_paths: dict[str, str] = {}
        self.selected_filename: str = ""
        self.selected_path_or_id: str = ""
        self.selected_is_drive: bool = False
        self.local_path: str = ""
        self.total_pages: int = 0
        self.page_images: list[bytes] = []
        self.recommended_save_names: tuple[str, str] = ("", "")

    def __del__(self):
        if hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def clear_preview_state(self):
        self.local_path = ""
        self.total_pages = 0
        self.page_images.clear()
        self.recommended_save_names = ("", "")

    # ===========================
    # [파일 목록 조회]
    # ===========================
    def start_fetch_file_list(self, is_drive: bool, target_dir: str, start_str: str, end_str: str):
        """분할 대상이 될 PDF 파일 목록을 조회하는 워커를 실행합니다."""
        self.clear_preview_state()
        self.file_paths.clear()

        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        worker.finished_signal.connect(self._on_file_list_ready)
        self.start_worker(worker)

    def _on_file_list_ready(self, file_paths: dict):
        self.file_paths = file_paths or {}
        self.file_list_ready.emit()

    # ===========================
    # [파일 선택 및 미리보기]
    # ===========================
    def select_file(self, filename: str, is_drive: bool):
        self.clear_preview_state()
        path_or_id = self.file_paths.get(filename)
        if not path_or_id:
            return

        self.selected_filename = filename
        self.selected_path_or_id = path_or_id
        self.selected_is_drive = is_drive

        # 파일명 추천 생성
        base, ext = os.path.splitext(filename)
        m = re.search(r'(\d+)_([1-9])([1-9])(.*)', base)
        m2 = re.search(r'(\d+)_([1-9]),([1-9])(.*)', base)
        if m:
            n1 = f"{m.group(1)}_{m.group(2)}{m.group(4)}{ext}"
            n2 = f"{m.group(1)}_{m.group(3)}{m.group(4)}{ext}"
        elif m2:
            n1 = f"{m2.group(1)}_{m2.group(2)}{m2.group(4)}{ext}"
            n2 = f"{m2.group(1)}_{m2.group(3)}{m2.group(4)}{ext}"
        else:
            n1 = f"{base}_Part 1{ext}"
            n2 = f"{base}_Part 2{ext}"
        self.recommended_save_names = (n1, n2)

        # 미리보기 다운로드 워커 실행
        worker = PdfPreviewPrepareWorker(path_or_id, is_drive, self.temp_dir)
        worker.finished_signal.connect(self._on_preview_ready)
        self.start_worker(worker)

    def _on_preview_ready(self, result: dict):
        self.local_path = result.get('local_path', '')
        self.total_pages = result.get('total_pages', 0)
        self.preview_ready.emit()

        # 페이지별 렌더링 시작
        if self.local_path and self.total_pages > 0:
            self.start_render_pages(self.local_path, self.total_pages)

    def start_render_pages(self, local_path: str, total_pages: int):
        worker = PdfSplitPreviewRenderWorker(local_path, total_pages)
        worker.page_rendered.connect(self._on_page_rendered)
        self.start_worker(worker)

    def _on_page_rendered(self, page_idx: int, img_data: bytes):
        self.page_images.append(img_data)
        self.page_rendered.emit(page_idx, img_data)

    # ===========================
    # [PDF 분할 저장]
    # ===========================
    def start_split_and_save(self, split_page_text: str, out1_name: str, out2_name: str, target_dir: str):
        if not self.local_path:
            self.emit_error("오류", "분할할 파일을 선택해주세요.")
            return

        is_overlap = False
        text = split_page_text.strip()
        if text.startswith('!'):
            is_overlap = True
            text = text[1:]
            
        try:
            split_page = int(text)
        except ValueError:
            self.emit_error("오류", "정확히 1개의 기준 페이지 번호(분할 지점)를 입력해주세요. (예: 3 또는 !3)")
            return

        if split_page <= 0 or split_page >= self.total_pages:
            self.emit_error("오류", f"분할 페이지 번호가 범위를 벗어났습니다. (1~{self.total_pages-1})")
            return

        if not out1_name.endswith('.pdf'): out1_name += '.pdf'
        if not out2_name.endswith('.pdf'): out2_name += '.pdf'

        worker = PdfSplitWorker(
            local_path=self.local_path,
            split_page=split_page,
            out1_name=out1_name,
            out2_name=out2_name,
            is_drive=True,
            target_dir=target_dir,
            original_id=self.selected_path_or_id,
            original_is_drive=self.selected_is_drive,
            is_overlap=is_overlap
        )
        worker.finished_signal.connect(self.split_completed.emit)
        self.start_worker(worker)

    def delete_selected_file(self):
        """선택된 원본 파일을 삭제합니다."""
        if not self.selected_path_or_id:
            return
        self.app.file.delete_files(
            file_paths_or_ids=[self.selected_path_or_id],
            is_drive=self.selected_is_drive,
            log_callback=GlobalLogger.info
        )
