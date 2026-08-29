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

class PdfAnalysisService(BaseService):
    """
    의학 강의 자료 중 '줄필기(학생 필기)'와 '야붙(족보/기출)' PDF의 페이지를 
    텍스트 유사도 및 시각적 해시 분석을 통해 논리적으로 매칭해주는 비즈니스 서비스입니다.
    """
    
    def __init__(self, sim_threshold: float = 0.8, hash_threshold: int = 12, lookahead: int = 5):
        super().__init__()
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
        self._jul_pattern = re.compile(r'_?줄필기\.pdf$')
        self._yaboot_pattern = re.compile(r'_?야붙\.pdf$')

    def get_matched_file_groups(self, folder_path: str | Path) -> Dict[str, Dict[str, Any]]:
        """
        [도메인 로직]
        지정된 폴더에서 '줄필기'와 '야붙' 태그가 붙은 PDF를 찾아, 같은 교시(Base Name)를 공유하는 파일끼리 그룹화합니다.
        """
        p = Path(folder_path)
        groups: Dict[str, Dict[str, Any]] = {}
        
        if not p.exists() or not p.is_dir(): 
            return groups

        for file_path in p.glob("*.pdf"):
            # macOS(NFD)와 Windows(NFC) 환경 간의 자소 분리 문제를 방지하기 위해 정규화 수행
            name_nfc = unicodedata.normalize('NFC', file_path.name)
            
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
                
            groups[base_name][doc_type] = file_path.name 
            
        return groups

    def generate_matching_data(
        self, 
        folder_path: str | Path, 
        selected_keys: List[str], 
        matched_groups: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        [도메인 로직]
        선택된 파일 쌍(줄필기/야붙)을 순회하며 페이지별 텍스트/이미지를 분석하여 병합 레시피를 생성합니다.
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

    def prepare_edit_data(self, base_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """UI 수동 검수용 데이터 상태 매핑"""
        edit_data: List[Dict[str, Any]] = []
        for item in base_data:
            new_item = item.copy()
            if item["type"] == "matched":
                new_item["jul_checked"] = True
                new_item["yaboot_checked"] = False
            elif item["type"] == "jul_only":
                new_item["jul_checked"] = True
                new_item["yaboot_checked"] = False
            elif item["type"] == "yaboot_only":
                new_item["jul_checked"] = False
                new_item["yaboot_checked"] = True
            edit_data.append(new_item)
        return edit_data

    def save_edits(self, edit_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """변경 상태 최종 확정"""
        new_base: List[Dict[str, Any]] = []
        for item in edit_data:
            if item["type"] == "matched" and item.get("jul_checked"):
                new_base.append(item)
            elif item["type"] == "jul_only" and item.get("jul_checked"):
                new_base.append(item)
            elif item["type"] == "yaboot_only" and item.get("yaboot_checked"):
                new_base.append(item)
        return new_base

    def split_item_on_yaboot_check(self, item: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """체크 상태 변경에 따른 단일 항목 분할"""
        item_jul = {
            "type": "jul_only",
            "save_name": item["save_name"],
            "jul": item["jul"], "yaboot": None,
            "jul_checked": item.get("jul_checked", False), "yaboot_checked": False,
            "metrics": "[분할됨]\n줄필기 단독"
        }
        item_yaboot = {
            "type": "yaboot_only",
            "save_name": item["save_name"],
            "jul": None, "yaboot": item["yaboot"],
            "jul_checked": False, "yaboot_checked": True,
            "metrics": "[분할됨]\n야붙 단독"
        }
        return item_jul, item_yaboot

    def swap_items(self, edit_data: List[Dict[str, Any]], idx: int, direction: int) -> List[Dict[str, Any]]:
        """배열 순서 변경"""
        target_idx = idx + direction
        if 0 <= target_idx < len(edit_data):
            edit_data[idx], edit_data[target_idx] = edit_data[target_idx], edit_data[idx]
        return edit_data

    def execute_merge(self, base_data: List[Dict[str, Any]], output_folder: str | Path) -> List[str]:
        """[도메인 로직] 최종 PDF 병합 및 디스크 저장"""
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
                            
                    out_pdf.save(str(out_path), garbage=4, deflate=True)
            except Exception as e:
                self._log(f"병합 저장 중 오류 발생 ({save_name}): {str(e)}")
                
        return list(docs_to_merge.keys())