# service/drive_sync_service.py
from typing import List, Tuple, Dict, Any, Optional, Callable
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.file_util import list_local_files
from utils.config import Config
from base.base_service import BaseService

# 분리된 도메인 서비스 임포트
from service.file_naming_service import FileNamingService
from service.pipeline_status_service import PipelineStatusService

class DriveSyncService(BaseService):
    """
    드라이브 및 로컬 폴더의 파일을 스캔하여 
    각 수업 교시별 동기화 상태를 판별하는 비즈니스 로직 서비스입니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        # BaseService 초기화 시 콜백을 한 번만 등록하여 이후 self._log()에서 자동 사용되도록 설정
        super().__init__(logger_callback=logger_callback)
        
        # 다른 서비스 파일들과의 통일성을 위해 직접 호출 방식 유지
        self.drive_service = get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR
        
        # 도메인 서비스 인스턴스화
        self.naming_service = FileNamingService()
        self.pipeline_service = PipelineStatusService(self.drive_service)

    def fetch_all_files(self, local_path: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """
        드라이브와 로컬의 모든 파일 목록을 스캔하여 반환합니다.
        macOS 환경(.DS_Store 등) 시스템 숨김 파일 필터링이 적용되어 있습니다.
        """
        # 네트워크 및 권한 에러 방어 (Try-Except 적용)
        try:
            drive_files: List[Dict[str, Any]] = get_all_drive_files(self.target_folder_id, drive_service=self.drive_service)
            drive_filenames: List[str] = [f['name'] for f in drive_files]
        except Exception as e:
            # 업데이트된 _log 활용: 별도의 콜백 인자 전달 불필요
            self._log(f"❌ [DriveSync] 구글 드라이브 스캔 중 오류 발생: {str(e)}")
            drive_files, drive_filenames = [], []

        try:
            raw_local_files: List[str] = list_local_files(local_path)
            # macOS 시스템 파일(.DS_Store 등) 및 임시 파일(._, ~$) 무시 로직 적용
            local_files: List[str] = [
                f for f in raw_local_files 
                if not f.startswith('.') and not f.startswith('~$')
            ]
        except Exception as e:
            self._log(f"❌ [DriveSync] 로컬 폴더({local_path}) 스캔 중 오류 발생: {str(e)}")
            local_files = []
        
        return drive_files, drive_filenames, local_files

    def extract_and_filter_lessons(self, filenames: List[str], search_mode: str, filter_value: Any) -> List[str]:
        """
        파일 이름 목록에서 교시(Lesson ID)를 추출하고 필터링 조건에 맞게 정렬하여 반환합니다.
        """
        lesson_ids = set()
        
        for f in filenames:
            lesson_id: Optional[str] = self.naming_service.extract_lesson_id(f)
            if not lesson_id:
                continue
                
            if search_mode == "DATE":
                try:
                    # 엄격한 네이밍 룰에 의거하여 기존 슬라이싱 방식 유지
                    start_date, end_date = filter_value
                    file_md: str = lesson_id.split('_')[0]
                    start_md: str = start_date.split('-')[1] + start_date.split('-')[2]
                    end_md: str = end_date.split('-')[1] + end_date.split('-')[2]
                    
                    if start_md <= file_md <= end_md:
                        lesson_ids.add(lesson_id)
                except IndexError:
                    # 예상치 못한 파일명으로 split이 실패해도 다음 파일로 스킵
                    continue
            else: 
                lesson_ids.add(lesson_id)
                
        return sorted(list(lesson_ids))

    def build_lesson_status_data(self, lesson_id: str, drive_files: List[Dict[str, Any]], drive_filenames: List[str], json_cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        단일 교시에 대한 각종 파일 존재 여부 및 상태 데이터를 조립합니다.
        """
        try:
            # PipelineStatusService 활용하여 파일 존재 여부 확인
            has_final_pdf: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "final_pdf")
            has_yaboot: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "yaboot")
            has_jul: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "jul")
            
            note_status: str = "완료" if has_final_pdf else ("야붙" if has_yaboot else ("줄" if has_jul else "없음"))

            has_script: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "script")
            has_audio: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "audio")
            
            script_status: str = "O (완료)" if has_script else ("Whisper AI 전사 필요" if has_audio else "영상 없음")

            # LLM 태스크 및 부가 작업 결과 확인
            has_corrected, has_summary = self.pipeline_service.get_ai_task_status_from_json(drive_files, lesson_id)
            has_anki: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "anki")
            has_scripted_pdf: bool = self.pipeline_service.check_lesson_file_status(drive_filenames, lesson_id, "scripted_pdf")

            return {
                "수업교시": lesson_id,
                "교수": "-", 
                "강의명": f"강의_{lesson_id}", 
                "필기 상태": note_status,
                "음성 스크립트 상태": script_status,
                "교정 스크립트": has_corrected,
                "요약본": has_summary,
                "Anki": has_anki,
                "스크립트 합본": has_scripted_pdf
            }
        except Exception as e:
            self._log(f"⚠️ [DriveSync] 교시({lesson_id}) 상태 데이터 조립 중 오류: {str(e)}")
            # 에러 발생 시 UI 테이블이 멈추지 않도록 기본 오류 템플릿 반환
            return {
                "수업교시": lesson_id, "교수": "Error", "강의명": "Error",
                "필기 상태": "오류", "음성 스크립트 상태": "오류",
                "교정 스크립트": False, "요약본": False, "Anki": False, "스크립트 합본": False
            }