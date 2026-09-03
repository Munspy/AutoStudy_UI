"""구글 드라이브 동기화 및 학습 자료 파이프라인 상태 관리 서비스.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
애플리케이션의 핵심 비즈니스 로직 중 하나로, 구글 드라이브(클라우드)와 로컬 파일 시스템 간의 
데이터 스캔 및 상태 매핑을 담당합니다. 

이 서비스는 파일의 존재 여부(필기 PDF, 오디오 파일, Whisper 추출 텍스트, Gemini LLM 요약본, Anki 패키지 등)를 
추적하여 각 '수업 교시(Lesson ID)'별 파이프라인 진행 상태(어떤 작업이 완료되었고 어떤 작업이 대기 중인지)를 
하나의 데이터 구조로 취합합니다. 이후 Controller 계층으로 반환되어 메인 UI의 데이터 테이블(Data Grid)에 
시각적으로 렌더링되도록 중개 역할을 수행합니다.
"""

import re
from typing import List, Tuple, Dict, Any, Optional, Callable
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.file_util import list_local_files
from utils.filename_util import normalize_text
from utils.config import Config
from base.base_service import BaseService

# 분리된 도메인 서비스 임포트
from service.file_naming_service import FileNamingService
from service.pipeline_status_service import PipelineStatusService

class DriveSyncService(BaseService):
    """드라이브 및 로컬 폴더의 파일을 스캔하여 각 수업 교시별 동기화 상태를 판별하는 단일 책임 서비스.

    구글 드라이브 API 통신(`get_drive_service`, `get_all_drive_files`), 파일 시스템 스캔, 
    도메인 로직 처리(`FileNamingService`, `PipelineStatusService`)에 대한 의존성을 묶어 
    Controller가 복잡한 상태 취합 로직에 관여하지 않도록 캡슐화(Encapsulation)합니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """DriveSyncService를 초기화하고 필요한 의존성 객체들을 주입받아 생성합니다."""
        super().__init__(logger_callback=logger_callback)
        
        self.drive_service = get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR
        
        # 도메인 서비스 인스턴스화
        self.naming_service = FileNamingService()
        self.pipeline_service = PipelineStatusService(self.drive_service)
        
        # 시험 기준 카테고리 캐시
        self._exam_categories_cache: Optional[List[Tuple[str, str]]] = None

    def fetch_exam_categories(self, force_refresh: bool = False) -> List[Tuple[str, str]]:
        """Google Drive 루트 폴더에서 정확히 2단계까지만 폴더 구조를 탐색하여 (과목/시험명, 폴더 ID)를 초고속 반환합니다.
        
        초고속 최적화:
        1. API 호출 단 2회로 완료 (1단계 폴더 조회 1회 + 2단계 폴더 조회 1회)
        2. 날짜_교시 형태('0414_34', '0826_1' 등)의 폴더는 쿼리/메모리 레벨에서 즉시 제외
        3. 3단계 이상의 깊은 하위 트리는 일절 진입하지 않음
        4. 메모리 캐싱 적용 (force_refresh가 아닐 경우 즉시 반환)
        """
        if not force_refresh and self._exam_categories_cache is not None:
            return self._exam_categories_cache

        import re

        def is_lesson_folder_name(name: str) -> bool:
            clean = name.strip()
            return bool(re.match(r'^\d{4}[-_]\d+', clean) or self.naming_service.extract_lesson_id(clean))

        try:
            root_id = Config.extract_drive_id(self.target_folder_id)
            if not root_id:
                return []

            # -------------------------------------------------------------
            # [1단계 폴더 조회: API 호출 1회]
            # -------------------------------------------------------------
            l1_query = f"'{root_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            res = self.drive_service.files().list(
                q=l1_query,
                pageSize=1000,
                fields="files(id, name)"
            ).execute()
            l1_folders = res.get('files', [])

            # 날짜_교시 형태 폴더(0414_34 등)는 1단계에서 즉시 제외
            valid_l1_folders = [f for f in l1_folders if not is_lesson_folder_name(f.get('name', ''))]
            if not valid_l1_folders:
                return []

            categories: List[Tuple[str, str]] = []
            chunk_map = {f['id']: f['name'] for f in valid_l1_folders}

            # -------------------------------------------------------------
            # [2단계 폴더 조회: API 호출 1회 (최대 50개 부모 폴더 통합 쿼리)]
            # -------------------------------------------------------------
            parents_q = " or ".join([f"'{f['id']}' in parents" for f in valid_l1_folders[:50]])
            l2_query = f"({parents_q}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            
            res_l2 = self.drive_service.files().list(
                q=l2_query,
                pageSize=1000,
                fields="files(id, name, parents)"
            ).execute()
            l2_folders = res_l2.get('files', [])

            # 2단계 폴더 매핑 및 날짜_교시 제외
            l1_with_l2 = set()
            for l2 in l2_folders:
                l2_name = l2.get('name', '').strip()
                if is_lesson_folder_name(l2_name):
                    continue
                parents = l2.get('parents', [])
                if parents and parents[0] in chunk_map:
                    parent_id = parents[0]
                    parent_name = chunk_map[parent_id]
                    l1_with_l2.add(parent_id)
                    
                    combo_name = f"{parent_name} {l2_name}".strip()
                    categories.append((combo_name, l2['id']))

            # 2단계 하위 폴더가 없는 1단계 폴더는 1단계 폴더명 자체로 추가
            for f in valid_l1_folders:
                if f['id'] not in l1_with_l2:
                    categories.append((f['name'], f['id']))

            categories.sort(key=lambda x: x[0])
            self._exam_categories_cache = categories
            self._log(f"📁 [DriveSync] 시험 기준 폴더 {len(categories)}개 초고속 조회 완료 (API 2회)")
            return categories

        except Exception as e:
            self._log(f"❌ [DriveSync] 시험 기준 폴더 목록 조회 실패: {str(e)}")
            return []

    def fetch_all_files(
        self, 
        local_path: str = "", 
        target_folder_id: Optional[str] = None,
        name_filter: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """구글 드라이브와 로컬 시스템의 모든 파일 목록을 스캔하여 수집합니다."""
        folder_id = target_folder_id or self.target_folder_id
        try:
            drive_files: List[Dict[str, Any]] = get_all_drive_files(
                folder_id, 
                name_filter=name_filter, 
                drive_service=self.drive_service
            )
            drive_filenames: List[str] = [normalize_text(f.get('name', '')) for f in drive_files]
        except Exception as e:
            self._log(f"❌ [DriveSync] 구글 드라이브 스캔 중 오류 발생: {str(e)}")
            drive_files, drive_filenames = [], []

        try:
            raw_local_files: List[str] = list_local_files(local_path) if local_path else []
            local_files: List[str] = [
                f for f in raw_local_files 
                if not f.startswith('.') and not f.startswith('~$')
            ]
        except Exception as e:
            self._log(f"❌ [DriveSync] 로컬 폴더({local_path}) 스캔 중 오류 발생: {str(e)}")
            local_files = []
        
        return drive_files, drive_filenames, local_files

    def extract_and_filter_lessons(self, filenames: List[str], search_mode: str, filter_value: Any) -> List[str]:
        """무작위 파일 이름 목록에서 정규화된 교시(Lesson ID)를 추출하고 조건에 맞게 정렬하여 반환합니다."""
        lesson_ids = set()
        
        for f in filenames:
            lesson_id: Optional[str] = self.naming_service.extract_lesson_id(f)
            if not lesson_id:
                continue
                
            if search_mode == "DATE":
                try:
                    start_date, end_date = filter_value
                    file_md: str = lesson_id.split('_')[0]
                    start_md: str = start_date.split('-')[1] + start_date.split('-')[2]
                    end_md: str = end_date.split('-')[1] + end_date.split('-')[2]
                    
                    if start_md <= file_md <= end_md:
                        lesson_ids.add(lesson_id)
                except IndexError:
                    continue
            else: 
                lesson_ids.add(lesson_id)
                
        return sorted(list(lesson_ids))

    # =========================================================================
    # [1단계: 순수 존재 유무 데이터 수집 (Raw Boolean Flags)]
    # =========================================================================
    def get_lesson_file_flags(self, lesson_id: str, filenames: List[str]) -> Dict[str, bool]:
        """해당 교시(Lesson ID)에 대해 모든 파이프라인 파일의 존재 여부만 True/False로 수집합니다."""
        return {
            "final_pdf": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "final_pdf"),
            "yaboot": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "yaboot"),
            "jul": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "jul"),
            "script": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "script"),
            "audio": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "audio"),
            "corrected_txt": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "corrected_txt"),
            "summary_txt": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "summary_txt"),
            "anki": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "anki"),
            "scripted_pdf": self.pipeline_service.check_lesson_file_status(filenames, lesson_id, "scripted_pdf"),
        }

    # =========================================================================
    # [2단계: 존재 유무 데이터 -> DriveSync(1번 탭) 가공 데이터 (줄, 야붙, 완료 등)]
    # =========================================================================
    def format_drive_sync_data(self, lesson_id: str, flags: Dict[str, bool]) -> Dict[str, Any]:
        """존재 유무 플래그를 바탕으로 1번 탭(DriveSync UI) 테이블용 데이터를 가공/조립합니다."""
        note_status = "완료" if flags.get("final_pdf") else ("야붙" if flags.get("yaboot") else ("줄" if flags.get("jul") else "없음"))
        script_status = "O (완료)" if flags.get("script") else ("Whisper AI 전사 필요" if flags.get("audio") else "영상 없음")

        return {
            "수업교시": lesson_id,
            "교수": "-", 
            "강의명": f"강의_{lesson_id}", 
            "필기 상태": note_status,
            "음성 스크립트 상태": script_status,
            "교정 스크립트": flags.get("corrected_txt", False),
            "요약본": flags.get("summary_txt", False),
            "Anki": flags.get("anki", False),
            "스크립트 합본": flags.get("scripted_pdf", False)
        }

    # =========================================================================
    # [3단계: 존재 유무 데이터 -> LLM(3번 탭) 가공 데이터 (교정, 요약 등)]
    # =========================================================================
    def format_llm_pipeline_data(self, lesson_id: str, flags: Dict[str, bool]) -> Tuple[Dict[str, Any], bool]:
        """존재 유무 플래그를 바탕으로 3번 탭(LLM UI) 테이블용 데이터와 전체 완료 여부를 반환합니다."""
        has_final_pdf = flags.get("final_pdf", False)
        has_script_txt = flags.get("script", False)
        has_corrected = flags.get("corrected_txt", False)
        has_summary = flags.get("summary_txt", False)
        anki_done = flags.get("anki", False)

        is_all_completed = has_final_pdf and has_script_txt and has_corrected and has_summary and anki_done

        data = {
            "교시": lesson_id,
            "강의록": has_final_pdf,
            "음성스크립트": has_script_txt,
            "교정": "완료" if has_corrected else "미완료",
            "요약": "완료" if has_summary else "미완료",
            "Anki": "완료" if anki_done else "미완료"
        }
        return data, is_all_completed