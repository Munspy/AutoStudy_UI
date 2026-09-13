"""LLM 작업 큐 관련 데이터 전송 객체(DTO) 모듈.

이 모듈은 Gemini Processing UI에서 작업 큐를 조립하고
LLMTaskWorker 및 AiPipelineService로 전달하는 작업 단위를 규격화합니다.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class LlmTask:
    """LLM 작업 큐의 단일 작업 항목.

    GeminiProcessingUi에서 조립하여 LLMTaskWorker.task_queue 리스트의
    원소로 사용되고, AiPipelineService에서 소비하는 데이터의 규격입니다.

    Attributes:
        row: 해당 작업이 표시되는 UI 테이블의 행 인덱스.
        col: 해당 작업이 표시되는 UI 테이블의 열 인덱스.
        task_type: 작업 유형 문자열 ("교정" / "요약" / "Anki").
        model: 사용할 Gemini 모델 이름의 풀(Pool) 리스트.
        base_name: 수업 교시 식별자 (예: "0901_1").
    """
    row: int = 0
    col: int = 0
    task_type: str = ""
    model: List[str] = field(default_factory=list)
    base_name: str = ""

    def to_dict(self) -> dict:
        """기존 dict 기반 코드와의 하위 호환을 위한 직렬화 메서드."""
        return {
            "row": self.row,
            "col": self.col,
            "task_type": self.task_type,
            "model": self.model,
            "base_name": self.base_name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LlmTask":
        """기존 dict에서 LlmTask 객체를 생성하는 팩토리 메서드."""
        return cls(
            row=d.get("row", 0),
            col=d.get("col", 0),
            task_type=d.get("task_type", ""),
            model=d.get("model", []),
            base_name=d.get("base_name", ""),
        )

