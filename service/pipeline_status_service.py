"""파이프라인 상태 점검 및 메타데이터 추적 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
의학 학습 자료 자동화 파이프라인의 각 단계(PDF 추출 -> Whisper STT -> LLM 교정 -> 요약 -> Anki)가 
현재 단일 교시(Lesson)에 대해 어디까지 진행되었는지 진단하고 상태를 평가하는 역할을 전담합니다. 

단순 파일 유무 검사를 넘어, `done.json`과 같은 상태(State) 기록 파일을 다운로드하고 파싱하여 
비즈니스 로직(AI 작업 성공 여부 등)의 완결성을 입증합니다. 이 서비스의 출력 결과는 주로 
`DriveSyncService`를 거쳐 UI의 대시보드 테이블에 시각화(렌더링)됩니다.
"""

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
    """단일 교시(Lesson)의 파이프라인 진행 상태 및 연관 파일 검증을 전담하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 파이프라인의 다음 작업을 직접 '실행'하지 않고, 
    오직 현재 드라이브와 로컬에 어떤 결과물들이 있는지 '진단'하고 '조회'하는 역할만 수행합니다.

    의존성:
    - 상태 확인을 위한 문자열 파싱은 `FileNamingService`에 위임합니다.
    - 클라우드 파일 검사를 위해 `utils.drive_api`를 통해 Google Drive API와 통신합니다.
    """
    
    def __init__(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        drive_service: Optional[Any] = None,
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """PipelineStatusService 인스턴스를 초기화합니다.        Args:
            drive_service (Optional[Any], optional): 인증된 구글 드라이브 API 서비스 리소스 객체. Defaults to None.
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 처리 로그를 메인 UI로 
                전달하기 위한 콜백 함수. 하위 `FileNamingService`에도 동일하게 주입됩니다. Defaults to None.
        """
        # [최적화 2] BaseService 초기화 누락 수정으로 일관된 로깅 시스템 활성화
        super().__init__(logger_callback=logger_callback)
        self.drive_service = drive_service
        self.json_cache: Dict[str, Any] = {}
        # 하위 서비스에도 로깅 콜백 주입
        self.naming_service = FileNamingService(logger_callback=logger_callback)

    def check_lesson_file_status(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        file_list: List[str], 
        target_lesson_id: str, 
        file_type: FileType
    ) -> bool:
        """[파이프라인 진행도 검증] 특정 단계의 파이프라인 결과물 파일이 리스트에 존재하는지 확인합니다.        파일 시스템이나 클라우드를 직접 스캔하지 않고, 미리 긁어온(Fetched) 단순 파일명 배열(`file_list`)을 
        메모리 상에서 빠르게 스캔합니다. 
        `FileType`에 정의된 8가지 주요 파이프라인 마일스톤에 대해 `FileNamingService`의 
        정규식 필터링 능력을 빌려 해당 교시(`target_lesson_id`)에 속한 파일이 물리적으로 존재하는지 
        Boolean 값으로 반환합니다. 이 값은 UI의 진행도 바(Progress Bar)나 상태 텍스트 갱신에 직접적으로 사용됩니다.

        Args:
            file_list (List[str]): 검사 대상이 되는 전체 파일명 문자열 리스트.
            target_lesson_id (str): 검사할 특정 수업의 교시 식별자 (예: '1004_1').
            file_type (FileType): 파이프라인의 특정 단계를 지칭하는 Enum 형태의 문자열 
                (예: 'script', 'anki', 'audio' 등).

        Returns:
            bool: 해당 교시에 매칭되는 지정된 타입의 파일이 리스트 내에 존재하면 True, 없으면 False.
        """
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
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        drive_files: List[Dict[str, Any]], 
        target_lesson_id: str
    ) -> tuple[bool, bool]:
        """드라이브에 저장된 `done.json`을 열어, AI 교정과 요약 작업이 내부에 실제로 기록되었는지 논리적으로 확인합니다.        물리적으로 파일(`done.json`)이 존재하더라도, 중간에 시스템 오류로 인해 안의 내용이 비어있을 수 있습니다. 
        이 메서드는 파일을 디스크로 다운로드하는 오버헤드 대신 `in_memory_download_from_drive`를 사용해 
        RAM 상에서 즉시 JSON을 디코딩합니다. 또한 반복 조회를 막기 위해 `self.json_cache`에 디코딩된 
        딕셔너리를 캐싱합니다. JSON 내부의 `corrected_text`와 `summary` 키를 파싱하여, 
        LLM 파이프라인의 세부적인 완결성을 2개의 불리언(Boolean) 값으로 명확하게 진단해냅니다.

        Args:
            drive_files (List[Dict[str, Any]]): 구글 드라이브에서 스캔된 파일들의 메타데이터 딕셔너리 리스트.
            target_lesson_id (str): 상태를 조회할 대상 수업 교시 식별자.

        Returns:
            tuple[bool, bool]: 
                - 첫 번째 불리언: 음성 스크립트 교정(Correction) 완료 여부.
                - 두 번째 불리언: 단권화 요약(Summary) 완료 여부.

        Raises:
            ValueError: 인스턴스 초기화 시 구글 드라이브 서비스가 주입되지 않은 상태로 호출될 경우.
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
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        start_date_str: str, 
        end_date_str: str, 
        file_extension: str = ".pdf"
    ) -> List[Dict[str, Any]]:
        """드라이브에서 특정 확장자를 가진 파일 중, 지정된 날짜 범위(MMDD)에 해당하는 파일 목록만 추출 반환합니다.        사용자가 UI의 달력 위젯(Calendar Widget)에서 특정 기간을 선택하고 해당 기간 내의 
        PDF 학습 자료만 모아보려 할 때 호출되는 편의성(Utility) 메서드입니다. 
        모든 드라이브 파일을 긁어온 뒤, 1차로 확장자를 필터링하여 루프의 횟수를 줄이고, 
        2차로 `FileNamingService`의 도메인 파서(Parser)에 위임하여 파일명 내에 숨겨진 날짜 메타데이터를 
        기간 문자열(`start_mmdd`, `end_mmdd`)과 비교합니다.

        Args:
            start_date_str (str): 검색을 시작할 기준 날짜 문자열 ("YYYY-MM-DD" 포맷).
            end_date_str (str): 검색을 종료할 기준 날짜 문자열 ("YYYY-MM-DD" 포맷).
            file_extension (str, optional): 찾고자 하는 대상 파일의 확장자. Defaults to ".pdf".

        Returns:
            List[Dict[str, Any]]: 해당 날짜 범위에 속하는 파일들의 드라이브 메타데이터 딕셔너리 리스트.

        Raises:
            ValueError: 인스턴스 초기화 시 구글 드라이브 서비스가 주입되지 않은 상태로 호출될 경우.
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