# controller/transcript_merge_split_controller.py
import os
import re
from datetime import datetime

from base.base_controller import BaseController
from service.text_processing_service import TextProcessingService
from utils.file_util import list_local_files
from utils.drive_api import get_all_drive_files, in_memory_download_from_drive, upload_to_drive
from utils.auth_util import get_drive_service
from utils.config import Config


from service.file_naming_service import FileNamingService

class TranscriptController(BaseController):
    def __init__(self, view=None):
        super().__init__(ui_view=view)
        self.text_service = TextProcessingService()
        self.naming_service = FileNamingService()
        self.drive_files_cache = {}  # 드라이브 파일 ID를 기억해둘 캐시

    def generate_split_filenames(self, filename: str):
        return self.naming_service.generate_split_filenames(filename)

    def generate_merged_filename(self, filenames: list):
        return self.naming_service.generate_merged_filename(filenames)

    # ==========================================
    # 1. 파일 목록 조회 (Utils 직접 활용)
    # ==========================================
    def get_local_text_files(self, directory: str):
        return list_local_files(directory, extension=".txt")

    def get_drive_text_files(self, start_date_str: str, end_date_str: str):
        drive_service = get_drive_service()
        target_folder_id = Config.TARGET_DRIVE_DIR
        all_files = get_all_drive_files(target_folder_id, drive_service=drive_service)
        
        start_mmdd = datetime.strptime(start_date_str, "%Y-%m-%d").strftime("%m%d")
        end_mmdd = datetime.strptime(end_date_str, "%Y-%m-%d").strftime("%m%d")
        
        txt_files = [f for f in all_files if f.get('name', '').lower().endswith('.txt')]
        
        # --- 다이어트 로직: 서비스 위임 ---
        from service.file_naming_service import FileNamingService
        naming_service = FileNamingService()
        filtered_dicts = naming_service.filter_files_by_date_range(txt_files, start_mmdd, end_mmdd)
        # -----------------------------------
        
        self.drive_files_cache.clear()
        filtered_files = []
        
        for f in filtered_dicts:
            name = f.get('name', '')
            filtered_files.append(name)
            self.drive_files_cache[name] = f.get('id')
            
        return sorted(filtered_files)

    # ==========================================
    # 2. 파일 읽기 (I/O 처리)
    # ==========================================
    def read_local_file(self, folder_path: str, filename: str):
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def read_drive_file(self, filename: str):
        file_id = self.drive_files_cache.get(filename)
        if not file_id:
            raise FileNotFoundError(f"드라이브에서 '{filename}'을 찾을 수 없습니다.")
            
        drive_service = get_drive_service()
        with in_memory_download_from_drive(file_id, drive_service=drive_service) as fh:
            return fh.read().decode('utf-8', errors='replace')

    # ==========================================
    # 3. 분할/병합 및 저장 (TextService + I/O 조율)
    # ==========================================
    def split_text_file(self, target_dir: str, filename: str, text_content: str, custom_name_1: str, custom_name_2: str):
        # 1) 순수 비즈니스 로직(서비스)으로 텍스트를 나눔
        parts = self.text_service.split_text_content(text_content)
        
        # 2) 로컬 파일 시스템에 직접 저장
        saved_paths = []
        for fname, content in zip([custom_name_1, custom_name_2], parts):
            save_path = os.path.join(target_dir, fname)
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)
            saved_paths.append(save_path)
            
        return saved_paths

    def merge_text_files(self, target_dir: str, filenames: list, merged_content: str, custom_filename: str):
        # UI에서 이미 병합된 텍스트(merged_content)를 주므로 그대로 파일에 저장
        save_path = os.path.join(target_dir, custom_filename)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(merged_content)
        return save_path
        
    def upload_to_drive(self, local_file_path: str):
        drive_service = get_drive_service()
        target_folder_id = Config.TARGET_DRIVE_DIR
        return upload_to_drive(local_file_path, target_folder_id, mime_type='text/plain', drive_service=drive_service)