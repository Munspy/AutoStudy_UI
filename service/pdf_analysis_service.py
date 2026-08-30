"""PDF 내용 기반 매칭 및 병합 분석 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
단순한 물리적 파일 병합을 넘어, OCR 텍스트 분석과 시각적 해시(Image Hash) 비교 알고리즘을 활용하여 
'줄필기(학생 개인 필기)' PDF와 '야붙(족보/기출)' PDF의 페이지를 논리적으로 1:1 매칭해주는 핵심 비즈니스 로직을 제공합니다.

비동기 자동화 파이프라인에서 수많은 학습 자료가 쏟아져 들어올 때, 
페이지 수가 서로 다르거나 중간에 불필요한 슬라이드가 끼어있는 이기종 PDF 문서들을 
인간의 개입을 최소화하며 지능적으로 병합하기 위해 설계되었습니다.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from contextlib import ExitStack

import pymupdf
from base.base_service import BaseService

# 순수 유틸리티 호출 (도메인 무관)
from service.pdf_ocr_service import PdfOcrService
from service.file_naming_service import FileNamingService
from utils.filename_util import normalize_text


class PdfAnalysisService(BaseService):
    """의학 강의 자료 PDF의 페이지 간 유사도를 분석하고 병합 레시피를 생성하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 파일의 물리적 저장 경로 관리나 UI 렌더링에 관여하지 않으며, 
    오로지 두 PDF 문서 간의 페이지 맵핑(Mapping) 알고리즘과 병합 규칙(Domain Logic)을 
    평가하고 조립하는 책임만 가집니다.

    의존성:
    - 텍스트 추출 및 유사도 계산, 이미지 해싱 처리를 위해 `PdfOcrService`에 강하게 의존합니다.
    - 파일명의 도메인 규칙 파싱을 위해 `FileNamingService`와 통신합니다.
    - 결과물은 Controller로 반환되어 UI의 수동 검수 테이블에 바인딩됩니다.
    """
    
    def __init__(self, sim_threshold: float = 0.8, hash_threshold: int = 12, lookahead: int = 5, logger_callback=None):
        """매칭 알고리즘 튜닝 파라미터 및 의존성 서비스를 초기화합니다.

        Args:
            sim_threshold (float, optional): 두 페이지가 동일하다고 판정할 텍스트 일치율 임계값 (0.0 ~ 1.0). 기본값은 0.8(80%).
            hash_threshold (int, optional): OCR이 실패했을 때 대체제로 사용하는 시각적 해시(pHash)의 최대 허용 차이(Hamming Distance). 값이 작을수록 엄격합니다. 기본값은 12.
            lookahead (int, optional): 현재 페이지가 불일치할 때, 매칭되는 페이지를 찾기 위해 앞/뒤로 탐색할 최대 페이지 수 (Look-ahead Window). 슬라이드 삽입/누락으로 인한 오프셋(Offset)을 교정합니다. 기본값은 5.
            logger_callback (callable, optional): 로그 메시지를 처리할 콜백 함수.
        """
        super().__init__(logger_callback=logger_callback)
        # 매칭 알고리즘 튜닝 파라미터
        self.sim_threshold = sim_threshold
        self.hash_threshold = hash_threshold
        self.lookahead = lookahead
        
        # 도메인 규칙: 비교 시 무시할 폰트 (필기 앱 등에서 추가된 특정 폰트 필터링)
        self.ignore_fonts = ["handwriting", "pen", "applesdgothicneo"]
        
        # 도메인 규칙: 줄필기 1페이지를 강제 인식하기 위한 식별자 폰트
        self.indicator_font = "apple"
        self.naming_service = FileNamingService()

        # OCR 서비스 인스턴스화
        self.ocr_service = PdfOcrService(logger_callback=self._log)
        
        # [최적화] 정규식 사전 컴파일 캐싱 (성능 향상)
        # 자동화 파이프라인에서 수백 개의 파일을 스캔할 때 매번 정규식 엔진을 번역하지 않도록 캐싱하여 CPU 부하를 줄입니다.
        self._jul_pattern = re.compile(r'[-_\s]*줄필기.*\.pdf$', re.IGNORECASE)
        self._yaboot_pattern = re.compile(r'[-_\s]*야붙.*\.pdf$', re.IGNORECASE)

    def get_matched_file_groups(self, folder_path: str | Path) -> Dict[str, Dict[str, Any]]:
        """지정된 폴더에서 '줄필기'와 '야붙' 태그가 붙은 PDF를 찾아, 같은 교시를 공유하는 파일끼리 그룹화합니다.

        비동기 Watchdog 스레드나 사용자가 업로드한 폴더 내에는 다양한 교시의 파일이 무작위로 섞여 있을 수 있습니다. 
        이 함수는 이기종 OS(Mac/Win) 환경에서 발생할 수 있는 유니코드 자소 분리(NFD/NFC) 문제를 선제적으로 
        정규화(Normalize)하여 매칭 실패를 방지하고, 정규식을 통해 파일명에서 교시 식별자(Base Name)를 추출하여 
        분석 대상이 되는 페어(Pair)를 안전하게 구축합니다.

        Args:
            folder_path (str | Path): PDF 파일들을 탐색할 로컬 디렉토리 경로.

        Returns:
            Dict[str, Dict[str, Any]]: Base Name(교시 식별자)을 Key로 가지고, 해당 교시의 줄필기 파일명, 야붙 파일명, 
                그리고 저장될 최종 표시명(save_name)을 Value 딕셔너리로 갖는 매핑 객체.
        """
        p = Path(folder_path)
        groups: Dict[str, Dict[str, Any]] = {}
        
        if not p.exists() or not p.is_dir(): 
            return groups

        for file_path in p.glob("*.pdf"):
            # macOS(NFD)와 Windows(NFC) 환경 간의 자소 분리 문제를 방지하기 위해 정규화 수행
            name_nfc = normalize_text(file_path.name)
            
            # 실제 파일 시스템 파일명도 NFC로 동기화하여 이후 읽기 실패(인코딩 불일치) 방지
            if file_path.name != name_nfc:
                try:
                    new_path = file_path.with_name(name_nfc)
                    os.rename(str(file_path), str(new_path))
                    file_path = new_path
                except Exception as e:
                    if self.logger:
                        self.logger(f"파일명 변경 실패: {e}")
            
            if "줄필기" in name_nfc:
                base_name = self._jul_pattern.sub('', name_nfc).strip()
                doc_type = "jul"
            elif "야붙" in name_nfc:
                base_name = self._yaboot_pattern.sub('', name_nfc).strip()
                doc_type = "yaboot"
            else: 
                continue 
                
            if base_name not in groups:
                groups[base_name] = {
                    "jul": None, 
                    "yaboot": None, 
                    "save_name": self.naming_service.extract_save_name(base_name)
                }
                
            groups[base_name][doc_type] = name_nfc 
            
        return groups

    def generate_matching_data(
        self, 
        folder_path: str | Path, 
        selected_keys: List[str], 
        matched_groups: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """선택된 파일 쌍(Pair)의 페이지별 텍스트 및 이미지를 분석하여 최종 병합 레시피(Recipe)를 생성합니다.

        이 메서드는 의학 강의 자료 자동화의 핵심 지능(Intelligence)입니다.
        줄필기와 야붙 PDF는 강의 슬라이드를 기반으로 하지만, 필기 공간 추가나 요약 페이지 삽입 등으로 인해 
        페이지 번호가 1:1로 일치하지 않는 경우가 매우 흔합니다. 

        이를 해결하기 위해 Two-Pointer 알고리즘을 기반으로 두 문서를 순회하며 다음 단계를 거칩니다:
        1. OCR 텍스트를 추출하고 불필요한 필기 앱 전용 폰트(`ignore_fonts`)를 배제하여 순수 슬라이드 텍스트 유사도를 비교합니다.
        2. 불일치 발생 시 슬라이딩 윈도우(`lookahead`) 기법을 통해 몇 페이지 앞/뒤에 동일한 슬라이드가 있는지 탐색하여 오프셋(Offset)을 교정합니다.
        3. 이미지가 많아 OCR 텍스트가 빈약한 슬라이드의 경우, Perceptual Hash(시각적 해시) 알고리즘을 통해 
           슬라이드의 레이아웃 실루엣을 비교하는 Fallback 로직을 수행합니다.
        
        대용량 분석 시 메모리 부족(OOM)이나 파일 핸들 누수가 발생하지 않도록 철저히 컨텍스트 매니저(`with`) 안에서 
        객체의 생명주기를 통제합니다.

        Args:
            folder_path (str | Path): 분석할 파일들이 위치한 루트 디렉토리.
            selected_keys (List[str]): `get_matched_file_groups`에서 반환된 그룹 중 실제로 분석을 실행할 그룹의 Key 목록.
            matched_groups (Dict[str, Dict[str, Any]]): 전체 파일 그룹 정보가 담긴 딕셔너리.

        Returns:
            List[Dict[str, Any]]: 어느 파일의 몇 페이지를 가져올지, 혹은 어떻게 병합할지 명시된 조립 레시피 리스트. 
                이 데이터는 Controller로 전달되어 UI 테이블의 행(Row)으로 렌더링됩니다.
        """
        base_data: List[Dict[str, Any]] = []
        folder_p = Path(folder_path)
        
        for key in selected_keys:
            if key not in matched_groups:
                continue
                
            group = matched_groups[key]
            jul_file = group.get("jul")
            yaboot_file = group.get("yaboot")
            save_name = group.get("save_name")
            
            if not jul_file or not yaboot_file:
                continue
                
            jul_path = folder_p / jul_file
            yaboot_path = folder_p / yaboot_file

            # [안전성] with 구문을 사용한 메모리 누수 방지
            try:
                with pymupdf.open(str(jul_path)) as jul_pdf, pymupdf.open(str(yaboot_path)) as yaboot_pdf:
                    total_jul = len(jul_pdf)
                    total_yaboot = len(yaboot_pdf)
                    i, j = 0, 0

                    def add_item(t_val: str, j_path: Optional[Path], j_page: Optional[int], y_path: Optional[Path], y_page: Optional[int], met: str):
                        base_data.append({
                            "type": t_val,
                            "save_name": save_name,
                            "jul": {"path": str(j_path), "page": j_page} if j_path else None,
                            "yaboot": {"path": str(y_path), "page": y_page} if y_path else None,
                            "metrics": met
                        })

                    # [도메인 규칙 1] 1페이지 고유 정책 (야붙 1p 무조건 삽입 + 줄필기 특정 폰트 감지)
                    if total_jul > 0 and total_yaboot > 0:
                        add_item("yaboot_only", None, None, yaboot_path, 0, f"{save_name}\n야붙 1p (무조건 삽입)")
                        if self.ocr_service.check_font_presence(jul_pdf[0], font_keyword=self.indicator_font):
                            add_item("jul_only", jul_path, 0, None, None, f"{save_name}\n줄필기 1p (애플폰트 감지)")
                        i += 1
                        j += 1

                    # [도메인 규칙 2] 텍스트 유사도 및 이미지 해시 비교 루프
                    while i < total_jul and j < total_yaboot:
                        text_jul = self.ocr_service.get_filtered_text(jul_pdf[i], self.ignore_fonts)
                        text_yaboot = self.ocr_service.get_filtered_text(yaboot_pdf[j], self.ignore_fonts)
                        sim = self.ocr_service.calculate_text_similarity(text_jul, text_yaboot)

                        if sim >= self.sim_threshold:
                            add_item("matched", jul_path, i, yaboot_path, j, f"{save_name}\n텍스트 일치율: {sim*100:.1f}%")
                            i += 1
                            j += 1
                            continue

                        match_found = False
                        for offset in range(1, self.lookahead + 1):
                            if j + offset < total_yaboot:
                                future_yaboot_text = self.ocr_service.get_filtered_text(yaboot_pdf[j + offset], self.ignore_fonts)
                                if self.ocr_service.calculate_text_similarity(text_jul, future_yaboot_text) >= self.sim_threshold:
                                    for k in range(j, j + offset):
                                        add_item("yaboot_only", None, None, yaboot_path, k, f"{save_name}\n야붙 {k+1}p (기출 추가)")
                                    j += offset
                                    match_found = True
                                    break
                            
                            if i + offset < total_jul:
                                future_jul_text = self.ocr_service.get_filtered_text(jul_pdf[i + offset], self.ignore_fonts)
                                if self.ocr_service.calculate_text_similarity(future_jul_text, text_yaboot) >= self.sim_threshold:
                                    for k in range(i, i + offset):
                                        add_item("jul_only", jul_path, k, None, None, f"{save_name}\n줄필기 {k+1}p (내용 유지)")
                                    i += offset
                                    match_found = True
                                    break

                        if not match_found:
                            hash_diff = self.ocr_service.compare_page_hashes(jul_pdf[i], yaboot_pdf[j])
                            if hash_diff <= self.hash_threshold:
                                add_item("matched", jul_path, i, yaboot_path, j, f"{save_name}\n실루엣 일치! (해시 차이: {hash_diff})")
                                i += 1
                                j += 1
                            else:
                                add_item("jul_only", jul_path, i, None, None, f"{save_name}\n줄필기 {i+1}p (완전 다름)")
                                add_item("yaboot_only", None, None, yaboot_path, j, f"{save_name}\n야붙 {j+1}p (완전 다름)")
                                i += 1
                                j += 1

                    # [도메인 규칙 3] 잔여 페이지 일괄 처리
                    while i < total_jul:
                        add_item("jul_only", jul_path, i, None, None, f"{save_name}\n줄필기 {i+1}p (잔여)")
                        i += 1
                    while j < total_yaboot:
                        add_item("yaboot_only", None, None, yaboot_path, j, f"{save_name}\n야붙 {j+1}p (잔여)")
                        j += 1
                        
            except Exception as e:
                self._log(f"PDF 처리 중 오류 발생 ({save_name}): {str(e)}")
                continue

        return base_data





    def execute_merge(self, base_data: List[Dict[str, Any]], output_folder: str | Path) -> List[str]:
        """확정된 레시피를 바탕으로 실제 물리적 PDF 병합을 수행하고 디스크에 저장합니다.

        분석 서비스의 종착점이자 가장 무거운 디스크 I/O 작업이 일어나는 메서드입니다. 
        `base_data` 레시피에 명시된 순서와 페이지 번호대로 여러 PDF 파일에서 단일 페이지들을 발췌하여 
        하나의 거대한 PDF로 조립합니다. 

        수십~수백 번 동일한 원본 파일을 열고 닫는 오버헤드를 막기 위해 파이썬의 `ExitStack`을 사용하여 
        동적으로 열린 파일 핸들(`opened_pdfs`)을 캐싱하고, 작업이 끝난 후 또는 예외 발생 시 안전하고 
        일괄적으로 메모리에서 해제(Close)합니다. 이는 장시간 실행되는 Worker 환경에서 
        OS의 "Too many open files" 에러를 원천 차단하는 매우 중요한 방어 메커니즘입니다.

        Args:
            base_data (List[Dict[str, Any]]): `save_edits` 등을 통해 정제 및 확정된 병합 레시피 데이터.
            output_folder (str | Path): 조립이 완료된 PDF 파일들을 저장할 대상 로컬 디렉토리.

        Returns:
            List[str]: 성공적으로 병합 및 저장 완료된 결과물들의 파일명(`save_name`) 리스트.

        Raises:
            Exception: 파일 시스템 쓰기 권한 부족 등 I/O 통신 중 치명적인 에러 발생 시 로그를 남기고 다음 파일로 넘어갑니다.
        """
        out_folder_p = Path(output_folder)
        out_folder_p.mkdir(parents=True, exist_ok=True)
            
        docs_to_merge: Dict[str, List[Dict[str, Any]]] = {}
        for item in base_data:
            s_name = item.get("save_name", "merged_output.pdf")
            if s_name not in docs_to_merge:
                docs_to_merge[s_name] = []
            docs_to_merge[s_name].append(item)
            
        for save_name, items in docs_to_merge.items():
            out_path = out_folder_p / save_name
            
            # [안전성] ExitStack을 활용하여 가변적인 개수의 PDF 파일을 열고 닫기 자동화
            try:
                with pymupdf.open() as out_pdf, ExitStack() as stack:
                    opened_pdfs: Dict[str, pymupdf.Document] = {}
                    
                    for item in items:
                        t_val = item["type"]
                        target = None
                        
                        if t_val in ["matched", "jul_only"]:
                            target = item.get("jul")
                        elif t_val == "yaboot_only":
                            target = item.get("yaboot")
                            
                        if target:
                            path = target["path"]
                            page_num = target["page"]
                            
                            if path not in opened_pdfs:
                                opened_pdfs[path] = stack.enter_context(pymupdf.open(path))
                                
                            src_pdf = opened_pdfs[path]
                            out_pdf.insert_pdf(src_pdf, from_page=page_num, to_page=page_num)
                            
                    # 병합 결과물의 용량 최적화 (가비지 컬렉트 및 압축 활성화)
                    out_pdf.save(str(out_path), garbage=4, deflate=True)
            except Exception as e:
                self._log(f"병합 저장 중 오류 발생 ({save_name}): {str(e)}")
                
        return list(docs_to_merge.keys())