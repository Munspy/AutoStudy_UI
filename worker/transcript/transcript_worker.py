import os
from datetime import datetime
from base.base_worker import BaseWorker
from service.text_processing_service import TextProcessingService
from service.file_naming_service import FileNamingService
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files, in_memory_download_from_drive, upload_to_drive
from utils.config import Config

class TranscriptDriveSearchWorker(BaseWorker):
    def __init__(self, start_date, end_date):
        super().__init__()
        self.start_date = start_date
        self.end_date = end_date

    def do_work(self):
        drive_service = get_drive_service()
        target_folder_id = Config.TARGET_DRIVE_DIR
        all_files = get_all_drive_files(target_folder_id, drive_service=drive_service)
        
        start_mmdd = datetime.strptime(self.start_date, "%Y-%m-%d").strftime("%m%d")
        end_mmdd = datetime.strptime(self.end_date, "%Y-%m-%d").strftime("%m%d")
        
        txt_files = [f for f in all_files if f.get('name', '').lower().endswith('.txt')]
        naming_service = FileNamingService()
        filtered_dicts = naming_service.filter_files_by_date_range(txt_files, start_mmdd, end_mmdd)
        
        drive_files_cache = {}
        filtered_files = []
        for f in filtered_dicts:
            name = f.get('name', '')
            filtered_files.append(name)
            drive_files_cache[name] = f.get('id')
            
        return sorted(filtered_files), drive_files_cache


class TranscriptReadWorker(BaseWorker):
    def __init__(self, filenames, folder_path, is_drive, drive_cache=None):
        super().__init__()
        self.filenames = filenames
        self.folder_path = folder_path
        self.is_drive = is_drive
        self.drive_cache = drive_cache or {}

    def do_work(self):
        contents = []
        drive_service = get_drive_service() if self.is_drive else None
        
        for fname in self.filenames:
            if self.is_cancelled(): break
            
            if self.is_drive:
                file_id = self.drive_cache.get(fname)
                if not file_id:
                    self.error_signal.emit(f"드라이브에서 '{fname}'을 찾을 수 없습니다.")
                    return None
                with in_memory_download_from_drive(file_id, drive_service=drive_service) as fh:
                    c = fh.read().decode('utf-8', errors='replace')
            else:
                file_path = os.path.join(self.folder_path, fname)
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    c = f.read()
            contents.append(c)
            
        return {"filenames": self.filenames, "contents": contents}

class TranscriptSplitSaveWorker(BaseWorker):
    def __init__(self, folder_path, filename, text_content, name1, name2, is_drive):
        super().__init__()
        self.folder_path = folder_path
        self.filename = filename
        self.text_content = text_content
        self.name1 = name1
        self.name2 = name2
        self.is_drive = is_drive

    def do_work(self):
        text_service = TextProcessingService()
        parts = text_service.split_text_content(self.text_content)
        
        saved_paths = []
        for fname, content in zip([self.name1, self.name2], parts):
            save_path = os.path.join(self.folder_path, fname)
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)
            saved_paths.append(save_path)
            
        msg = f"총 {len(saved_paths)}개의 파일로 분할되어 로컬에 저장되었습니다."
        if self.is_drive:
            self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
            drive_service = get_drive_service()
            target_folder_id = Config.TARGET_DRIVE_DIR
            for path in saved_paths:
                if self.is_cancelled(): break
                upload_to_drive(path, target_folder_id, mime_type='text/plain', drive_service=drive_service)
            msg += "\n(드라이브 업로드도 완료되었습니다!)"
            
        return msg

class TranscriptMergeSaveWorker(BaseWorker):
    def __init__(self, folder_path, files_to_merge, merged_content, custom_name, is_drive):
        super().__init__()
        self.folder_path = folder_path
        self.files_to_merge = files_to_merge
        self.merged_content = merged_content
        self.custom_name = custom_name
        self.is_drive = is_drive

    def do_work(self):
        import os
        save_path = os.path.join(self.folder_path, self.custom_name)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(self.merged_content)
            
        new_filename = os.path.basename(save_path)
        msg = f"파일이 성공적으로 병합되어 로컬에 저장되었습니다:\n{new_filename}"
        
        if self.is_drive:
            self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
            drive_service = get_drive_service()
            upload_to_drive(save_path, Config.TARGET_DRIVE_DIR, mime_type='text/plain', drive_service=drive_service)
            msg += "\n\n(드라이브 업로드도 완료되었습니다!)"
            
        return msg, new_filename
