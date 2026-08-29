import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Literal

from base.base_service import BaseService
from service.file_naming_service import FileNamingService
from utils.filename_util import normalize_text
from utils.drive_api import (
    in_memory_download_from_drive,
    get_all_drive_files
    )
from utils.config import Config

# [최적화 1] 매직 스트링 제거를 위한 Literal 타입 정의 (IDE 자동완성 및 타입 체크 지원)
FileType = Literal[
    "final_pdf", "yaboot", "jul", "script", 
    "audio", "anki", "scripted_pdf", "done_json"
]

class PipelineStatusService(BaseService):
    """단일 교시(Lesson)의 파이프라인 진행 상태 및 연관 파일 검증을 전담합니다."""
    
    def __init__(
        self, 
        drive_service: Optional[Any] = None,
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        # [최적화 2] BaseService 초기화 누락 수정으로 일관된 로깅 시스템 활성화
        super().__init__(logger_callback=logger_callback)
        self.drive_service = drive_service
        self.json_cache: Dict[str, Any] = {}
        # 하위 서비스에도 로깅 콜백 주입
        self.naming_service = FileNamingService(logger_callback=logger_callback)

    def check_lesson_file_status(
        self, 
        file_list: List[str], 
        target_lesson_id: str, 
        file_type: FileType
    ) -> bool:
        """[파이프라인 진행도 검증] 특정 단계의 파일이 존재하는지 확인합니다."""
        target_lesson_id = normalize_text(target_lesson_id)
        
        # 1. 최종 합본 PDF 존재 여부
        if file_type == "final_pdf": 
            return f"{target_lesson_id}.pdf" in file_list
            
        # 2. 개별 필기본(야붙/줄필기) 존재 여부
        elif file_type == "yaboot": 
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "야붙필기"))
        elif file_type == "jul": 
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "줄필기"))
            
        # 3. Whisper 음성 스크립트 존재 여부 (교정 전/후 모두 인정)
        elif file_type == "script":
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "음성스크립트")) or \
                   bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "최종교정본"))
                   
        # 4. 원본 오디오 미디어 파일 존재 여부
        elif file_type == "audio":
            audio_exts = ('.wav', '.m4a', '.mp3', '.mp4', '.aac', '.flac')
            return any(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, ext) for ext in audio_exts)
            
        # 5. Anki 생성 완료 여부
        elif file_type == "anki": 
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "통합본.apkg"))
            
        # 6. 스크립트가 병합된 최종 PDF 존재 여부
        elif file_type == "scripted_pdf": 
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "scripted.pdf"))
            
        # 7. LLM 작업 메타데이터 파일 존재 여부
        elif file_type == "done_json": 
            return bool(self.naming_service.find_file_by_lesson(file_list, target_lesson_id, "done.json"))
            
        return False

    def get_ai_task_status_from_json(
        self, 
        drive_files: List[Dict[str, Any]], 
        target_lesson_id: str
    ) -> tuple[bool, bool]:
        """
        드라이브에 저장된 `done.json`을 열어, AI 교정과 요약 작업이 내부에 실제로 기록되었는지 확인합니다.
        """
        if not self.drive_service:
            raise ValueError("구글 드라이브 서비스가 초기화되지 않았습니다.")

        target_lesson_id = normalize_text(target_lesson_id)
        file_names = [normalize_text(f.get('name', '')) for f in drive_files]
        
        # 대상 교시의 done.json 파일명 검색
        done_json_filename = self.naming_service.find_file_by_lesson(file_names, target_lesson_id, "done.json")
        has_corrected, has_summary = False, False
        done_file_info = None
        
        if done_json_filename:
            done_file_info = next((f for f in drive_files if normalize_text(f.get('name', '')) == done_json_filename), None)
            
        if done_file_info:
            file_id = done_file_info['id']
            
            # 캐시에 없다면 드라이브에서 메모리로 직접 다운로드
            if file_id not in self.json_cache:
                try:
                    with in_memory_download_from_drive(file_id, drive_service=self.drive_service) as fh:
                        content = fh.read().decode('utf-8')
                        # [최적화 2] JSONDecodeError 방어 및 빈 파일 처리
                        self.json_cache[file_id] = json.loads(content) if content.strip() else {}
                except json.JSONDecodeError as e:
                    self._log(f"⚠️ [JSON 파싱 오류] {done_json_filename} 파일이 손상되었습니다: {str(e)}")
                    self.json_cache[file_id] = {}
                except Exception as e: 
                    self._log(f"⚠️ [다운로드 오류] {done_json_filename} 파일 읽기 실패: {str(e)}")
                    self.json_cache[file_id] = {}
                    
            # 캐시된 JSON 데이터 분석
            json_data = self.json_cache.get(file_id, {})
            has_corrected = bool(json_data.get("corrected_text", "").strip())
            has_summary = bool(json_data.get("summary", "").strip())
                
        return has_corrected, has_summary

    def fetch_files_by_date_range(
        self, 
        start_date_str: str, 
        end_date_str: str, 
        file_extension: str = ".pdf"
    ) -> List[Dict[str, Any]]:
        """
        드라이브에서 특정 확장자를 가진 파일 중, 지정된 날짜 범위(MMdd)에 해당하는 파일 목록만 반환합니다.
        """
        # [최적화 3] 지연 임포트 제거 (상단 임포트로 통합)
        if not self.drive_service:
            raise ValueError("드라이브 서비스가 초기화되지 않았습니다.")
            
        target_folder_id = Config.TARGET_DRIVE_DIR
        all_files = get_all_drive_files(target_folder_id, drive_service=self.drive_service)        

        start_mmdd = datetime.strptime(start_date_str, "%Y-%m-%d").strftime("%m%d")
        end_mmdd = datetime.strptime(end_date_str, "%Y-%m-%d").strftime("%m%d")

        # 1차: 확장자 필터링
        ext_filtered = [f for f in all_files if f.get('name', '').lower().endswith(file_extension)]
        
        # 2차: FileNamingService에 날짜 필터링 위임
        return self.naming_service.filter_files_by_date_range(ext_filtered, start_mmdd, end_mmdd)