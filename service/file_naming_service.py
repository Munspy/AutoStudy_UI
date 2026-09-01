"""파일명 파싱 및 도메인 기반 명명 규칙 처리 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 파이프라인 중 **Service(서비스) 계층**에 속합니다.
애플리케이션 전반에서 사용되는 의학 강의 자료 파일들(PDF, 오디오 등)의 복잡한 네이밍 컨벤션을 
중앙 집중적으로 파싱하고, 새로운 파일명을 규격에 맞게 생성하는 책임을 가집니다.

Controller, DriveSyncService, Worker 등 다른 계층들이 파일의 논리적 메타데이터(예: 수업 날짜, 교시)를 
추출하거나 병합/분할 파이프라인을 수행할 때, 정규식 기반의 문자열 조작 로직을 직접 구현하지 않고 
이 서비스를 의존성으로 주입받아 사용하도록 설계되었습니다.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from utils.filename_util import normalize_text
from base.base_service import BaseService

class FileNamingService(BaseService):
    """의학 강의 자료의 파일명 명명 규칙(도메인 지식)을 전담하여 파싱하고 생성하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 파일 시스템 I/O나 API 호출은 수행하지 않으며, 
    오로지 파일 이름(문자열)에 담긴 도메인 지식(날짜, 교시, 확장자 등)을 추출하고 
    변형(병합, 분할 네이밍 생성)하는 텍스트 처리 로직만 담당합니다[cite: 1]. 
    이 서비스는 `PipelineStatusService`, `DriveSyncService` 및 병합/분할 관련 Controller 들과 통신하며 
    파이프라인의 데이터 흐름을 제어하는 기준 식별자를 제공합니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """FileNamingService 객체를 초기화하고 성능 최적화를 위한 정규식 패턴을 사전 컴파일합니다.

        Args:            logger_callback (Optional[Callable[[str], None]], optional): 로그 메시지를 UI나 상위 레이어로 
                전달하기 위한 콜백 함수입니다. Defaults to None.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        super().__init__(logger_callback=logger_callback)
        
        # [최적화] 자주 사용하는 정규식 패턴을 인스턴스 생성 시 한 번만 컴파일(번역)하여 저장해 둡니다.
        # 드라이브 동기화 워커가 파일 수백 개를 파싱할 때 매번 정규식 엔진을 번역하는 과정이 생략되어 
        # CPU 오버헤드가 줄고 전체 파이프라인 처리 속도가 비약적으로 상승합니다.
        self._meta_pattern = re.compile(r'^(\d{4})_(\d+)(.*)$')
        self._save_name_pattern = re.compile(r'^(\d{4})_([\d,]+)교시')

    def _parse_filename_meta(self, filename: str) -> Dict[str, Any]:
        """내부 유틸: 파일명에서 [날짜(4자리), 교시, 접미사, 확장자]를 구조화된 데이터로 추출합니다.

        모든 네이밍 처리의 근간이 되는 코어 함수입니다. 
        이기종 OS 환경(macOS vs Windows)에서 발생하는 자소 분리 문제를 선제적으로 해결하기 위해 
        `normalize_text`를 가장 먼저 적용합니다. 그 후 사전 컴파일된 정규식을 통해 `MMDD_교시` 형태의 
        도메인 네이밍 룰에 따라 파일명을 분해합니다.

        Args:            filename (str): 파싱할 대상 원본 파일명.

        Returns:
            Dict[str, Any]: 추출된 메타데이터 딕셔너리.
                - 'date': MMDD 형식의 4자리 문자열 (매칭 실패 시 None)
                - 'periods': 각 교시 숫자를 분리한 리스트 (예: "12" -> ['1', '2'])
                - 'periods_str': 교시를 나타내는 원본 문자열 (예: "12")
                - 'rest': 교시 이후에 붙는 부가 설명 문자열
                - 'ext': 파일 확장자 문자열 (기본값 '.pdf')
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        norm_name = normalize_text(filename)
        path = Path(norm_name)
        stem, ext = path.stem, path.suffix

        # 미리 만들어둔 컴파일 패턴을 사용해 빠른 검색만 수행합니다.
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
        """파일명에서 '날짜_교시' 형태의 파이프라인 전역 식별자(Lesson ID)를 추출합니다.

        DriveSyncService나 Controller가 이 식별자를 통해 여러 흩어져 있는 관련 파일 
        (예: 필기본, 음성본, JSON 결과)들을 하나의 수업 교시 그룹으로 묶어 상태를 추적하게 해주는 핵심 키입니다.

        Args:            filename (str): 분석할 대상 파일명.

        Returns:
            Optional[str]: 'MMDD_교시' 형태의 식별자 문자열(예: '1004_1'). 파싱 실패 시 None 반환.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        meta = self._parse_filename_meta(filename)
        if meta['date'] and meta['periods_str']:
            return f"{meta['date']}_{meta['periods_str']}"
        return None

    def find_file_by_lesson(self, file_list: List[str], target_lesson_id: str, keyword: Optional[str] = None) -> Optional[str]:
        """특정 교시 식별자(Lesson ID)와 추가 키워드를 모두 포함하는 파일 1개를 탐색하여 반환합니다.

        파이프라인 진행 중, 특정 교시에 해당하는 '원본 필기'나 '음성 파일'을 매칭하여 
        다음 단계(예: Whisper 또는 Gemini 처리)로 넘기기 위해 파일 리스트에서 타겟을 핀셋 탐색할 때 사용됩니다.

        Args:            file_list (List[str]): 검색 대상이 되는 전체 파일명 리스트.
            target_lesson_id (str): 찾고자 하는 교시 식별자.
            keyword (Optional[str], optional): 파일명에 추가로 포함되어야 하는 키워드(예: 'script'). Defaults to None.

        Returns:
            Optional[str]: 조건을 모두 만족하는 첫 번째 파일명. 찾지 못하면 None.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        target_lesson_id = normalize_text(target_lesson_id)
        search_keyword = normalize_text(keyword) if keyword else ""
        
        for filename in file_list:
            if self.extract_lesson_id(filename) == target_lesson_id:
                norm_name = normalize_text(filename)
                if not search_keyword or search_keyword in norm_name:
                    return filename
        return None

    def filter_files_by_date_range(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        file_list: List[Any], 
        start_mmdd: str, 
        end_mmdd: str
    ) -> List[Any]:
        """파일 목록에서 지정된 날짜(MMDD) 범위에 해당하는 파일만 필터링하여 반환합니다.        메인 UI에서 사용자가 '특정 기간'의 학습 자료만 동기화하거나 보기 원할 때 호출됩니다. 
        입력값이 로컬에서 수집된 단순 문자열 리스트인지, 드라이브 API 통신으로 가져온 
        딕셔너리 메타데이터 리스트인지 구분하지 않고 다형성(Polymorphism)을 지원하여 
        호출부의 데이터 가공 부담을 줄였습니다.

        Args:
            file_list (List[Any]): 문자열 또는 드라이브 API 파일 객체(딕셔너리)가 담긴 리스트.
            start_mmdd (str): 필터링 시작 기준 날짜 (예: "1001").
            end_mmdd (str): 필터링 종료 기준 날짜 (예: "1031").

        Returns:
            List[Any]: 날짜 조건을 만족하는 파일 데이터들만 남긴 필터링된 리스트.
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
        """여러 파일명을 분석하여 병합 파이프라인의 결과물이 될 논리적인 새 파일명을 생성합니다.

        사용자가 여러 개의 분할된 교시 PDF(예: 1교시와 2교시)를 병합할 때, 
        '1004_1.pdf'와 '1004_2.pdf'의 메타데이터를 취합해 '1004_12.pdf'와 같은 형식으로 
        자동 명명해주는 스마트 유틸리티입니다. 
        내부적으로 집합(Set) 연산을 사용해 중복 교시 번호를 제거하고 오름차순으로 정렬하여 
        항상 일관된 네이밍 컨벤션을 유지합니다.

        Args:            filenames (List[str]): 병합 대상이 되는 원본 파일명들의 리스트.

        Returns:
            str: 규칙에 맞게 생성된 새로운 합본 파일명. 리스트가 비어있거나 규칙을 
                 분석할 수 없는 경우 기본값("merged_output...")을 반환합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """하나의 파일명을 두 개로 분할 파이프라인 처리 시 할당될 이름 리스트를 생성합니다.

        합쳐져 있던 교시 파일(예: '1004_12.pdf')을 사용자가 분할할 때, 
        이전 상태 메타데이터를 분석해 '1004_1.pdf'와 '1004_2.pdf'로 각각 나누어 질 수 있도록 
        논리적인 파일명 2개를 미리 계산하여 반환합니다.

        Args:            filename (str): 분할 대상이 되는 원본 합본 파일명.

        Returns:
            List[str]: 분할될 두 개의 새로운 파일명을 담은 리스트.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """UI에 표시되거나 드라이브에 저장될 최종 표시용(Display) 파일명을 추출합니다.

        정규식 컴파일 패턴(`_save_name_pattern`)을 사용하여 복잡한 원본 이름에서 불필요한 태그나 
        콤마(,)를 제거하고, 사용자 친화적으로 깔끔하게 정돈된 최종 저장용 이름을 도출합니다.

        Args:            base_name (str): 정리되지 않은 복잡한 형태의 원본 기본 이름.

        Returns:
            str: 불필요한 특수문자가 제거된 정돈된 PDF 파일명.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        norm_name = normalize_text(base_name)
        # 미리 만들어둔 컴파일 패턴을 사용해 빠른 검색만 수행합니다.
        match = self._save_name_pattern.search(norm_name)
        
        if match:
            clean_period = match.group(2).replace(',', '')
            return f"{match.group(1)}_{clean_period}.pdf"
        return f"{norm_name}_합본.pdf"

    def suggest_pdf_merge_name(self, file_names: List[str]) -> str:
        """선택된 여러 PDF 파일명을 분석해 UI 저장 텍스트 입력창에 추천할 텍스트를 반환합니다.

        사용자가 수동으로 여러 파일을 드래그 앤 드롭하여 병합하려 할 때 UI Controller에 의해 호출됩니다.
        `generate_merged_filename`과 유사하지만, 사용자가 직접 눈으로 보고 확인하는 
        입력 폼(Form)을 채워주는 용도이므로 스크립트 합본(`_scripted`) 여부 등을 추가로 평가하여 
        더 직관적이고 친절한 파일명을 제안(Suggest)합니다.

        Args:            file_names (List[str]): 병합을 위해 사용자가 선택한 원본 파일명 리스트.

        Returns:
            str: UI 입력창에 플레이스홀더(Placeholder)로 들어갈 추천 병합 파일명.
                 날짜가 다르거나 분석이 어려울 경우 기본값("merged_output.pdf" 등)을 반환합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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