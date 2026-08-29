# controller/pdf_split_controller.py
import os
import tempfile
import shutil
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt

import pymupdf

from utils.file_util import list_local_files
from utils.auth_util import get_drive_service
from utils.drive_api import (
    get_all_drive_files,
    download_from_drive,
)
from utils.config import Config
from service.pdf_operation_service import PdfOperationService

class PdfSplitController:
    def __init__(self, ui_instance):
        self.ui = ui_instance
        self.file_paths = {}
        self.temp_dir = tempfile.mkdtemp()
        self.drive_cache = {}
        self.current_pdf_path = None
        self.total_pages = 0

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def populate_file_list(self):
        """UI 설정에 따라 로컬 혹은 드라이브에서 파일을 조회합니다."""
        self.ui.file_list.blockSignals(True)
        self.ui.file_list.clear()
        self.file_paths.clear()
        self.ui.clear_preview()

        is_drive = self.ui.drive_check.isChecked()

        if not is_drive:
            target_dir = self.ui.folder_input.text()
            if not os.path.exists(target_dir):
                self.ui.log_signal.emit("❌ 대상 폴더가 존재하지 않습니다.")
                self.ui.file_list.blockSignals(False)
                return

            files = list_local_files(target_dir, extension=".pdf")
            if not files:
                self.ui.log_signal.emit("⚠️ 폴더 내에 PDF 파일이 없습니다.")
                self.ui.file_list.blockSignals(False)
                return

            for f in sorted(files):
                item_text = f"📄 {f}"
                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.ui.file_list.addItem(item)
                self.file_paths[item_text] = os.path.join(target_dir, f)

            self.ui.log_signal.emit(f"✅ 로컬 폴더에서 {len(files)}개의 PDF를 불러왔습니다.")

        else:
            self.ui.log_signal.emit("🔄 구글 드라이브에서 조건에 맞는 PDF 파일을 조회 중입니다...")
            try:
                drive_service = get_drive_service()
                try:
                    folder_id = Config.TARGET_DRIVE_DIR
                except ValueError:
                    self.ui.log_signal.emit("❌ .env 설정 오류: TARGET_DRIVE_DIR 폴더 ID를 찾을 수 없습니다.")
                    return

                files = get_all_drive_files(folder_id, drive_service=drive_service)
                pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]

                start_str = self.ui.start_date.date().toString("MMdd")
                end_str = self.ui.end_date.date().toString("MMdd")

                from service.file_naming_service import FileNamingService
                naming_service = FileNamingService(logger_callback=self.ui.log_signal.emit)
                filtered_pdfs = naming_service.filter_files_by_date_range(pdf_files, start_str, end_str)

                for f in sorted(filtered_pdfs, key=lambda x: x['name']):
                    item_text = f"☁️ {f['name']}"
                    item = QListWidgetItem(item_text)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.ui.file_list.addItem(item)
                    self.file_paths[item_text] = f['id']

                self.ui.log_signal.emit(f"✅ 구글 드라이브에서 {len(filtered_pdfs)}개의 PDF를 불러왔습니다.")
            except Exception as e:
                self.ui.log_signal.emit(f"❌ 구글 드라이브 파일 로드 실패: {str(e)}")

        self.ui.file_list.blockSignals(False)

    def prepare_file_for_preview(self, path_or_id: str, is_drive: bool) -> tuple:
        """선택된 파일의 데이터를 준비하고 (로컬경로, 총 페이지 수)를 반환합니다."""
        if is_drive:
            drive_service = get_drive_service()
            if path_or_id not in self.drive_cache:
                temp_path = os.path.join(self.temp_dir, f"{path_or_id}.pdf")
                download_from_drive(path_or_id, temp_path, drive_service=drive_service)
                self.drive_cache[path_or_id] = temp_path
            self.current_pdf_path = self.drive_cache[path_or_id]
        else:
            self.current_pdf_path = path_or_id

        try:
            with pymupdf.open(self.current_pdf_path) as doc:
                self.total_pages = len(doc)
        except Exception as e:
            self.ui.log_signal.emit(f"❌ PDF 열기 실패: {str(e)}")
            return None, 0
            
        return self.current_pdf_path, self.total_pages

    def split_and_save(self):
        """선택된 파일을 분할하고 저장소(로컬/드라이브)에 저장합니다."""
        if not self.current_pdf_path:
            self.ui.log_signal.emit("⚠️ 분할할 파일을 선택해주세요.")
            return

        text = self.ui.split_input.text()
        try:
            split_page = int(text.strip())
        except ValueError:
            self.ui.log_signal.emit("⚠️ 정확히 1개의 기준 페이지 번호(분할 지점)를 입력해주세요. (예: 3)")
            return

        if split_page <= 0 or split_page >= self.total_pages:
            self.ui.log_signal.emit(f"⚠️ 분할 페이지 번호가 범위를 벗어났습니다. (1~{self.total_pages-1})")
            return

        out1 = self.ui.save_name_1.text()
        out2 = self.ui.save_name_2.text()
        if not out1.endswith('.pdf'): out1 += '.pdf'
        if not out2.endswith('.pdf'): out2 += '.pdf'

        is_drive = self.ui.drive_check.isChecked()
        target_dir = self.ui.folder_input.text() if not is_drive else None

        operation_service = PdfOperationService(logger_callback=self.ui.log_signal.emit)
        success, msg = operation_service.split_and_save(
            current_pdf_path=self.current_pdf_path,
            split_page=split_page,
            out1_name=out1,
            out2_name=out2,
            is_drive=is_drive,
            target_dir=target_dir
        )