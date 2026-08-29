"""구글 드라이브 동기화 및 학습 자료 파이프라인 상태 관리 서비스.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
애플리케이션의 핵심 비즈니스 로직 중 하나로, 구글 드라이브(클라우드)와 로컬 파일 시스템 간의 
데이터 스캔 및 상태 매핑을 담당합니다. 

이 서비스는 파일의 존재 여부(필기 PDF, 오디오 파일, Whisper 추출 텍스트, Gemini LLM 요약본, Anki 패키지 등)를 
추적하여 각 '수업 교시(Lesson ID)'별 파이프라인 진행 상태(어떤 작업이 완료되었고 어떤 작업이 대기 중인지)를 
하나의 데이터 구조로 취합합니다. 이후 Controller 계층으로 반환되어 메인 UI의 데이터 테이블(Data Grid)에 
시각적으로 렌더링되도록 중개 역할을 수행합니다.
"""

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
    """드라이브 및 로컬 폴더의 파일을 스캔하여 각 수업 교시별 동기화 상태를 판별하는 단일 책임 서비스.

    구글 드라이브 API 통신(`get_drive_service`, `get_all_drive_files`), 파일 시스템 스캔, 
    도메인 로직 처리(`FileNamingService`, `PipelineStatusService`)에 대한 의존성을 묶어 
    Controller가 복잡한 상태 취합 로직에 관여하지 않도록 캡슐화(Encapsulation)합니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """DriveSyncService를 초기화하고 필요한 의존성 객체들을 주입받아 생성합니다.

        Args:
            logger_callback (Optional[Callable[[str], None]], optional): 
                백그라운드 스레드에서 발생하는 이벤트나 에러를 Controller를 통해 메인 UI 스레드로 
                안전하게 전달하기 위한 로거 콜백 함수. Defaults to None.
        """
        # BaseService 초기화 시 콜백을 한 번만 등록하여 이후 self._log()에서 자동 사용되도록 설정
        super().__init__(logger_callback=logger_callback)
        
        # 다른 서비스 파일들과의 통일성을 위해 직접 호출 방식 유지
        self.drive_service = get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR
        
        # 도메인 서비스 인스턴스화
        self.naming_service = FileNamingService()
        self.pipeline_service = PipelineStatusService(self.drive_service)

    def fetch_all_files(self, local_path: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """구글 드라이브와 로컬 시스템의 모든 파일 목록을 재귀적으로 스캔하여 수집합니다.

        자동화 모니터링 시스템에서 클라우드와 로컬 저장소 간의 상태 동기화를 맞추기 위해 필수적으로 선행되는 함수입니다. 
        대량의 파일이 오가는 비동기 환경에서 네트워크 지연, API 할당량 초과, 사용자 디렉토리 권한 없음 등 
        다양한 예외 상황이 발생할 수 있습니다. 
        
        따라서 각각의 I/O 작업(네트워크, 디스크)을 개별 `try-except` 블록으로 격리하여 방어적으로 프로그래밍했습니다. 
        만약 드라이브 스캔이 실패하더라도 로컬 스캔은 정상적으로 시도되며, 둘 다 실패할 경우 빈 리스트를 반환하여 
        UI가 멈추는(Freezing) 치명적 에러를 방지합니다. 
        또한 macOS 환경에서 발생하는 불필요한 시스템 숨김 파일(`.DS_Store`) 및 오피스 임시 파일(`~$`)을 
        선제적으로 필터링하여 비즈니스 로직의 오작동을 차단합니다.

        Args:
            local_path (str): 파일을 스캔할 로컬 디렉토리의 절대 또는 상대 경로 문자열.

        Returns:
            Tuple[List[Dict[str, Any]], List[str], List[str]]:
                - 첫 번째 요소: 드라이브 파일들의 원본 메타데이터 딕셔너리 리스트.
                - 두 번째 요소: 드라이브 파일들의 파일명 문자열만 추출한 리스트.
                - 세 번째 요소: 로컬 시스템에서 스캔(필터링 완료)된 파일명 리스트.
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
        """무작위 파일 이름 목록에서 정규화된 교시(Lesson ID)를 추출하고 조건에 맞게 정렬하여 반환합니다.

        수백 개의 임의 파일들(예: '1004_1_필기.pdf', '1004_1_음성.mp3') 속에서 핵심 도메인 식별자인 
        '수업 교시(Lesson ID)' 단위(예: '1004_1')를 뽑아내어 중복 없는 집합(Set)으로 구축하는 데이터 전처리 로직입니다. 
        사용자가 메인 UI에서 '특정 날짜 범위' 등으로 검색 필터를 걸 경우(`search_mode == "DATE"`), 
        도출된 Lesson ID 내장 날짜 정보를 바탕으로 문자열 슬라이싱 비교를 수행하여 범위를 벗어나는 교시들을 
        결과 목록에서 제외시킵니다. 
        파일 네이밍 컨벤션이 깨진(IndexError 유발) 불량 파일이 발견되더라도 무시(continue)하고 스킵하여 안정성을 유지합니다.

        Args:
            filenames (List[str]): 교시 아이디를 추출할 원본 파일명 리스트.
            search_mode (str): 검색 및 필터링 모드 (예: "ALL" 전체 검색, "DATE" 날짜 범위 검색 등).
            filter_value (Any): 필터링에 사용될 기준 값. "DATE" 모드일 경우 시작 날짜와 종료 날짜 문자열 튜플.

        Returns:
            List[str]: 필터링을 통과하고 오름차순으로 정렬된 고유 교시(Lesson ID) 문자열 리스트.
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
        """단일 교시(Lesson ID)를 기준으로 모든 파일의 존재 여부를 평가하여 통합 상태 데이터를 조립합니다.

        자동화 파이프라인의 핵심 상태를 정의하는 조립부(Assembler)입니다.
        입력된 단일 `lesson_id` 하나에 대해, 드라이브 상에 '원본 필기 파일', 'Whisper 전사 텍스트', 
        'LLM 교정본 및 요약본', 'Anki 추출 데이터'가 물리적으로 존재하는지 `PipelineStatusService`를 통해 
        계층적으로 검사합니다. 
        
        파이프라인의 진행 상황을 '완료', '전사 필요', '영상 없음' 등 비즈니스 친화적인 자연어 상태(Status)로 변환하며, 
        이렇게 생성된 단일 딕셔너리는 UI 레이어의 데이터 그리드(Table)의 한 행(Row)으로 직접 매핑(Mapping)됩니다.
        네트워크 지연이나 JSON 파싱 에러 등으로 상태 조회가 실패하더라도 전체 스캔 프로세스를 죽이지 않도록 
        오류 전용 더미(Dummy) 데이터를 반환하는 예외 처리 방어선이 구축되어 있습니다.

        Args:
            lesson_id (str): 상태를 조회하고 조립할 기준이 되는 수업 교시 식별자(ID).
            drive_files (List[Dict[str, Any]]): 구글 드라이브에서 가져온 파일들의 상세 메타데이터 리스트. (LLM JSON 읽기 시 사용)
            drive_filenames (List[str]): 단순 파일 이름 검색 효율을 위한 파일명 문자열 리스트.
            json_cache (Optional[Dict[str, Any]], optional): 반복적인 드라이브 통신을 줄이기 위한 
                JSON 내용 메모리 캐싱 변수. Defaults to None.

        Returns:
            Dict[str, Any]: 파이프라인의 각 단계별 완료/대기 상태와 불리언 플래그 값들이 
                포함된 통합 상태 데이터 딕셔너리.
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