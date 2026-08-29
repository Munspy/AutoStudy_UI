# utils/pdf_core_util.py
# 기본 PDF 사용 도구들

from pathlib import Path
from typing import List, Tuple, Union
from contextlib import ExitStack
import pymupdf

from utils.file_util import ensure_parent_dir

# 경로 표준 입력을 위한 타입 정의
PathLike = Union[str, Path]


# ==========================================
# 1. UI 렌더링 (바이트 형태로 위로 쏘고 UI에서 랜더링)
# ==========================================

def get_page_image_bytes(
    file_path: PathLike, 
    page_num: int, 
    zoom: float = 1.0,
    image_format: str = "png"
) -> bytes | None:
    """
    PDF 파일의 특정 페이지를 렌더링하여 순수 바이트(Bytes) 데이터로 반환합니다.
    UI 프레임워크(PyQt)에 종속되지 않습니다.
    """
    try:
        path_str = str(file_path)
        with pymupdf.open(path_str) as doc:
            if page_num < 0 or page_num >= len(doc):
                print(f"⚠️ 유효하지 않은 페이지 번호입니다 ({page_num}p / 전체 {len(doc)}p)")
                return None
                
            pdf_page = doc.load_page(page_num)
            zoom_matrix = pymupdf.Matrix(zoom, zoom)
            
            # alpha=False: 배경 투명도 제거
            pix = pdf_page.get_pixmap(matrix=zoom_matrix, alpha=False)
            
            # 순수 Bytes로 변환하여 반환
            return pix.tobytes(image_format)
            
    except FileNotFoundError:
        print(f"⚠️ PDF 렌더링 실패: 파일을 찾을 수 없습니다. ({file_path})")
        return None
    except pymupdf.FileDataError:
        print(f"⚠️ PDF 렌더링 실패: 파일이 손상되었거나 유효한 PDF가 아닙니다. ({file_path})")
        return None
    except Exception as e:
        print(f"⚠️ PDF 렌더링 중 알 수 없는 오류 발생 ({file_path} - {page_num}p): {e}")
        return None


# ==========================================
# 2. PDF 물리적 조작 (병합 및 분할)
# ==========================================

def merge_pdfs(pdf_paths: List[PathLike], output_path: PathLike) -> str:
    """
    여러 PDF 파일 경로를 순서대로 병합하여 새로운 하나의 PDF로 저장합니다.
    """
    if not pdf_paths:
        raise ValueError("❌ 병합할 PDF 파일 목록이 비어있습니다.")

    out_path = ensure_parent_dir(output_path)
    
    # with 구문을 통해 out_pdf 자동 해제 보장
    with pymupdf.open() as out_pdf:
        for path in pdf_paths:
            p_str = str(path)
            if not Path(p_str).exists():
                print(f"⚠️ 존재하지 않는 파일 스킵: {p_str}")
                continue
            try:
                with pymupdf.open(p_str) as doc:
                    out_pdf.insert_pdf(doc)
            except pymupdf.FileDataError:
                print(f"⚠️ 유효하지 않은 PDF 스킵: {p_str}")
                
        # garbage=4(미사용 객체 완전 정리), deflate=True(압축 저장)를 통한 용량 최적화
        out_pdf.save(str(out_path), garbage=4, deflate=True)
        return str(out_path)


def split_pdf_two_parts(
    file_path: PathLike, 
    split_page_num: int, 
    output_path_1: PathLike, 
    output_path_2: PathLike
) -> Tuple[str, str]:
    """
    하나의 PDF를 지정한 기준 페이지 번호를 경계로 2개의 파일로 분할합니다.
    """
    p_str = str(file_path)
    
    out_path1 = ensure_parent_dir(output_path_1)
    out_path2 = ensure_parent_dir(output_path_2)

    with pymupdf.open(p_str) as doc:
        total_pages = len(doc)
        if split_page_num <= 0 or split_page_num >= total_pages:
            raise ValueError(
                f"❌ 분할 기준 페이지({split_page_num})가 유효하지 않습니다. "
                f"(전체 페이지 수: {total_pages})"
            )
            
        # Part 1 추출 (0부터 split_page_num - 1까지)
        with pymupdf.open() as doc1:
            doc1.insert_pdf(doc, from_page=0, to_page=split_page_num - 1)
            doc1.save(str(out_path1), garbage=4, deflate=True)
        
        # Part 2 추출 (split_page_num부터 마지막 페이지까지)
        with pymupdf.open() as doc2:
            doc2.insert_pdf(doc, from_page=split_page_num, to_page=total_pages - 1)
            doc2.save(str(out_path2), garbage=4, deflate=True)

    return str(out_path1), str(out_path2)


# ==========================================
# 3. PDF 세부/임의 페이지 재조작
# ==========================================

def merge_specific_pages(
    page_recipe: List[Tuple[PathLike, int]], 
    output_path: PathLike
) -> str:
    """
    임의의 PDF 파일과 페이지 번호 조합(레시피)을 전달받아 단일 PDF로 맞춤 병합합니다.
    """
    if not page_recipe:
        raise ValueError("❌ 페이지 레시피 목록이 비어있습니다.")

    out_path = ensure_parent_dir(output_path)
    
    # ExitStack을 활용하여 가변적인 개수의 PDF 객체를 안전하게 자동 해제
    with pymupdf.open() as out_pdf, ExitStack() as stack:
        opened_pdfs = {}  # 동일 파일의 반복 오픈 I/O 오버헤드를 막기 위한 메모리 캐싱
        
        for path, page_num in page_recipe:
            p_str = str(path)
            if p_str not in opened_pdfs:
                if not Path(p_str).exists():
                    print(f"⚠️ 존재하지 않는 파일 스킵: {p_str}")
                    continue
                try:
                    # 여는 즉시 stack에 등록하여 에러 발생 시에도 무조건 close() 되도록 보장
                    opened_pdfs[p_str] = stack.enter_context(pymupdf.open(p_str))
                except pymupdf.FileDataError:
                    print(f"⚠️ 유효하지 않은 PDF 스킵: {p_str}")
                    continue
                
            src_pdf = opened_pdfs.get(p_str)
            if src_pdf and 0 <= page_num < len(src_pdf):
                out_pdf.insert_pdf(src_pdf, from_page=page_num, to_page=page_num)
            else:
                print(f"⚠️ 범위를 벗어난 페이지 스킵: {p_str} ({page_num}p)")

        # 최적화 압축 저장
        out_pdf.save(str(out_path), garbage=4, deflate=True)
        return str(out_path)
