import io
from pathlib import Path
from typing import List, Union, Optional, Set, Callable
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
import pymupdf
import imagehash
from PIL import Image

from utils.config import Config
from base.base_service import BaseService

# 경로 표준 입력을 위한 타입 정의
PathLike = Union[str, Path]

class PdfOcrService(BaseService):
    """
    PDF에서 텍스트 추출, 폰트 감지, 시각적 해시 비교 및 OCR 전사를 담당하는 
    이미지/텍스트 분석 전문 도메인 서비스 클래스입니다.
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None, default_ignore_fonts: Optional[List[str]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        # [최적화] 매번 리스트 컴프리헨션을 돌리지 않도록 Set 자료구조로 캐싱하여 O(1) 탐색 속도 확보
        self._cached_ignore_fonts: Set[str] = set(f.lower() for f in (default_ignore_fonts or []))

    # ==========================================
    # 1. 텍스트 추출 및 폰트 감지 (범용 도구)
    # ==========================================

    def get_filtered_text(self, page: pymupdf.Page, ignore_fonts: Optional[List[str]] = None) -> str:
        """
        PDF 페이지에서 텍스트를 추출하되, 지정된 폰트(예: 각주, 워터마크 폰트 등)가 사용된 텍스트는 제외합니다.
        """
        if not page:
            return ""

        # 동적으로 들어온 ignore_fonts와 기존 캐싱된 Set 병합
        dynamic_ignore = set(f.lower() for f in (ignore_fonts or []))
        target_ignore_fonts = self._cached_ignore_fonts | dynamic_ignore
        
        text_dict = page.get_text("dict")
        clean_text_pieces = []

        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:  # 0: 텍스트 블록
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_name = span.get("font", "").lower()
                        # Set을 이용한 O(1) 탐색 최적화
                        if not any(ignore_f in font_name for ignore_f in target_ignore_fonts):
                            text = span.get("text", "").strip()
                            if text:
                                clean_text_pieces.append(text)

        return " ".join(clean_text_pieces)

    def check_font_presence(self, page: pymupdf.Page, font_keyword: str) -> bool:
        """
        PDF 페이지 내에 특정 키워드가 포함된 폰트가 쓰였는지 감지합니다.
        """
        if not page or not font_keyword:
            return False

        target_kw = font_keyword.lower()
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if target_kw in span.get("font", "").lower():
                            return True
        return False

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        두 텍스트 간의 유효 유사도 비율(0.0 ~ 1.0)을 계산합니다.
        """
        t1 = (text1 or "").strip()
        t2 = (text2 or "").strip()

        if not t1 and not t2:
            return 1.0
        if not t1 or not t2:
            return 0.0

        return SequenceMatcher(None, t1, t2).ratio()

    # ==========================================
    # 2. 시각적 이미지 분석 도구
    # ==========================================

    def compare_page_hashes(self, page1: pymupdf.Page, page2: pymupdf.Page, zoom: float = 0.5, hash_size: int = 8) -> int:
        """
        두 PDF 페이지의 시각적 레이아웃/실루엣(Average Hash) 차이값을 계산합니다.
        """
        try:
            mat = pymupdf.Matrix(zoom, zoom)
            pix1 = page1.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
            pix2 = page2.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)

            with Image.open(io.BytesIO(pix1.tobytes("png"))) as img1, \
                 Image.open(io.BytesIO(pix2.tobytes("png"))) as img2:
                hash1 = imagehash.average_hash(img1, hash_size=hash_size)
                hash2 = imagehash.average_hash(img2, hash_size=hash_size)

            return hash1 - hash2
            
        except Exception as e:
            self._log(f"⚠️ 이미지 해시 비교 중 오류 발생: {str(e)}")
            return 999  # 오류 발생 시 시각적으로 완전히 다름으로 간주

    # ==========================================
    # 3. 고정밀 OCR 전사 도구
    # ==========================================

    def extract_text_with_ocr(self, file_path: PathLike, tesseract_cmd: Optional[str] = None, min_text_len: int = 10) -> Optional[str]:
        """
        텍스트 데이터가 포함되어 있지 않은 이미지/스캔본 PDF를 대상으로 Tesseract OCR을 수행합니다.
        """
        file_p = Path(file_path)
        if not file_p.exists():
            self._log(f"⚠️ OCR 대상 파일을 찾을 수 없습니다: {file_p.name}")
            return None

        cmd = tesseract_cmd or getattr(Config, 'TESSERACT_CMD', None)
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

        try:
            full_text_list = []
            custom_config = r'--oem 1 --psm 3'

            with pymupdf.open(str(file_p)) as doc:
                for i, page in enumerate(doc):
                    text = page.get_text().strip()

                    if len(text) < min_text_len:
                        pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
                        gray_img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
                        _, binary_img = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        text = pytesseract.image_to_string(binary_img, lang='kor+eng', config=custom_config)

                    full_text_list.append(f"--- {i + 1} Page ---\n{text.strip()}")

            return "\n\n".join(full_text_list)

        except pytesseract.TesseractNotFoundError:
            self._log("❌ Tesseract OCR 엔진을 찾을 수 없습니다. 시스템 PATH 환경 변수 또는 TESSERACT_CMD 설정을 확인하세요.")
            return None
        except Exception as e:
            self._log(f"⚠️ OCR 분석 중 오류 발생 ({file_p.name}): {str(e)}")
            return None