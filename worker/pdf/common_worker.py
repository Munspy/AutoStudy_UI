import os
from base.base_worker import BaseWorker
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.file_util import list_local_files
from utils.config import Config
from service.file_naming_service import FileNamingService

class PdfFileListWorker(BaseWorker):
    def __init__(self, is_drive, target_dir, start_str, end_str):
        super().__init__()
        self.is_drive = is_drive
        self.target_dir = target_dir
        self.start_str = start_str
        self.end_str = end_str

    def do_work(self):
        file_paths = {}
        if not self.is_drive:
            if not os.path.exists(self.target_dir):
                self.error_signal.emit("대상 폴더가 존재하지 않습니다.")
                return file_paths

            files = list_local_files(self.target_dir, extension=".pdf")
            if not files:
                self.error_signal.emit("폴더 내에 PDF 파일이 없습니다.")
                return file_paths

            for f in sorted(files):
                item_text = f"📄 {f}"
                file_paths[item_text] = os.path.join(self.target_dir, f)
            self.log_signal.emit(f"✅ 로컬 폴더에서 {len(files)}개의 PDF를 불러왔습니다.")
        else:
            self.log_signal.emit("🔄 구글 드라이브에서 조건에 맞는 PDF 파일을 조회 중입니다...")
            drive_service = get_drive_service()
            try:
                folder_id = Config.TARGET_DRIVE_DIR
            except ValueError:
                self.error_signal.emit(".env 설정 오류: TARGET_DRIVE_DIR 폴더 ID를 찾을 수 없습니다.")
                return file_paths

            files = get_all_drive_files(folder_id, drive_service=drive_service)
            pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]

            naming_service = FileNamingService(logger_callback=self.log_signal.emit)
            filtered_pdfs = naming_service.filter_files_by_date_range(pdf_files, self.start_str, self.end_str)

            for f in sorted(filtered_pdfs, key=lambda x: x['name']):
                item_text = f"☁️ {f['name']}"
                file_paths[item_text] = f['id']

            self.log_signal.emit(f"✅ 구글 드라이브에서 {len(filtered_pdfs)}개의 PDF를 불러왔습니다.")
        
        return file_paths
