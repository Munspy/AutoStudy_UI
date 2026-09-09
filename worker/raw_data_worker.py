"""Raw Data 에디터 탭의 백그라운드 작업을 처리하는 워커 모듈입니다."""
import os
import tempfile
from base.base_worker import BaseWorker
from utils.drive_api import get_all_drive_files, in_memory_download_from_drive, upload_to_drive, delete_drive_file
from utils.config import Config

class RawDataLoadWorker(BaseWorker):
    """Raw Data (PDF 및 텍스트)를 드라이브에서 검색하고 로드하는 워커입니다."""
    def __init__(self, date_str: str, period_str: str, drive_service):
        super().__init__()
        self.date_str = date_str
        self.period_str = period_str
        self.drive_service = drive_service

    def do_work(self):
        target_folder = Config.TARGET_DRIVE_DIR
        query = f"{self.date_str}_{self.period_str}"
        
        self.log_signal.emit(f"🔍 '{query}' 관련 파일을 구글 드라이브에서 검색합니다...")
        
        # 1. 파일 검색
        files = get_all_drive_files(target_folder, name_filter=query, drive_service=self.drive_service)
        
        pdf_file = None
        text_file = None
        
        for f in files:
            name = f.get('name', '')
            if name.endswith('_요약본.txt') or name.endswith('_scripted.pdf'):
                continue
                
            if name.endswith('_최종교정본.txt'):
                text_file = f
            elif name.endswith('.pdf'):
                pdf_file = f
        
        if not pdf_file or not text_file:
            raise Exception("일치하는 원본 PDF 또는 '_최종교정본.txt' 파일을 찾지 못했습니다.")
            
        self.log_signal.emit(f"📥 다운로드 시작: {pdf_file['name']}, {text_file['name']}")
        
        # 2. PDF 파일 인메모리 다운로드
        pdf_bytes = b""
        with in_memory_download_from_drive(pdf_file['id'], drive_service=self.drive_service) as fh:
            pdf_bytes = fh.read()
            
        # 3. 텍스트 파일 인메모리 다운로드
        text_bytes = b""
        with in_memory_download_from_drive(text_file['id'], drive_service=self.drive_service) as fh:
            text_bytes = fh.read()
            
        text_str = text_bytes.decode('utf-8')
        
        return {
            "pdf_bytes": pdf_bytes,
            "text_str": text_str,
            "text_file": text_file
        }


class RawDataApplyWorker(BaseWorker):
    """모든 텍스트 수정사항을 취합하여 구글 드라이브에 업로드하는 워커입니다."""
    def __init__(self, text_dict, total_pages, text_file_id, text_file_name, text_file_parent_id, drive_service):
        super().__init__()
        self.text_dict = text_dict
        self.total_pages = total_pages
        self.text_file_id = text_file_id
        self.text_file_name = text_file_name
        self.text_file_parent_id = text_file_parent_id
        self.drive_service = drive_service

    def do_work(self):
        from utils.text_util import assemble_slide_text
        final_text = assemble_slide_text(self.text_dict, self.total_pages)
        
        # 2. 임시 파일로 저장
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(final_text)
                temp_path = f.name
                
            # 3. 기존 원본 파일 휴지통으로 이동
            self.log_signal.emit(f"🗑️ 기존 파일({self.text_file_name})을 휴지통으로 이동합니다...")
            delete_drive_file(self.text_file_id, drive_service=self.drive_service)
            
            # 4. 새 파일 업로드
            self.log_signal.emit(f"☁️ 수정본을 드라이브로 업로드합니다...")
            upload_to_drive(
                local_file_path=temp_path,
                target_folder_id=self.text_file_parent_id,
                mime_type="text/plain",
                new_file_name=self.text_file_name,
                drive_service=self.drive_service
            )
            
            self.log_signal.emit("✅ 성공: 모든 변경사항이 구글 드라이브에 최종 반영되었습니다!")
            return True
            
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

