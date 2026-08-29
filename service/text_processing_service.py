"""텍스트 데이터 파싱 및 조작 순수 도메인 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
파일 시스템 접근(I/O)이나 외부 API 네트워크 통신 없이, 오직 메모리 상에 존재하는 
문자열(Text) 데이터의 내용을 분석하고 비즈니스 규칙에 따라 병합(Merge) 및 분할(Split)하는 
순수 도메인 로직(Pure Domain Logic)만을 제공합니다.

Whisper AI를 통해 추출된 음성 스크립트나 Gemini LLM으로 전송할 프롬프트, 
또는 Anki/Notion 연동 과정에서 텍스트의 구조적인 유효성을 검증하고 가공할 때 
Controller 또는 백그라운드 Worker 계층에 의해 호출되어 텍스트 데이터의 무결성을 보장합니다.
"""

from typing import List, Optional, Callable
from base.base_service import BaseService

class TextProcessingService(BaseService):
    """텍스트 데이터의 내용을 분석하고 규칙에 따라 병합/분할을 수행하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 파일의 읽기/쓰기나 클라우드 업로드 같은 
    인프라성 작업은 철저히 배제하고 오직 텍스트 문자열 그 자체의 조작만을 책임집니다. 
    UI 이벤트 핸들러(Controller)나 비동기 파이프라인(Worker)에서 텍스트 기반의 비즈니스 룰 
    검증이 필요할 때 호출되며, 부모 클래스인 `BaseService`를 상속받아 일관된 로깅 시스템을 공유합니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """TextProcessingService 인스턴스를 초기화합니다.

        Args:
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 스레드 등에서 
                발생한 문자열 처리 결과 및 오류 로그를 메인 UI 스레드로 전달하기 위한 콜백 함수. 
                Defaults to None.
        """
        # [최적화 2] BaseService 초기화를 통해 로깅 시스템 통합
        super().__init__(logger_callback=logger_callback)

    def split_text_content(self, text_content: str) -> List[str]:
        """텍스트가 정확히 한 번의 줄바꿈으로 두 부분으로 나뉘는지 검증하고 분할합니다.

        자동화된 학습 자료 파이프라인에서 특정 텍스트 데이터(예: 특정 슬라이드의 질문과 답변, 
        또는 명확하게 두 파트로 나뉘어야 하는 스크립트 본문)가 규칙에 맞게 작성되었는지 검증할 때 사용됩니다. 
        대량의 데이터를 비동기 Worker가 백그라운드에서 처리할 때, 사용자의 입력 실수나 
        LLM의 포맷 이탈로 인해 텍스트가 1조각이거나 3조각 이상으로 쪼개질 경우, 하위 시스템(Anki 등)이 
        심각한 오작동을 일으킬 수 있습니다. 
        
        따라서 이 메서드는 `splitlines()`를 이용해 운영체제 환경(\n, \r\n)에 무관하게 텍스트를 쪼갠 뒤, 
        그 결과가 정확히 2개인지 엄격하게 검사(Fail-fast)하여 비정형 데이터의 구조적 위험을 
        파이프라인 최전방에서 차단합니다.

        Args:
            text_content (str): 검증 및 분할을 수행할 원본 문자열 데이터.

        Returns:
            List[str]: 공백이 제거(strip)된 정확히 2개의 문자열 요소를 가지는 리스트.

        Raises:
            ValueError: 입력된 텍스트가 비어 있거나, 엔터(줄바꿈) 기준으로 나누었을 때 
                정확히 2개의 조각으로 분리되지 않는 경우(구조적 규칙 위반 시) 발생합니다.
        """
        if not text_content:
            self._log("⚠️ 입력된 텍스트가 비어 있습니다.")
            raise ValueError("입력된 텍스트가 비어 있습니다.")

        # [최적화 1] splitlines()를 사용하여 운영체제(\n, \r\n) 무관하게 안전하게 분할
        # [최적화 3] List[str] 타입 힌트를 통해 명확한 반환 타입 보장
        parts: List[str] = [p.strip() for p in text_content.splitlines() if p.strip()]
        
        if len(parts) != 2:
            # 에러 발생 시 명확한 사유를 로깅하고, 분할된 개수를 포함하여 예외 발생
            error_msg = f"엔터(줄바꿈)가 정확히 한 번 적용되어 두 부분으로 나뉘어야 합니다. (현재 분할된 조각 수: {len(parts)}개)"
            self._log(f"❌ 텍스트 분할 오류: {error_msg}")
            raise ValueError(error_msg)
            
        return parts

    def merge_text_contents(self, contents: List[str]) -> str:
        """여러 텍스트 콘텐츠를 일정한 병합 규칙에 따라 하나의 문자열로 합칩니다.

        자동화 파이프라인에서 여러 개로 분할되어 개별 처리된 스크립트 조각들이나, 
        다수의 교시(Lesson)에서 추출된 LLM 요약 결과들을 최종적으로 하나의 단일 문서나 
        프롬프트로 조립(Assembly)할 때 호출됩니다. 
        
        단순한 문자열 이어붙이기가 아니라, 각 조각 내부의 불필요한 앞뒤 공백을 선제적으로 제거한 후 
        더블 라인브레이크(`\n\n`)를 삽입하여 문단 간의 논리적 구분을 명확히 유지하도록 설계되어 
        이후 PDF 렌더링이나 Notion 동기화 시 시각적 레이아웃이 깨지지 않도록 보장합니다.

        Args:
            contents (List[str]): 하나로 병합할 대상이 되는 개별 문자열들의 리스트.

        Returns:
            str: 리스트 내의 각 문자열 요소가 두 줄 바꿈(`\n\n`)으로 구분되어 하나로 연결된 최종 완성 문자열.
        """
        # 안전한 조인을 위해 내부 요소들의 공백을 한 번 더 제거
        return "\n\n".join(c.strip() for c in contents if c.strip())