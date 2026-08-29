import os
import io
import re
import html
from pathlib import Path
from typing import Union

import pymupdf
import markdown
from xhtml2pdf import pisa
from pylatexenc.latex2text import LatexNodes2Text

from utils.config import Config
from base.base_service import BaseService

PathLike = Union[str, Path]

class PdfRenderService(BaseService):
    """
    마크다운 텍스트를 파싱, 수식 정제, HTML 변환을 거쳐
    최종 의학 강의 노트 PDF 및 슬라이드 합본 PDF로 렌더링하는 통합 서비스입니다.
    """

    def __init__(self):
        super().__init__()
        self.default_font_path = getattr(
            Config, 
            "PDF_RENDER_FONT_PATH", 
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
        )
        
        # [최적화 3] 반복 호출되는 정규식 패턴 사전 컴파일 캐싱
        self._math_display_pattern = re.compile(r'\$\$(.*?)\$\$', flags=re.DOTALL)
        self._math_inline_pattern = re.compile(r'\$(.*?)\$', flags=re.DOTALL)
        self._list_spacing_pattern = re.compile(r'([^\n])\n(\s*[\*\-]\s)')

    # ==========================================
    # 1. 내부 전처리 및 렌더링 엔진
    # ==========================================

    def _sanitize_markdown(self, text: str) -> str:
        """
        LaTeX 수식 및 특수문자로 인한 xhtml2pdf 렌더링 엔진 오류를 방지하기 위해 텍스트를 정제합니다.
        """
        if not text:
            return ""

        def convert_math_block(match: re.Match) -> str:
            math_expr = match.group(1)
            math_expr = re.sub(r'\\(\s+)', r'\1', math_expr)
            
            try:
                converted = LatexNodes2Text(math_mode=True).latex_to_text(math_expr)
            except Exception:
                converted = (
                    math_expr.replace(r'\times', '×')
                    .replace(r'\cdot', '·')
                    .replace(r'\le', '≤')
                    .replace(r'\ge', '≥')
                    .replace(r'\neq', '≠')
                    .replace(r'\approx', '≈')
                    .replace(r'\pm', '±')
                    .replace(r'\infty', '∞')
                )
                converted = converted.replace('\\', '')
            return html.escape(converted)

        # 수식 블록 ($$, $) 텍스트 치환 (캐싱된 정규식 사용)
        text = self._math_display_pattern.sub(convert_math_block, text)
        text = self._math_inline_pattern.sub(convert_math_block, text)
        
        # xhtml2pdf 패닉 유발 특수 기호 및 아스키 다이어그램 기호 치환
        text = text.replace('──►', '-->').replace('►', '>').replace('▼', 'v')
        text = text.replace('┌', '+').replace('┐', '+').replace('└', '+').replace('┘', '+')
        text = text.replace('├', '+').replace('┤', '+').replace('┬', '+').replace('┴', '+')
        text = text.replace('│', '|').replace('─', '-')
        
        # [최적화 1] 마크다운 리스트 포맷 정규화로 글머리 기호 렌더링 오류 방지
        text = self._list_spacing_pattern.sub(r'\1\n\n\2', text)
        return text

    def _html_to_pdf_doc(self, html_content: str) -> pymupdf.Document:
        """CSS가 주입된 완성형 HTML 문자열을 메모리 상의 pymupdf.Document 객체로 변환합니다."""
        pdf_io = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_content), dest=pdf_io)
        return pymupdf.open("pdf", pdf_io.getvalue())

    def _get_css_template(self, margin: str = "40pt") -> str:
        """의학 노트 포맷에 맞춘 기본 CSS 레이아웃 스타일을 반환합니다."""
        return f"""
            @font-face {{ font-family: 'KoreanFont'; src: url('{self.default_font_path}'); }}
            body {{ 
                font-family: 'KoreanFont', sans-serif; font-size: 10pt; line-height: 1.6; 
                color: #1d1d1f; word-wrap: cjk; word-break: keep-all; 
            }}
            pre {{ 
                font-family: 'KoreanFont', monospace; font-size: 7.5pt; line-height: 1.2; 
                white-space: pre; background-color: #f4f5f7; padding: 10px; border: 1pt solid #ddd; 
            }}
            code {{ font-family: 'KoreanFont', monospace; }}
            h1 {{ font-size: 18pt; border-bottom: 1.5pt solid #333; padding-bottom: 5px; margin-bottom: 15px; }}
            h2 {{ font-size: 14pt; margin-top: 15px; margin-bottom: 10px; border-bottom: 0.5pt solid #ccc; }}
            p {{ margin-bottom: 8px; text-align: justify; }}
            
            /* [최적화 1] xhtml2pdf 리스트(글머리 기호) 씹힘 방지 속성 명시적 부여 */
            ul {{ margin-bottom: 10pt; margin-left: 20pt; list-style-type: disc; display: block; }}
            li {{ display: list-item; margin-bottom: 4pt; line-height: 1.5; }}
            
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            th, td {{ border: 0.5pt solid #999; padding: 8px; text-align: left; vertical-align: top; }}
            th {{ background-color: #f0f0f0; font-weight: bold; text-align: center; }}
            @page {{ size: a4 portrait; margin: {margin}; }}
        """

    # ==========================================
    # 2. 메인 렌더링 비즈니스 엔트리포인트
    # ==========================================

    def create_pdf_from_markdown(self, md_text: str, custom_css: str = None) -> pymupdf.Document:
        """마크다운 텍스트를 파싱하여 메모리 상의 PDF(pymupdf.Document) 객체로 반환합니다."""
        css_str = custom_css if custom_css else self._get_css_template()
        sanitized_text = self._sanitize_markdown(md_text)
        html_body = markdown.markdown(sanitized_text, extensions=['tables', 'sane_lists', 'fenced_code'])
        
        html_content = f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><style>{css_str}</style></head>
        <body>{html_body}</body></html>
        """
        return self._html_to_pdf_doc(html_content)

    def create_slide_script_pdf(self, orig_pdf_path: PathLike, slides_data_dict: dict, output_path: PathLike) -> str:
        """원본 PDF 슬라이드를 상단에, 교정된 스크립트 마크다운 텍스트를 하단에 배치한 PDF를 생성합니다."""
        a4_width, a4_height = 595.0, 842.0
        top_half_rect = pymupdf.Rect(0, 0, a4_width, a4_height / 2)
        custom_css = self._get_css_template(margin="430pt 40pt 40pt 40pt")
        out_path_str = str(output_path)
        
        # [최적화 2] 컨텍스트 매니저를 통해 대용량 원본 파일 및 출력 파일의 메모리 누수 100% 방지
        try:
            with pymupdf.open(str(orig_pdf_path)) as orig_doc, pymupdf.Document() as out_doc:
                for page_index in range(len(orig_doc)):
                    slide_num = page_index + 1
                    raw_text = slides_data_dict.get(slide_num, "").strip()

                    if not raw_text or raw_text == "(내용 없음)":
                        new_page = out_doc.new_page(width=a4_width, height=a4_height)
                        new_page.show_pdf_page(top_half_rect, orig_doc, page_index)
                        continue

                    # 생성되는 수십 개의 temp_doc 객체들도 with 구문으로 안전하게 해제
                    with self.create_pdf_from_markdown(raw_text, custom_css) as temp_doc:
                        for temp_page in temp_doc:
                            temp_page.show_pdf_page(top_half_rect, orig_doc, page_index)
                            
                        out_doc.insert_pdf(temp_doc)

                out_doc.save(out_path_str, garbage=4, deflate=True)
            return out_path_str
            
        except Exception as e:
            self._log(f"❌ 슬라이드/스크립트 합성 PDF 렌더링 중 오류 발생: {str(e)}")
            raise Exception(f"합성 PDF 렌더링 실패: {str(e)}")