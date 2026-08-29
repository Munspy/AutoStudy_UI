from typing import List, Optional, Callable
from base.base_service import BaseService

class TextProcessingService(BaseService):
    """
    텍스트 데이터의 내용을 분석하고, 규칙에 따라 병합/분할하는
    순수 도메인 비즈니스 로직을 담당합니다. (파일 I/O 로직 제거)
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        # [최적화 2] BaseService 초기화를 통해 로깅 시스템 통합
        super().__init__(logger_callback=logger_callback)

    def split_text_content(self, text_content: str) -> List[str]:
        """텍스트가 정확히 한 번의 줄바꿈으로 두 부분으로 나뉘는지 검증하고 분할합니다."""
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
        """여러 텍스트 콘텐츠를 병합 규칙에 따라 하나로 합칩니다."""
        # 안전한 조인을 위해 내부 요소들의 공백을 한 번 더 제거
        return "\n\n".join(c.strip() for c in contents if c.strip())