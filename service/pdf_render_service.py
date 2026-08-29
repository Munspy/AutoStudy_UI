"""마크다운 기반 PDF 동적 렌더링 및 슬라이드 합성 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
LLM(Gemini)이 생성한 요약본(단권화 노트)이나 스크립트 데이터를 물리적인 PDF 파일로 
시각화(Rendering)하는 핵심 엔진(Engine) 역할을 수행합니다.

마크다운(Markdown) 문법, 의학 특수 기호, LaTeX 수식 등 비정형 텍스트 데이터를 
`markdown` 및 `xhtml2pdf` 라이브러리를 통해 구조화된 HTML/CSS 돔(DOM)으로 파싱하고, 
최종적으로 `pymupdf`를 사용해 파일에 기록(Write)합니다. 
특히 기존 강의록(Slide)과 교정된 텍스트를 위/아래로 결합(Merge)하여 새로운 복합 학습 자료를 
창출하는 비즈니스 도메인 로직이 포함되어 있습니다.
"""

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
    """마크다운 텍스트를 파싱, 수식 정제, HTML 변환을 거쳐 최종 PDF로 렌더링하는 통합 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 외부 파일 시스템 제어나 API 통신을 수행하지 않으며, 
    오직 문자열 데이터를 PDF 시각적 레이아웃으로 변환하는 '렌더러(Renderer)' 역할만 전담합니다. 
    LlmService나 PipelineStatusService에서 가공된 텍스트 데이터를 주입받아 동작합니다.
    """

    def __init__(self):
        """PdfRenderService 인스턴스를 초기화하고 전역 설정 및 정규식을 로드합니다."""
        super().__init__()
        self.default_font_path = getattr(
            Config, 
            "PDF_RENDER_FONT_PATH", 
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
        )
        
        # [최적화 3] 반복 호출되는 정규식 패턴 사전 컴파일 캐싱
        # 대용량 텍스트 파싱 시 매번 정규식을 번역하는 엔진 오버헤드를 막기 위해, 
        # 수학 수식 매칭($$ $$, $ $) 및 리스트 간격 보정 패턴을 인스턴스 생성 시 캐싱해 둡니다.
        self._math_display_pattern = re.compile(r'\$\$(.*?)\$\$', flags=re.DOTALL)
        self._math_inline_pattern = re.compile(r'\$(.*?)\$', flags=re.DOTALL)
        self._list_spacing_pattern = re.compile(r'([^\n])\n(\s*[\*\-]\s)')

    # ==========================================
    # 1. 내부 전처리 및 렌더링 엔진
    # ==========================================

    def _sanitize_markdown(self, text: str) -> str:
        """LaTeX 수식 및 특수문자로 인한 렌더링 엔진(xhtml2pdf) 패닉 오류를 방지하기 위해 텍스트를 정제합니다.

        Gemini 등 LLM은 의학 및 수치 데이터를 출력할 때 LaTeX 수식(예: `$ \infty $`, `\neq`)이나 
        아스키 아트 표(예: `┌─┐`)를 자주 사용합니다. 그러나 `xhtml2pdf` 렌더링 엔진은 이러한 문법을 
        이해하지 못하고 빈 사각형으로 렌더링하거나 파이프라인 전체를 크래시(Crash) 낼 수 있습니다.
        
        이 메서드는 정규표현식과 `LatexNodes2Text`를 활용해 마크다운 내의 수식을 일반 유니코드 텍스트(예: `∞`, `≠`)로 
        안전하게 치환(Fallback)하고, HTML 예약어 충돌을 막기 위해 `html.escape` 처리를 
        선행하는 핵심 방어 로직입니다.

        Args:
            text (str): 치환되지 않은 원본 마크다운 텍스트 문자열.

        Returns:
            str: 렌더링 엔진에 주입해도 안전하도록 모든 수식과 기호가 유니코드 및 이스케이프 처리된 문자열.
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
        """CSS가 주입된 완성형 HTML 문자열을 메모리 상의 `pymupdf.Document` 객체로 직접 변환합니다.

        물리적인 디스크를 거치지 않고 I/O 바이트 버퍼(`io.BytesIO()`)를 활용하여 RAM 상에서 
        문서를 즉시 컴파일(In-memory rendering)합니다. 이는 다수의 페이지를 렌더링해야 하는 
        자동화 파이프라인에서 디스크 접근 병목(Bottleneck)을 제거하여 속도를 비약적으로 높이는 방식입니다.

        Args:
            html_content (str): CSS 스타일링과 정제된 텍스트가 모두 포함된 완성된 HTML 문서 문자열.

        Returns:
            pymupdf.Document: 조작 및 파일 저장이 가능한 메모리 상의 PDF 객체.
        """
        pdf_io = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_content), dest=pdf_io)
        return pymupdf.open("pdf", pdf_io.getvalue())

    def _get_css_template(self, margin: str = "40pt") -> str:
        """의학 요약 노트 및 합성 PDF 포맷에 맞춘 기본 CSS 레이아웃 스타일 문자열을 반환합니다.

        단순한 텍스트 배치가 아닌, 표(Table) 테두리 두께 조절, 줄바꿈 간격, 폰트 임베딩 등 
        시각적 가독성(Readability)을 위한 스타일 시트입니다. 동적으로 `margin` 값을 주입받아 
        일반 A4 요약본 렌더링과, 상단에 슬라이드가 들어가는 합성 PDF 렌더링 모두에 유연하게 대응합니다.

        Args:
            margin (str, optional): CSS `@page` 영역에 적용될 페이지 여백 문자열 
                (예: "40pt" 또는 "430pt 40pt 40pt 40pt"). Defaults to "40pt".

        Returns:
            str: 렌더링될 문서의 Head 태그에 삽입될 `<style>` 내용.
        """
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
        """마크다운 텍스트를 파싱하여 메모리 상의 PDF(pymupdf.Document) 객체로 변환 반환합니다.

        상위 Service나 Worker가 단권화 노트를 최종 PDF로 배포할 때 호출되는 퍼블릭 API입니다. 
        내부적으로 텍스트 정제(`_sanitize_markdown`) -> 마크다운 to HTML 변환 -> CSS 주입 -> 
        메모리 버퍼 렌더링(`_html_to_pdf_doc`)을 순차적으로 파이프라이닝(Pipelining)합니다. 
        파일 시스템에 접근하지 않고 객체만 반환하므로 동시성 환경에서도 안전합니다.

        Args:
            md_text (str): 변환할 대상 마크다운 포맷의 텍스트.
            custom_css (str, optional): 기본 템플릿 대신 적용할 커스텀 CSS 문자열. Defaults to None.

        Returns:
            pymupdf.Document: 모든 데이터가 렌더링된 메모리 기반 PDF 객체 (사용 후 close 필수).
        """
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
        """원본 PDF 슬라이드를 상단에, LLM 교정 스크립트를 하단에 배치한 복합(Composite) 학습 PDF를 생성합니다.

        의학 학습 자료 자동화의 핵심 결과물 중 하나로, 학생들이 강의 화면(시각 자료)과 교수님의 구두 설명(스크립트 텍스트)을 
        한 페이지 안에서 직관적으로 대조하며 볼 수 있도록 문서를 새롭게 조립하는 고도화된 기능입니다.
        
        A4 세로(Portrait) 크기를 기준으로 상단 절반(`top_half_rect`)에는 `show_pdf_page`를 이용해 
        기존 원본 슬라이드 이미지를 덮어씌우고(Overlay), 하단에는 빈 공간에 맞게 마진(margin)을 준 텍스트 렌더링 
        결과물을 결합합니다. 대량의 메모리가 소비될 수 있으므로 모든 PDF 핸들에 대해 파이썬 컨텍스트 매니저(`with`)를 
        강제하여 예외가 터지더라도 OOM(Out of Memory)과 메모리 누수(Leak)를 완벽히 차단합니다.

        Args:
            orig_pdf_path (PathLike): 원본 강의록 슬라이드 PDF 파일의 위치.
            slides_data_dict (dict): 키(Key)가 페이지 번호(1-based)이고 값(Value)이 해당 슬라이드의 마크다운 텍스트인 데이터 딕셔너리.
            output_path (PathLike): 최종 완성된 슬라이드-스크립트 복합 PDF가 저장될 경로.

        Returns:
            str: 정상적으로 생성되어 저장된 결과물 PDF의 경로.

        Raises:
            Exception: 파일이 없거나 디스크 공간 부족, 렌더링 엔진 에러 등 예외 발생 시 로그 출력과 함께 상위로 전파됩니다.
        """
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