"""구글 드라이브 최상단 timetable 스프레드시트 기반 수업 메타데이터 관리 서비스.

이 모듈은 AutoStudy_UI 프로젝트의 Service 계층에 속합니다.
Google Drive 최상단 디렉토리(TARGET_DRIVE_DIR)에 위치한 'timetable' 스프레드시트를
메모리 상에서 실시간 스트리밍(Export API)으로 내려받아 파싱하고,
수업 교시(Lesson ID)별 교수명, 강의명, 과목명, 시험 차수 등의 메타데이터를 제공합니다.
"""

import io
import re
import csv
import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from base.base_service import BaseService
from utils.config import BASE_DIR, Config
from utils.auth_util import get_drive_service
from utils.drive_api import in_memory_download_from_drive


class TimetableService(BaseService):
    """드라이브의 timetable 스프레드시트 파싱 및 수업 메타데이터 매칭 전담 서비스."""

    CACHE_FILE: Path = BASE_DIR / "timetable_cache.json"

    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """TimetableService를 초기화합니다."""
        super().__init__(logger_callback=logger_callback)
        self._timetable_cache: Optional[Dict[str, Dict[str, str]]] = None

    def fetch_timetable_file_id(self, drive_service: Any = None) -> Optional[str]:
        """드라이브 최상단(TARGET_DRIVE_DIR) 폴더에서 timetable 스프레드시트 파일의 ID를 조회합니다.

        Args:
            drive_service (Any, optional): Google Drive API 서비스 객체.

        Returns:
            Optional[str]: 조회된 파일의 ID 또는 None.
        """
        if drive_service is None:
            drive_service = get_drive_service()

        target_folder = Config.TARGET_DRIVE_DIR
        query = (
            f"'{target_folder}' in parents and "
            f"name contains 'timetable' and "
            f"trashed = false"
        )

        try:
            results = drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType)'
            ).execute()

            files = results.get('files', [])
            if not files:
                self._log("⚠️ 드라이브 최상단 폴더에서 'timetable' 파일을 찾지 못했습니다.")
                return None

            # 스프레드시트 타입 우선 선택
            for f in files:
                if f.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
                    return f.get('id')

            # 스프레드시트가 아닌 경우(예: CSV 등) 첫 번째 파일 ID 반환
            return files[0].get('id')
        except Exception as e:
            self._log(f"⚠️ timetable 파일 검색 중 오류 발생: {e}")
            return None

    def fetch_all_timetable_metadata(
        self,
        force_refresh: bool = False,
        drive_service: Any = None
    ) -> Dict[str, Dict[str, str]]:
        """드라이브의 timetable 스프레드시트에서 모든 교시 메타데이터를 조회하여 캐시 및 반환합니다.

        Args:
            force_refresh (bool): 캐시 무시 여부. 기본값 False.
            drive_service (Any, optional): Drive API 서비스 객체.

        Returns:
            Dict[str, Dict[str, str]]: lesson_id -> {professor, lecture_name, subject, exam_round} 맵.
        """
        # 1. 메모리 캐시 반환
        if not force_refresh and self._timetable_cache is not None:
            return self._timetable_cache

        # 2. 로컬 디스크 캐시 반환
        if not force_refresh and self.CACHE_FILE.exists():
            try:
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._timetable_cache = json.load(f)
                    self._log(f"📊 timetable 캐시 로드 완료 (총 {len(self._timetable_cache)}개 교시)")
                    return self._timetable_cache
            except Exception as e:
                self._log(f"⚠️ timetable 캐시 파일 읽기 실패: {e}")

        # 3. 드라이브에서 직접 조회
        if drive_service is None:
            drive_service = get_drive_service()

        file_id = self.fetch_timetable_file_id(drive_service=drive_service)
        if not file_id:
            self._timetable_cache = {}
            return self._timetable_cache

        cache_map: Dict[str, Dict[str, str]] = {}
        try:
            self._log("📥 드라이브 timetable 스프레드시트 다운로드 및 동기화 중...")
            with in_memory_download_from_drive(file_id, mime_type='text/csv', drive_service=drive_service) as fh:
                content = fh.read().decode('utf-8-sig', errors='replace')
                reader = csv.DictReader(io.StringIO(content))

                for row in reader:
                    # 키/값 공백 정리
                    clean_row = {k.strip(): (v.strip() if v else '') for k, v in row.items() if k}

                    lesson_id = (
                        clean_row.get('수업교시') or
                        clean_row.get('교시') or
                        clean_row.get('lesson_id') or
                        ''
                    )
                    if not lesson_id:
                        continue

                    professor = (
                        clean_row.get('교수') or
                        clean_row.get('교수명') or
                        clean_row.get('담당교수') or
                        ''
                    )
                    lecture_name = (
                        clean_row.get('강의명') or
                        clean_row.get('강의주제') or
                        ''
                    )
                    subject = (
                        clean_row.get('과목명') or
                        clean_row.get('계통명') or
                        clean_row.get('블록명') or
                        ''
                    )
                    exam_round = (
                        clean_row.get('시험 차수') or
                        clean_row.get('시험차수') or
                        clean_row.get('차수') or
                        ''
                    )

                    cache_map[lesson_id] = {
                        "professor": professor,
                        "lecture_name": lecture_name,
                        "subject": subject,
                        "exam_round": exam_round
                    }

            self._timetable_cache = cache_map
            # 로컬 파일에 캐시 저장
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f_out:
                    json.dump(self._timetable_cache, f_out, ensure_ascii=False, indent=2)
            except Exception as save_err:
                self._log(f"⚠️ timetable 캐시 파일 저장 실패: {save_err}")

            self._log(f"✅ 드라이브 timetable 메타데이터 로드 완료 (총 {len(cache_map)}개 교시)")
            return self._timetable_cache

        except Exception as e:
            self._log(f"❌ timetable 데이터 다운로드/파싱 실패: {e}")
            self._timetable_cache = {}
            return self._timetable_cache

    def find_timetable_info_for_lesson(
        self,
        lesson_id: str,
        timetable_map: Optional[Dict[str, Dict[str, str]]] = None,
        drive_service: Any = None
    ) -> Dict[str, str]:
        """주어진 교시 ID(예: 0209_12, 0209_1 등)에 대응하는 시간표 메타데이터를 지능적으로 검색합니다.

        Args:
            lesson_id (str): 검색할 교시 ID.
            timetable_map (Optional[Dict[str, Dict[str, str]]]): 사전 로드된 시간표 맵 (없으면 내부 로드).
            drive_service (Any, optional): Drive API 서비스 객체.

        Returns:
            Dict[str, str]: 일치하는 메타데이터 {'professor', 'lecture_name', 'subject', 'exam_round'} 또는 {}.
        """
        if timetable_map is None:
            timetable_map = self.fetch_all_timetable_metadata(drive_service=drive_service)

        if not timetable_map:
            return {}

        # 1. 완전 일치 (Exact match)
        if lesson_id in timetable_map:
            return timetable_map[lesson_id]

        # 2. 콤마 제거 정규화 일치 (예: 0209_1,2 <-> 0209_12)
        norm_target = lesson_id.replace(",", "").strip()
        for k, v in timetable_map.items():
            if k.replace(",", "").strip() == norm_target:
                return v

        # 3. 날짜 및 교시 포함/교집합 관계 매칭 (예: 폴더 0209_1 -> 타임테이블 0209_12 매칭)
        m_target = re.match(r"^(\d{4})_(.*)$", lesson_id)
        if m_target:
            target_date = m_target.group(1)
            target_period_str = m_target.group(2).replace(",", "").strip()
            target_periods = set(target_period_str)

            candidates = []
            for k, v in timetable_map.items():
                m_k = re.match(r"^(\d{4})_(.*)$", k)
                if m_k and m_k.group(1) == target_date:
                    cand_period_str = m_k.group(2).replace(",", "").strip()
                    cand_periods = set(cand_period_str)
                    overlap = target_periods.intersection(cand_periods)
                    if overlap:
                        # 겹치는 교시 수가 많고, 후보의 전체 교시 길이가 짧은(가장 구체적인) 것 우선
                        candidates.append((len(overlap), len(cand_periods), v))

            if candidates:
                candidates.sort(key=lambda x: (-x[0], x[1]))
                return candidates[0][2]

            # 4. 해당 날짜에 수업이 단 1개만 등록된 경우 폴백
            same_date_lessons = [v for k, v in timetable_map.items() if k.startswith(target_date + "_")]
            if len(same_date_lessons) == 1:
                return same_date_lessons[0]

        return {}
