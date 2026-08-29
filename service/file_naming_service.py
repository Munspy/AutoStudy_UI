# service/file_naming_service.py
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from utils.filename_util import normalize_text
from base.base_service import BaseService

class FileNamingService(BaseService):
    """
    의학 강의 자료의 파일명 명명 규칙(도메인 지식)을 전담하여 파싱하고 생성하는 서비스입니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        
        # [최적화] 자주 사용하는 정규식 패턴을 인스턴스 생성 시 한 번만 컴파일(번역)하여 저장해 둡니다.
        # 파일 수백 개를 파싱할 때 엔진 번역 과정이 생략되어 처리 속도가 비약적으로 상승합니다.
        self._meta_pattern = re.compile(r'^(\d{4})_(\d+)(.*)$')
        self._save_name_pattern = re.compile(r'^(\d{4})_([\d,]+)교시')

    def _parse_filename_meta(self, filename: str) -> Dict[str, Any]:
        """내부 유틸: 파일명에서 [날짜(4자리), 교시, 접미사, 확장자]를 추출합니다."""
        norm_name = normalize_text(filename)
        path = Path(norm_name)
        stem, ext = path.stem, path.suffix

        # 미리 만들어둔 컴파일 패턴을 사용해 검색만 수행합니다.
        match = self._meta_pattern.match(stem)
        if match:
            return {
                'date': match.group(1),
                'periods': list(match.group(2)), # 예: "12" -> ['1', '2']
                'periods_str': match.group(2),    
                'rest': match.group(3),
                'ext': ext or '.pdf'
            }
        return {'date': None, 'periods': [], 'periods_str': '', 'rest': stem, 'ext': ext}

    def extract_lesson_id(self, filename: str) -> Optional[str]:
        """파일명에서 '날짜_교시' 형태의 식별자를 추출합니다."""
        meta = self._parse_filename_meta(filename)
        if meta['date'] and meta['periods_str']:
            return f"{meta['date']}_{meta['periods_str']}"
        return None

    def find_file_by_lesson(self, file_list: List[str], target_lesson_id: str, keyword: Optional[str] = None) -> Optional[str]:
        """특정 교시 식별자와 키워드를 모두 포함하는 파일을 찾습니다."""
        target_lesson_id = normalize_text(target_lesson_id)
        search_keyword = normalize_text(keyword) if keyword else ""
        
        for filename in file_list:
            if self.extract_lesson_id(filename) == target_lesson_id:
                norm_name = normalize_text(filename)
                if not search_keyword or search_keyword in norm_name:
                    return filename
        return None

    def filter_files_by_date_range(
        self, 
        file_list: List[Any], 
        start_mmdd: str, 
        end_mmdd: str
    ) -> List[Any]:
        """
        파일 목록에서 지정된 날짜(MMdd) 범위에 해당하는 파일만 필터링하여 반환합니다.
        문자열 리스트(Local)와 딕셔너리 리스트(Drive API) 모두 지원합니다.
        """
        filtered_files = []
        
        for f in file_list:
            # 다형성 지원: 요소가 딕셔너리(드라이브 결과)이면 'name' 추출, 아니면 문자열 변환
            name = f.get('name', '') if isinstance(f, dict) else str(f)
            
            # 기존 파싱 엔진(사전 컴파일된 정규식) 재사용
            meta = self._parse_filename_meta(name)
            
            if meta['date']:
                file_date = meta['date']
                # 단순 문자열 대소 비교로 해당 기간 내에 있는지 판별
                if start_mmdd <= file_date <= end_mmdd:
                    filtered_files.append(f)
                    
        self._log(f"📅 [FileNaming] 날짜 필터링 완료: {len(file_list)}개 중 {len(filtered_files)}개 추출 ({start_mmdd}~{end_mmdd})")
        return filtered_files

    def generate_merged_filename(self, filenames: List[str]) -> str:
        """여러 파일명을 기반으로 논리적으로 병합된 새 파일명을 생성합니다."""
        if not filenames: 
            return "merged_output.txt"
            
        first_meta = self._parse_filename_meta(filenames[0])
        if not first_meta['date']:
            return f"merged_output{first_meta['ext']}"
            
        # 중복 방지를 위해 집합(Set)을 사용합니다.
        all_periods: Set[str] = set()
        for f in filenames:
            m = self._parse_filename_meta(f)
            all_periods.update(m['periods'])
            
        # 교시 문자를 정렬하여 조합합니다. (예: ['2', '1'] -> "12")
        sorted_periods = sorted(list(all_periods))
        
        merged_name = f"{first_meta['date']}_{''.join(sorted_periods)}{first_meta['rest']}{first_meta['ext']}"
        self._log(f"📝 [FileNaming] 병합 파일명 생성됨: {merged_name}")
        
        return merged_name

    def generate_split_filenames(self, filename: str) -> List[str]:
        """하나의 파일명을 두 개로 분할할 때 사용할 이름 리스트를 생성합니다."""
        meta = self._parse_filename_meta(filename)
        if meta['date'] and len(meta['periods']) == 2:
            p1, p2 = meta['periods']
            split_names = [
                f"{meta['date']}_{p1}{meta['rest']}{meta['ext']}",
                f"{meta['date']}_{p2}{meta['rest']}{meta['ext']}"
            ]
        else:
            stem = Path(normalize_text(filename)).stem
            split_names = [f"{stem}_1{meta['ext']}", f"{stem}_2{meta['ext']}"]
            
        self._log(f"✂️ [FileNaming] 분할 파일명 생성됨: {split_names}")
        return split_names

    def extract_save_name(self, base_name: str) -> str:
        """UI에 표시할 깔끔한 저장용 파일명을 추출합니다."""
        norm_name = normalize_text(base_name)
        # 미리 만들어둔 컴파일 패턴을 사용해 검색만 수행합니다.
        match = self._save_name_pattern.search(norm_name)
        
        if match:
            clean_period = match.group(2).replace(',', '')
            return f"{match.group(1)}_{clean_period}.pdf"
        return f"{norm_name}_합본.pdf"

    def suggest_pdf_merge_name(self, file_names: List[str]) -> str:
        """선택된 여러 파일명을 분석해 UI 저장 입력창에 추천할 파일명을 반환합니다."""
        if len(file_names) < 2:
            return ""
            
        is_all_scripted = all('_scripted.pdf' in f.lower() for f in file_names)
        dates: Set[str] = set()
        periods: Set[str] = set()
        
        for f in file_names:
            meta = self._parse_filename_meta(f)
            if meta['date']:
                dates.add(meta['date'])
                periods.update(meta['periods'])
                
        if len(dates) == 1:
            date_str = dates.pop()
            if is_all_scripted:
                suggested = f"{date_str}_merged_scripted.pdf"
            else:
                # 추천 파일명 생성 시에도 중복 교시 제거 및 오름차순 정렬 적용
                sorted_periods = sorted(list(periods))
                suggested = f"{date_str}_{''.join(sorted_periods)}.pdf"
                
            self._log(f"💡 [FileNaming] PDF 병합 파일명 제안: {suggested}")
            return suggested
        
        self._log("💡 [FileNaming] 날짜가 불일치하여 기본 병합 파일명을 제안합니다.")
        return "merged_output.pdf"