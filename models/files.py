"""파일 관련 워커 반환값 데이터 전송 객체(DTO) 모듈.

이 모듈은 각 Worker의 do_work()가 finished_signal을 통해
UI/Controller로 전달하는 파일 데이터 결과의 규격을 정의합니다.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ParsedFilename:
    """파일명 파싱 결과 데이터.

    FileNamingService._parse_filename_meta()가 반환하는 딕셔너리를
    타입 안전하게 대체합니다.

    Attributes:
        date: MMDD 형식의 날짜 문자열 (예: "0901"). 매칭 실패 시 None.
        periods: 교시 숫자 리스트 (예: "12" -> ['1', '2']).
        periods_str: 교시를 합친 문자열 (예: "12").
        rest: 교시 이후 부가 설명 (예: "_야붙").
        ext: 파일 확장자 (예: ".pdf").
    """
    date: Optional[str] = None
    periods: List[str] = field(default_factory=list)
    periods_str: str = ""
    rest: str = ""
    ext: str = ".pdf"

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedFilename":
        """기존 dict에서 ParsedFilename 객체를 생성하는 팩토리 메서드."""
        return cls(
            date=d.get("date"),
            periods=d.get("periods", []),
            periods_str=d.get("periods_str", ""),
            rest=d.get("rest", ""),
            ext=d.get("ext", ".pdf"),
        )

    def to_dict(self) -> dict:
        """기존 dict 기반 코드와의 하위 호환을 위한 직렬화 메서드."""
        return {
            "date": self.date,
            "periods": self.periods,
            "periods_str": self.periods_str,
            "rest": self.rest,
            "ext": self.ext,
        }


@dataclass
class RawDataLoadResult:
    """RawDataLoadWorker가 반환하는 원시 데이터 로드 결과.

    raw_data_worker.py의 do_work()가 finished_signal로 방출하고,
    RawDataEditorUi._on_load_finished()가 소비하는 데이터의 규격입니다.

    Attributes:
        pdf_bytes: 렌더링할 PDF 파일의 바이트 데이터.
        text_str: 파싱할 스크립트 텍스트 전체 내용.
        text_file: 구글 드라이브 텍스트 파일 메타데이터 딕셔너리 (id, name, parents 포함).
    """
    pdf_bytes: bytes = b""
    text_str: str = ""
    text_file: Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "RawDataLoadResult":
        return cls(
            pdf_bytes=d.get("pdf_bytes", b""),
            text_str=d.get("text_str", ""),
            text_file=d.get("text_file", {}),
        )


@dataclass
class PdfPreviewResult:
    """PdfPreviewWorker가 반환하는 PDF 미리보기 로드 결과.

    pdf/preview_worker.py의 do_work()가 finished_signal로 방출하고,
    PdfSplitUi가 소비하는 데이터의 규격입니다.

    Attributes:
        local_path: 로컬 또는 임시 저장된 PDF 파일 경로.
        total_pages: 해당 PDF의 총 페이지 수.
    """
    local_path: str = ""
    total_pages: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "PdfPreviewResult":
        return cls(
            local_path=d.get("local_path", ""),
            total_pages=d.get("total_pages", 0),
        )


@dataclass
class TranscriptLoadResult:
    """TranscriptLoadWorker가 반환하는 스크립트 로드 결과.

    transcript/transcript_worker.py의 do_work()가 finished_signal로 방출하고,
    TranscriptMergeSplitUi가 소비하는 데이터의 규격입니다.

    Attributes:
        filenames: 로드된 파일 이름 목록.
        contents: 각 파일 이름에 대응하는 텍스트 내용 목록.
    """
    filenames: List[str] = field(default_factory=list)
    contents: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "TranscriptLoadResult":
        return cls(
            filenames=d.get("filenames", []),
            contents=d.get("contents", []),
        )

