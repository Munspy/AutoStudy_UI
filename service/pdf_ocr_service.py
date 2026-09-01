"""PDF 이미지/텍스트 분석 및 OCR 전사 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다[cite: 1].
PDF 파일에서 텍스트를 추출하고, 시각적 레이아웃(Image Hash)을 비교하며, 
스캔된 문서에 대해 Tesseract OCR을 수행하는 저수준(Low-level) 데이터 분석 책임을 갖습니다.

PdfAnalysisService(매칭/병합 로직)나 LlmService(텍스트 분석 로직) 등 상위 비즈니스 서비스들이 
PDF 내부의 파편화된 데이터(폰트, 좌표, 픽셀 등)를 직접 다루지 않도록, 
고도화된 정제 및 추출 인터페이스를 제공하는 기반 도메인 서비스 역할을 수행합니다.
"""

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
    """PDF에서 텍스트 추출, 폰트 감지, 시각적 해시 비교 및 OCR 전사를 담당하는 이미지/텍스트 분석 전문 도메인 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 파일 저장이나 전체 파이프라인의 상태 관리는 수행하지 않으며, 
    오직 `pymupdf`, `OpenCV`, `Tesseract`를 활용하여 PDF 단일 페이지 내의 텍스트와 픽셀 데이터를 
    추출 및 수치화(유사도, 해시값)하는 작업만을 전담합니다.

    의존성:
    - 전역 환경설정인 `utils.config.Config`를 참조하여 Tesseract 엔진 경로를 획득합니다.
    - 부모 클래스인 `BaseService`를 상속받아 공통 로깅 인터페이스를 사용합니다[cite: 1].
    """
    
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None, default_ignore_fonts: Optional[List[str]] = None) -> None:
        """PdfOcrService 객체를 초기화하고 폰트 필터링 캐시를 구성합니다.

        Args:            logger_callback (Optional[Callable[[str], None]], optional): 비동기 처리 중 발생하는 로그를 
                상위 레이어(Controller/UI)로 전달하기 위한 콜백 함수. Defaults to None.
            default_ignore_fonts (Optional[List[str]], optional): 텍스트 추출 시 전역적으로 무시할 
                폰트 이름 키워드 리스트 (예: 필기 앱 워터마크 폰트). Defaults to None.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        super().__init__(logger_callback=logger_callback)
        # [최적화] 매번 리스트 컴프리헨션을 돌리지 않도록 Set 자료구조로 캐싱하여 O(1) 탐색 속도 확보
        self._cached_ignore_fonts: Set[str] = set(f.lower() for f in (default_ignore_fonts or []))

    # ==========================================
    # 1. 텍스트 추출 및 폰트 감지 (범용 도구)
    # ==========================================

    def get_filtered_text(self, page: pymupdf.Page, ignore_fonts: Optional[List[str]] = None) -> str:
        """PDF 페이지에서 텍스트를 추출하되, 지정된 폰트가 쓰인 텍스트는 필터링하여 제외합니다.

        의학 강의 자료(PDF)에는 종종 학생이 태블릿(굿노트, 노타빌리티 등)으로 덧그린 필기나 
        출처 워터마크가 포함되어 있습니다. 이러한 필기 텍스트는 원본 슬라이드 텍스트와 폰트가 다르다는 점을 
        이용해, 순수 슬라이드 텍스트만 추출하도록 폰트 이름 기반의 블랙리스트 필터링을 수행합니다. 
        자동화된 페이지 매칭 알고리즘이 필기 내용의 차이 때문에 두 슬라이드를 '다르다'고 오판하는 것을 
        방지하는 핵심 전처리 로직입니다.

        Args:            page (pymupdf.Page): 텍스트를 추출할 대상 PDF 페이지 객체.
            ignore_fonts (Optional[List[str]], optional): 해당 페이지 추출 시 추가로 무시할 폰트 키워드 리스트. Defaults to None.

        Returns:
            str: 필터링 조건에 의해 제외된 텍스트를 뺀 순수 추출 텍스트 문자열.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """PDF 페이지 내에 특정 키워드가 포함된 폰트가 쓰였는지 감지합니다.

        PDF 구조(Dictionary)를 파싱하여 특정 폰트(예: "Apple", "Pen" 등)의 사용 여부를 불리언(Boolean)으로 반환합니다. 
        이는 PdfAnalysisService가 '학생이 필기한 첫 페이지'를 휴리스틱(Heuristic)하게 탐지하여, 
        병합 시 필기본 표지를 강제로 삽입하는 등의 도메인 비즈니스 규칙(Rule)을 트리거하는 데 사용됩니다.

        Args:            page (pymupdf.Page): 분석할 대상 PDF 페이지 객체.
            font_keyword (str): 감지하고자 하는 폰트 이름의 일부(소문자 기준).

        Returns:
            bool: 해당 폰트가 페이지 내 텍스트 스팬(Span)에 한 번이라도 사용되었으면 True, 아니면 False.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """두 텍스트 간의 유효 유사도 비율(0.0 ~ 1.0)을 계산합니다.

        Python 내장 `difflib.SequenceMatcher`를 사용하여 레벤슈타인 거리 기반의 형태적 텍스트 일치율을 산출합니다. 
        비동기 매칭 파이프라인에서 두 개의 슬라이드가 논리적으로 같은 페이지인지를 판별할 때 
        가장 1차적이고 빠른 판단 기준(Threshold)으로 작용합니다.

        Args:            text1 (str): 비교할 첫 번째 텍스트 문자열.
            text2 (str): 비교할 두 번째 텍스트 문자열.

        Returns:
            float: 0.0(완전 불일치)에서 1.0(완전 일치) 사이의 실수값. 입력값이 모두 비어있으면 1.0을 반환합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """두 PDF 페이지의 시각적 레이아웃/실루엣(Average Hash) 차이값을 계산합니다.

        그림이나 도표 위주로 구성되어 추출 가능한 텍스트가 극히 적은 슬라이드의 경우, 
        텍스트 유사도 비교 알고리즘이 무용지물이 됩니다. 이 메서드는 페이지 자체를 저해상도(zoom=0.5) 
        그레이스케일 이미지로 렌더링한 뒤, Average Hash 기법을 통해 이미지의 전체적인 레이아웃 실루엣을 
        비트 배열로 압축합니다. 이후 두 해시값의 해밍 거리(Hamming Distance)를 반환하여, 
        미세한 필기 자국이 추가되었더라도 전체적인 형태가 같으면 동일 페이지로 간주하는 
        매칭 알고리즘의 최후 방어선(Fallback) 역할을 합니다.

        Args:            page1 (pymupdf.Page): 비교할 첫 번째 PDF 페이지 객체.
            page2 (pymupdf.Page): 비교할 두 번째 PDF 페이지 객체.
            zoom (float, optional): 이미지를 렌더링할 배율. 작을수록 속도는 빠르나 정밀도가 떨어집니다. Defaults to 0.5.
            hash_size (int, optional): 생성할 해시 비트맵의 한 변의 길이(기본 8x8). Defaults to 8.

        Returns:
            int: 두 페이지의 시각적 해시 차이(해밍 거리). 0에 가까울수록 시각적으로 동일함을 의미합니다. 오류 발생 시 999를 반환.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """텍스트 데이터가 포함되어 있지 않은 이미지형/스캔본 PDF를 대상으로 Tesseract OCR을 수행합니다.

        일반적인 텍스트 추출이 불가능한 스캔 문서(통이미지 PDF)가 파이프라인에 인입될 경우, 
        이 메서드가 OpenCV를 활용한 이미지 전처리(이진화 및 오츠 임계값 적용)를 수행한 후 
        Tesseract OCR 엔진을 가동하여 문자를 강제로 전사(Transcription)해 냅니다. 
        추출된 데이터는 LLM 요약 서비스(Gemini)나 Anki 생성 로직의 입력(Context)으로 활용될 수 있도록 
        페이지 구분자와 함께 문자열로 반환됩니다.

        Args:            file_path (PathLike): OCR 전사를 수행할 원본 PDF 파일의 로컬 경로.
            tesseract_cmd (Optional[str], optional): 명시적으로 주입할 Tesseract 실행 파일 경로. 
                없을 경우 Config 환경 변수에서 로드합니다. Defaults to None.
            min_text_len (int, optional): 페이지 내에서 기본 추출된 텍스트가 이 길이보다 작을 경우에만 
                무거운 OCR 연산을 수행하도록 하는 임계값. Defaults to 10.

        Returns:
            Optional[str]: 페이지별 구분자(`--- X Page ---`)가 포함된 전체 추출 텍스트. 
                엔진을 찾지 못하거나 처리 중 오류가 발생하면 None을 반환합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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

                    # 기본 텍스트 추출 결과가 너무 짧으면 이미지 스캔본으로 간주하고 OCR 가동
                    if len(text) < min_text_len:
                        pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
                        gray_img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
                        
                        # 인식률을 극대화하기 위한 OpenCV 이진화 전처리
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