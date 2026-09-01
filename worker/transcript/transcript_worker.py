import os
from datetime import datetime
from base.base_worker import BaseWorker
from service.text_processing_service import TextProcessingService
from service.file_naming_service import FileNamingService
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files, in_memory_download_from_drive, upload_to_drive
from utils.config import Config

class TranscriptDriveSearchWorker(BaseWorker):
    """구글 드라이브에서 특정 기간의 텍스트 파일을 검색하는 워커 클래스입니다."""
    
    def __init__(self, start_date, end_date):
        """TranscriptDriveSearchWorker 초기화."""
        super().__init__()
        self.start_date = start_date
        self.end_date = end_date

    def do_work(self):
        """드라이브를 스캔하여 조건에 맞는 파일 목록을 반환합니다."""
        # ===========================
        # [드라이브 파일 목록 가져오기]
        # ===========================
        drive_service = get_drive_service()
        target_folder_id = Config.TARGET_DRIVE_DIR
        all_files = get_all_drive_files(target_folder_id, drive_service=drive_service)
        
        # 시작 및 종료 날짜를 월일(MMDD) 형식으로 변환합니다.
        start_mmdd = datetime.strptime(self.start_date, "%Y-%m-%d").strftime("%m%d")
        end_mmdd = datetime.strptime(self.end_date, "%Y-%m-%d").strftime("%m%d")
        
        # 텍스트 파일(.txt)만 필터링합니다.
        txt_files = [f for f in all_files if f.get('name', '').lower().endswith('.txt')]
        
        # 명명 규칙 서비스를 사용하여 날짜 범위 내의 파일만 다시 필터링합니다.
        naming_service = FileNamingService()
        filtered_dicts = naming_service.filter_files_by_date_range(txt_files, start_mmdd, end_mmdd)
        
        # ===========================
        # [캐시 및 결과 목록 생성]
        # ===========================
        drive_files_cache = {}
        filtered_files = []
        for f in filtered_dicts:
            name = f.get('name', '')
            filtered_files.append(name)
            # 파일 ID를 캐시에 저장합니다.
            drive_files_cache[name] = f.get('id')
            
        return sorted(filtered_files), drive_files_cache


class TranscriptReadWorker(BaseWorker):
    """로컬 또는 드라이브에서 텍스트 파일 내용을 읽어오는 워커 클래스입니다."""
    
    def __init__(self, filenames, folder_path, is_drive, drive_cache=None):
        """TranscriptReadWorker 초기화."""
        super().__init__()
        self.filenames = filenames
        self.folder_path = folder_path
        self.is_drive = is_drive
        self.drive_cache = drive_cache or {}

    def do_work(self):
        """요청된 파일들의 내용을 읽어서 반환합니다."""
        # ===========================
        # [파일 내용 읽기 루프]
        # ===========================
        contents = []
        drive_service = get_drive_service() if self.is_drive else None
        
        for fname in self.filenames:
            if self.is_cancelled(): break
            
            if self.is_drive:
                # 드라이브 파일 읽기
                file_id = self.drive_cache.get(fname)
                if not file_id:
                    self.error_signal.emit(f"드라이브에서 '{fname}'을 찾을 수 없습니다.")
                    return None
                with in_memory_download_from_drive(file_id, drive_service=drive_service) as fh:
                    c = fh.read().decode('utf-8', errors='replace')
            else:
                # 로컬 파일 읽기
                file_path = os.path.join(self.folder_path, fname)
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    c = f.read()
            contents.append(c)
            
        return {"filenames": self.filenames, "contents": contents}

class TranscriptSplitSaveWorker(BaseWorker):
    """텍스트 내용을 분할하여 저장하는 워커 클래스입니다."""
    
    def __init__(self, folder_path, filename, text_content, name1, name2, is_drive):
        """TranscriptSplitSaveWorker 초기화."""
        super().__init__()
        self.folder_path = folder_path
        self.filename = filename
        self.text_content = text_content
        self.name1 = name1
        self.name2 = name2
        self.is_drive = is_drive

    def do_work(self):
        """텍스트를 분할하여 로컬에 저장하고, 필요 시 드라이브에 업로드합니다."""
        # ===========================
        # [텍스트 분할 및 로컬 저장]
        # ===========================
        text_service = TextProcessingService()
        parts = text_service.split_text_content(self.text_content)
        
        saved_paths = []
        for fname, content in zip([self.name1, self.name2], parts):
            save_path = os.path.join(self.folder_path, fname)
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(content)
            saved_paths.append(save_path)
            
        msg = f"총 {len(saved_paths)}개의 파일로 분할되어 로컬에 저장되었습니다."
        
        # ===========================
        # [드라이브 업로드 처리]
        # ===========================
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
    """여러 텍스트 파일을 하나로 병합하여 저장하는 워커 클래스입니다."""
    
    def __init__(self, folder_path, files_to_merge, merged_content, custom_name, is_drive):
        """TranscriptMergeSaveWorker 초기화."""
        super().__init__()
        self.folder_path = folder_path
        self.files_to_merge = files_to_merge
        self.merged_content = merged_content
        self.custom_name = custom_name
        self.is_drive = is_drive

    def do_work(self):
        """병합된 텍스트를 로컬에 저장하고, 필요 시 드라이브에 업로드합니다."""
        import os
        # ===========================
        # [병합 파일 로컬 저장]
        # ===========================
        save_path = os.path.join(self.folder_path, self.custom_name)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(self.merged_content)
            
        new_filename = os.path.basename(save_path)
        msg = f"파일이 성공적으로 병합되어 로컬에 저장되었습니다:\n{new_filename}"
        
        # ===========================
        # [드라이브 업로드 처리]
        # ===========================
        if self.is_drive:
            self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
            drive_service = get_drive_service()
            upload_to_drive(save_path, Config.TARGET_DRIVE_DIR, mime_type='text/plain', drive_service=drive_service)
            msg += "\n\n(드라이브 업로드도 완료되었습니다!)"
            
        return msg, new_filename
