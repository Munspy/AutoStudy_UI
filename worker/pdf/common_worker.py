import os
from base.base_worker import BaseWorker
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.file_util import list_local_files
from utils.config import Config
from service.file_naming_service import FileNamingService

class PdfFileListWorker(BaseWorker):
    """지정된 조건에 따라 로컬 또는 구글 드라이브의 PDF 파일 목록을 조회하는 워커 클래스입니다."""
    
    def __init__(self, is_drive, target_dir, start_str, end_str):
        """PdfFileListWorker 초기화.
        
        Args:
            is_drive (bool): 드라이브 조회 여부.
            target_dir (str): 로컬 대상 디렉토리.
            start_str (str): 검색 시작 조건 문자열.
            end_str (str): 검색 종료 조건 문자열.
        """
        super().__init__()
        self.is_drive = is_drive
        self.target_dir = target_dir
        self.start_str = start_str
        self.end_str = end_str

    def do_work(self):
        """파일 목록을 가져와서 딕셔너리로 반환합니다.
        
        Returns:
            dict: 파일명(UI 표시용 텍스트)과 경로(또는 ID)를 매핑한 딕셔너리.
        """
        file_paths = {}
        
        # ===========================
        # [로컬 파일 목록 조회]
        # ===========================
        if not self.is_drive:
            # 로컬 경로 유효성 검사
            if not os.path.exists(self.target_dir):
                self.error_signal.emit("대상 폴더가 존재하지 않습니다.")
                return file_paths

            # 폴더 내의 PDF 파일 목록 가져오기
            files = list_local_files(self.target_dir, extension=".pdf")
            if not files:
                self.error_signal.emit("폴더 내에 PDF 파일이 없습니다.")
                return file_paths

            # 파일 경로 매핑 생성
            for f in sorted(files):
                item_text = f"📄 {f}"
                file_paths[item_text] = os.path.join(self.target_dir, f)
            self.log_signal.emit(f"✅ 로컬 폴더에서 {len(files)}개의 PDF를 불러왔습니다.")
            
        # ===========================
        # [구글 드라이브 파일 목록 조회]
        # ===========================
        else:
            self.log_signal.emit("🔄 구글 드라이브에서 조건에 맞는 PDF 파일을 조회 중입니다...")
            drive_service = get_drive_service()
            try:
                folder_id = Config.TARGET_DRIVE_DIR
            except ValueError:
                self.error_signal.emit(".env 설정 오류: TARGET_DRIVE_DIR 폴더 ID를 찾을 수 없습니다.")
                return file_paths

            # 전체 드라이브 파일 가져오기 및 PDF 필터링
            files = get_all_drive_files(folder_id, drive_service=drive_service)
            pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]

            # 명명 규칙 서비스로 날짜 범위에 맞게 필터링
            naming_service = FileNamingService(logger_callback=self.log_signal.emit)
            filtered_pdfs = naming_service.filter_files_by_date_range(pdf_files, self.start_str, self.end_str)

            # 파일 ID 매핑 생성
            for f in sorted(filtered_pdfs, key=lambda x: x['name']):
                item_text = f"☁️ {f['name']}"
                file_paths[item_text] = f['id']

            self.log_signal.emit(f"✅ 구글 드라이브에서 {len(filtered_pdfs)}개의 PDF를 불러왔습니다.")
        
        return file_paths
