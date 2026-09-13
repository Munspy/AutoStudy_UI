"""수업 교시(Lesson) 관련 데이터 전송 객체(DTO) 모듈.

이 모듈은 수업 한 교시(Lesson)의 메타데이터, 파일 존재 여부 플래그,
DriveSync UI 테이블 행, LLM 파이프라인 UI 테이블 행을 규격화한 dataclass를 정의합니다.
"""

from dataclasses import dataclass, field


@dataclass
class LessonMeta:
    """수업 교시의 식별 정보 및 메타데이터.

    유튜브 재생목록, 시간표 스프레드시트, 드라이브 동기화 서비스 등에서
    공통으로 사용되는 교수/강의 정보를 하나의 규격화된 객체로 관리합니다.

    Attributes:
        professor: 강의 교수명. 알 수 없으면 "-".
        lecture_name: 강의(수업) 이름.
        subject: 과목명. 없으면 빈 문자열.
        exam_round: 시험 차수 (예: "1차"). 없으면 빈 문자열.
        video_url: 유튜브 영상 URL. 없으면 빈 문자열.
        raw_title: 유튜브 영상 원본 제목. 없으면 빈 문자열.
    """
    professor: str = "-"
    lecture_name: str = ""
    subject: str = ""
    exam_round: str = ""
    video_url: str = ""
    raw_title: str = ""


@dataclass
class LessonFileFlags:
    """수업 교시의 파이프라인 파일 존재 여부 플래그 묶음.

    get_lesson_file_flags()가 반환하는 True/False 상태값들을
    key 오타 없이 안전하게 다루기 위해 사용합니다.

    Attributes:
        final_pdf: 최종 필기 PDF 존재 여부.
        yaboot: 야붙 필기 파일 존재 여부.
        jul: 줄 필기 파일 존재 여부.
        script: 음성 스크립트(텍스트) 파일 존재 여부.
        audio: 음성 파일(WAV) 존재 여부.
        corrected_txt: 교정 스크립트 존재 여부.
        summary_txt: 요약본 파일 존재 여부.
        anki: Anki 카드 파일 존재 여부.
        scripted_pdf: 스크립트 합본 PDF 존재 여부.
    """
    final_pdf: bool = False
    yaboot: bool = False
    jul: bool = False
    script: bool = False
    audio: bool = False
    corrected_txt: bool = False
    summary_txt: bool = False
    anki: bool = False
    scripted_pdf: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "LessonFileFlags":
        """기존 코드의 dict에서 LessonFileFlags 객체를 생성하는 팩토리 메서드."""
        return cls(
            final_pdf=d.get("final_pdf", False),
            yaboot=d.get("yaboot", False),
            jul=d.get("jul", False),
            script=d.get("script", False),
            audio=d.get("audio", False),
            corrected_txt=d.get("corrected_txt", False),
            summary_txt=d.get("summary_txt", False),
            anki=d.get("anki", False),
            scripted_pdf=d.get("scripted_pdf", False),
        )


@dataclass
class LessonSyncRow:
    """DriveSync(1번 탭) 테이블의 행 데이터.

    drive_sync_service.format_drive_sync_data()가 반환하고
    DriveSyncUi.render_table()이 소비하는 데이터의 규격입니다.

    Attributes:
        lesson_id: 수업 교시 식별자 (예: "0901_1").
        professor: 강의 교수명.
        lecture_name: 강의 이름.
        subject: 과목명.
        note_status: 필기 상태 문자열 ("완료" / "야붙" / "줄" / "없음").
        script_status: 음성 스크립트 상태 문자열.
        corrected_txt: 교정 스크립트 완료 여부.
        summary_txt: 요약본 완료 여부.
        anki: Anki 카드 완료 여부.
        scripted_pdf: 스크립트 합본 완료 여부.
    """
    lesson_id: str = ""
    professor: str = "-"
    lecture_name: str = ""
    subject: str = ""
    note_status: str = "없음"
    script_status: str = "영상 없음"
    corrected_txt: bool = False
    summary_txt: bool = False
    anki: bool = False
    scripted_pdf: bool = False


@dataclass
class LlmPipelineRow:
    """Gemini Processing(3번 탭) 테이블의 행 데이터.

    drive_sync_service.format_llm_pipeline_data()가 반환하고
    GeminiProcessingUi.render_scan_results()가 소비하는 데이터의 규격입니다.

    Attributes:
        lesson_id: 수업 교시 식별자.
        has_final_pdf: 최종 필기 PDF 존재 여부.
        has_script_txt: 음성 스크립트 존재 여부.
        corrected: 교정 완료 여부 ("완료" / "미완료").
        summary: 요약 완료 여부 ("완료" / "미완료").
        anki: Anki 완료 여부 ("완료" / "미완료").
        is_all_completed: 모든 파이프라인 작업이 완료되었는지 여부.
    """
    lesson_id: str = ""
    has_final_pdf: bool = False
    has_script_txt: bool = False
    corrected: str = "미완료"
    summary: str = "미완료"
    anki: str = "미완료"
    is_all_completed: bool = False

