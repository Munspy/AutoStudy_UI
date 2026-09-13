"""PDF 파일 병합 작업을 관리하는 ViewModel 모듈입니다.

UI(PdfMergeUi)와 연동하여 병합할 PDF 파일 목록 조회,
미리보기 생성, 실제 병합 작업을 수행하는 워커들을 제어하고 상태를 관리합니다.
"""
import os
import tempfile
from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from worker.pdf import (PdfBatchPreviewPrepareWorker, PdfFileListWorker,
                        PdfMergeWorker, PdfMergePreviewRenderWorker)


class PreviewState:
    """단일 PDF 문서의 미리보기 및 로딩 상태를 보관하는 데이터 클래스."""
    def __init__(self, doc, path, is_drive):
        self.doc = doc
        self.path = path
        self.is_drive = is_drive
        self.total_pages = doc.page_count if doc else 0
        self.loaded_pages = 0
        self.is_loading = False


class PdfMergeViewModel(BaseViewModel):
    """PDF 파일 병합 비즈니스 로직과 상태를 관리하는 ViewModel 클래스."""

    # ===========================
    # [시그널 정의] - 알람 및 진행 시그널
    # ===========================
    file_list_ready = pyqtSignal()
    merge_completed = pyqtSignal(str)
    preview_prepared = pyqtSignal(str)
    preview_finished = pyqtSignal()
    page_rendered = pyqtSignal(str, int, bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths: dict[str, str] = {}
        self.preview_states: dict[str, PreviewState] = {}
        self.drive_cache: dict[str, str] = {}
        self.temp_dir = os.path.join(tempfile.gettempdir(), "antigravity_pdf_cache")
        os.makedirs(self.temp_dir, exist_ok=True)

    def cleanup_preview_states(self):
        """기존 열려있는 MuPDF 문서 핸들을 모두 안전하게 닫습니다."""
        for state in self.preview_states.values():
            if getattr(state, 'doc', None):
                try:
                    state.doc.close()
                except Exception:
                    pass
        self.preview_states.clear()

    # ===========================
    # [파일 목록 조회]
    # ===========================
    def start_fetch_file_list(self, is_drive: bool, target_dir: str, start_str: str, end_str: str):
        """병합 대상이 될 PDF 파일 목록을 조회하는 워커를 실행합니다."""
        self.cleanup_preview_states()
        self.file_paths.clear()

        worker = PdfFileListWorker(is_drive, target_dir, start_str, end_str)
        worker.finished_signal.connect(self._on_file_list_ready)
        self.start_worker(worker)

    def _on_file_list_ready(self, file_paths: dict):
        self.file_paths = file_paths or {}
        self.file_list_ready.emit()

    # ===========================
    # [미리보기 준비]
    # ===========================
    def start_prepare_previews(self, items_to_prepare: list[str], is_drive: bool):
        """목록에 추가된 PDF 파일들의 첫 페이지 미리보기를 일괄 생성하는 워커를 실행합니다."""
        if not items_to_prepare:
            self.preview_finished.emit()
            return

        worker = PdfBatchPreviewPrepareWorker(
            items_to_prepare, self.file_paths, self.drive_cache, self.temp_dir, is_drive
        )
        worker.prepared_signal.connect(self._on_item_prepared)
        worker.finished_signal.connect(self._on_preview_finished)
        self.start_worker(worker)

    def _on_item_prepared(self, item_text, doc, path_or_id, is_drive, local_path):
        self.preview_states[item_text] = PreviewState(doc, path_or_id, is_drive)
        if is_drive and local_path:
            self.drive_cache[path_or_id] = local_path
        self.preview_prepared.emit(item_text)

    def _on_preview_finished(self, _=None):
        self.preview_finished.emit()

    # ===========================
    # [부분 페이지 렌더링]
    # ===========================
    def request_render_pages(self, item_text: str, start_page: int, end_page: int):
        state = self.preview_states.get(item_text)
        if not state:
            return

        local_path = state.path
        if state.is_drive and state.path in self.drive_cache:
            local_path = self.drive_cache[state.path]

        worker = PdfMergePreviewRenderWorker(item_text, local_path, start_page, end_page)
        worker.page_rendered.connect(self.page_rendered.emit)
        self.start_worker(worker)

    # ===========================
    # [PDF 병합 실행]
    # ===========================
    def start_merge(self, selected_items: list[str], save_name: str, save_local: bool, target_dir: str):
        """사용자가 선택한 순서대로 PDF 파일을 병합하는 워커를 실행합니다."""
        if len(selected_items) < 2:
            self.emit_error("오류", "병합할 PDF 파일을 2개 이상 선택해주세요.")
            return

        paths_to_merge = [self.file_paths[t] for t in selected_items if t in self.file_paths]
        if len(paths_to_merge) < 2:
            self.emit_error("오류", "선택된 파일의 유효한 경로를 찾을 수 없습니다.")
            return

        task_data = {
            'paths_to_merge': paths_to_merge,
            'save_name': save_name or "merged.pdf",
            'is_drive': True,
            'save_local': save_local,
            'target_dir': target_dir
        }

        worker = PdfMergeWorker(task_data)
        worker.finished_signal.connect(self.merge_completed.emit)
        self.start_worker(worker)
