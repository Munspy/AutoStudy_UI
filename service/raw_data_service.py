from typing import Dict, Any
import os
import tempfile

from base.base_service import BaseService
from core.config import Config
from core.constants import FileSuffix, Extensions
from utils.text_util import assemble_slide_text

class RawDataService(BaseService):
    """Raw Data 뷰어/에디터의 백그라운드 데이터 처리 및 드라이브 통신을 전담하는 서비스 클래스."""

    def fetch_raw_data(self, date_str: str, period_str: str) -> Dict[str, Any]:
        target_folder = Config.TARGET_DRIVE_DIR
        query = f"{date_str}_{period_str}"
        
        self._log(f"🔍 '{query}' 관련 파일을 구글 드라이브에서 검색합니다...")
        
        files = self.app.drive_client.get_all_drive_files(target_folder, name_filter=query)
        
        pdf_file = None
        text_file = None
        
        for f in files:
            name = f.get('name', '')
            if name.endswith(f'_{FileSuffix.SUMMARY_TXT}.txt') or name.endswith(f'_{FileSuffix.SCRIPTED}{Extensions.PDF}'):
                continue
                
            if name.endswith(f'_{FileSuffix.TRANSCRIPT_CORRECTED}.txt'):
                text_file = f
            elif name.endswith('.pdf'):
                pdf_file = f
        
        if not pdf_file or not text_file:
            raise Exception(f"일치하는 원본 PDF 또는 _{FileSuffix.TRANSCRIPT_CORRECTED}.txt 파일을 찾지 못했습니다.")
            
        self._log(f"📥 다운로드 시작: {pdf_file['name']}, {text_file['name']}")
        
        pdf_bytes = b""
        with self.app.drive_client.in_memory_download_from_drive(pdf_file['id']) as fh:
            pdf_bytes = fh.read()
            
        text_bytes = b""
        with self.app.drive_client.in_memory_download_from_drive(text_file['id']) as fh:
            text_bytes = fh.read()
            
        text_str = text_bytes.decode('utf-8')
        
        return {
            "pdf_bytes": pdf_bytes,
            "text_str": text_str,
            "text_file": text_file
        }

    def apply_raw_data(self, text_dict: Dict[int, str], total_pages: int, text_file_id: str, text_file_name: str, text_file_parent_id: str):
        final_text = assemble_slide_text(text_dict, total_pages)
        
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(final_text)
                temp_path = f.name
                
            self._log(f"☁️ 수정본을 드라이브로 업로드합니다...")
            uploaded_file = self.app.drive_client.upload_to_drive(
                local_file_path=temp_path,
                target_folder_id=text_file_parent_id,
                mime_type="text/plain",
                new_file_name=text_file_name,
            )
            
            self._log(f"🗑️ 기존 파일({text_file_name})을 휴지통으로 이동합니다...")
            self.app.drive_client.delete_drive_file(text_file_id)
            
            self._log("✅ 성공: 모든 변경사항이 구글 드라이브에 최종 반영되었습니다!")
            return uploaded_file.get('id') if uploaded_file else True
            
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
