"""Anki 카드 생성 관련 데이터 전송 객체(DTO) 모듈.

이 모듈은 AnkiGenerationService 내부에서 파싱된 카드 유형별
텍스트 줄 목록을 규격화합니다.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class AnkiCardSet:
    """파싱된 Anki 카드 세트.

    AnkiGenerationService.parse_llm_output()이 반환하는
    카드 유형별 텍스트 리스트를 묶은 객체입니다.

    Attributes:
        basic: Basic 유형 카드의 텍스트 줄 리스트 (앞면 / 뒷면).
        mcq: MCQ(객관식) 유형 카드의 텍스트 줄 리스트.
        cloze: Cloze(빈칸) 유형 카드의 텍스트 줄 리스트.
    """
    basic: List[str] = field(default_factory=list)
    mcq: List[str] = field(default_factory=list)
    cloze: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "AnkiCardSet":
        return cls(
            basic=d.get("Basic", []),
            mcq=d.get("MCQ", []),
            cloze=d.get("Cloze", []),
        )

    def to_dict(self) -> dict:
        """기존 dict 기반 코드와의 하위 호환을 위한 직렬화 메서드."""
        return {
            "Basic": self.basic,
            "MCQ": self.mcq,
            "Cloze": self.cloze,
        }

