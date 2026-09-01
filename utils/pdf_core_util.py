"""PDF 코어 유틸리티 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Utils(유틸리티) 계층**에 속합니다.
PDF 파일의 물리적 조작(병합, 분할, 재조합) 및 UI 렌더링을 위한 이미지 변환 기능을 제공합니다.

전체 애플리케이션 파이프라인에서 파일 I/O 및 `pymupdf` 라이브러리와 직접 맞닿아 있는 로우레벨(low-level) 
코어 계층을 담당합니다. 상위 UI 레이어나 비즈니스 로직(Service 계층)에서 PDF 내부의 복잡한 구조를 
알 필요 없이 손쉽게 파일을 다룰 수 있도록 추상화된 인터페이스를 제공합니다. 

특히, 장시간 실행되는 비동기 Worker(예: 대용량 PDF 분할 후 Whisper/Gemini 처리) 환경에서 
메모리 누수를 방지하기 위한 컨텍스트 매니저 기반의 자원 반환 로직과, 
병합/분할 시 발생할 수 있는 객체 파편화 및 파일 용량 팽창을 막기 위한 최적화 로직이 일관되게 적용되어 있습니다.
"""

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
    """PDF 파일의 특정 페이지를 렌더링하여 순수 바이트(Bytes) 데이터로 변환하여 반환합니다.
    
    이 함수는 상위 UI 프레임워크(예: PyQt, Tkinter 등)와 코어 로직 간의 강결합을 방지하기 위해 설계되었습니다.
    PDF 페이지를 특정 UI 객체로 변환하지 않고 언어 및 프레임워크 독립적인 순수 바이트 배열로 반환함으로써,
    호출하는 측(Controller나 UI)에서 자유롭게 바이트 데이터를 활용해 이미지를 렌더링할 수 있습니다. 
    비동기 워커가 백그라운드에서 썸네일을 생성할 때도 UI 스레드를 차단하지 않고 안전하게 동작할 수 있게 해줍니다.

    내부적으로 `pymupdf.Matrix`를 사용해 해상도(zoom)를 조절하며, `alpha=False`를 통해 배경 투명도를 
    제거하여 UI에 렌더링될 때 검은색 배경이 나타나는 문제를 방지합니다.

    Args:
        file_path (PathLike): 렌더링할 대상 PDF 파일의 절대 또는 상대 경로입니다.
        page_num (int): 추출하고자 하는 페이지 번호입니다. 0부터 시작하는 인덱스(0-based index)를 사용합니다.
        zoom (float, optional): 렌더링 해상도 배율입니다. 값이 커질수록 고해상도 이미지가 생성됩니다. Defaults to 1.0.
        image_format (str, optional): 출력할 이미지의 포맷을 지정합니다 (예: "png", "jpeg"). Defaults to "png".

    Returns:
        bytes | None: 성공적으로 렌더링된 이미지의 순수 바이트 데이터입니다.
            페이지 번호가 범위를 벗어나거나, 파일을 찾을 수 없거나, 손상된 경우 시스템 중단 대신 None을 반환합니다.
    """
    try:
        path_str = str(file_path)
        # PDF 문서를 안전하게 열기 (자동으로 닫힘)
        with pymupdf.open(path_str) as doc:
            # 유효하지 않은 페이지 번호 체크
            if page_num < 0 or page_num >= len(doc):
                print(f"⚠️ 유효하지 않은 페이지 번호입니다 ({page_num}p / 전체 {len(doc)}p)")
                return None
                
            # 지정된 페이지 로드
            pdf_page = doc.load_page(page_num)
            
            # 확대/축소 배율 매트릭스 설정
            zoom_matrix = pymupdf.Matrix(zoom, zoom)
            
            # alpha=False: 배경 투명도 제거하여 픽스맵(Pixmap) 생성
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
    """여러 PDF 파일 경로를 순서대로 병합하여 새로운 하나의 단일 PDF 파일로 저장합니다.
    
    학습 자료 자동화 파이프라인에서, 여러 개의 쪼개진 문서나 파트별로 처리 완료된 분석 결과를 
    다시 하나로 취합할 때 사용되는 핵심 병합 로직입니다. 

    단순히 파일을 이어붙이는 것에 그치지 않고, `pymupdf.open()`을 컨텍스트 매니저(`with`)로 감싸 
    워커(Worker) 스레드의 장기 실행 중 발생할 수 있는 메모리/파일 핸들 누수를 원천 차단합니다.
    특히 PDF 병합 시 빈번하게 발생하는 내부 객체 파편화 및 파일 용량 팽창 문제를 해결하기 위해,
    최종 저장 시 `garbage=4`(미사용 객체 및 중복 데이터 완전 정리)와 `deflate=True`(스트림 압축) 옵션을 강제합니다.
    중간에 존재하지 않거나 손상된 파일이 포함되어 있더라도 오류를 발생시키지 않고 해당 파일만 스킵하여 
    전체 자동화 배치의 안정성을 높였습니다.

    Args:
        pdf_paths (List[PathLike]): 병합할 대상 PDF 파일 경로들의 리스트입니다. 리스트의 순서대로 페이지가 병합됩니다.
        output_path (PathLike): 병합이 완료된 결과물 PDF를 저장할 최종 경로입니다. 부모 폴더가 없다면 자동 생성됩니다.

    Returns:
        str: 정상적으로 병합 및 압축되어 저장된 최종 결과물 파일의 절대/상대 경로 문자열입니다.

    Raises:
        ValueError: `pdf_paths` 리스트가 비어 있어 병합을 수행할 파일이 전혀 없는 경우 발생합니다.
    """
    if not pdf_paths:
        raise ValueError("❌ 병합할 PDF 파일 목록이 비어있습니다.")

    # 출력 경로의 부모 디렉토리가 없으면 생성
    out_path = ensure_parent_dir(output_path)
    
    # with 구문을 통해 out_pdf 자동 해제 보장
    with pymupdf.open() as out_pdf:
        for path in pdf_paths:
            p_str = str(path)
            
            # 대상 파일 존재 여부 확인
            if not Path(p_str).exists():
                print(f"⚠️ 존재하지 않는 파일 스킵: {p_str}")
                continue
                
            try:
                # 개별 PDF를 열어 출력 PDF에 병합 삽입
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
    """하나의 원본 PDF를 지정한 기준 페이지 번호를 경계로 2개의 파일로 깔끔하게 분할합니다.
    
    대용량 문서나 챕터별 구분이 필요한 문서를 두 동강 내기 위한 목적으로 사용됩니다.
    Gemini LLM의 토큰 제한이나 Whisper STT의 용량 제한을 우회하기 위해 Service 계층이 
    이 함수를 호출하여 문서를 사전에 청크(chunk) 단위로 나누는 파이프라인에서 핵심적으로 동작합니다.

    `split_page_num`을 경계로 이전 페이지들은 첫 번째 파트로, 해당 페이지를 포함한 이후 페이지들은 
    두 번째 파트로 분할됩니다. 문서를 나눌 때 불필요한 메타데이터 손실을 막기 위해 `insert_pdf`를 활용하여 
    페이지 범위를 복제하는 방식을 채택하였으며, 저장 시에는 병합 로직과 동일하게 최적화(`garbage=4`) 
    및 압축(`deflate=True`) 옵션을 적용하여 디스크 용량 효율성을 확보합니다.

    Args:
        file_path (PathLike): 분할할 대상 원본 PDF 파일의 경로입니다.
        split_page_num (int): 분할의 기준이 되는 페이지 번호(0-based index)입니다. 
            이 번호에 해당하는 페이지는 두 번째 출력 파일의 첫 페이지가 됩니다.
        output_path_1 (PathLike): 첫 번째 분할 결과물(페이지 0 ~ split_page_num-1)이 저장될 경로입니다.
        output_path_2 (PathLike): 두 번째 분할 결과물(페이지 split_page_num ~ 끝)이 저장될 경로입니다.

    Returns:
        Tuple[str, str]: 성공적으로 분할되어 저장된 첫 번째 파일 경로와 두 번째 파일 경로 문자열을 튜플로 반환합니다.

    Raises:
        ValueError: 기준 페이지(`split_page_num`)가 0 이하이거나 원본 문서의 전체 페이지 수보다 크거나 같아서 
            문서를 두 개로 분할할 수 없는 유효하지 않은 범위인 경우 발생합니다.
    """
    p_str = str(file_path)
    
    # 두 출력 파일의 부모 경로 미리 확인 및 생성
    out_path1 = ensure_parent_dir(output_path_1)
    out_path2 = ensure_parent_dir(output_path_2)

    with pymupdf.open(p_str) as doc:
        total_pages = len(doc)
        
        # 분할 경계 페이지의 유효성 검사
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
    """임의의 PDF 파일과 특정 페이지 번호 조합(레시피)을 전달받아 단일 PDF로 맞춤 병합합니다.
    
    여러 문서에서 필요한 페이지들만 골라내어(예: A문서 3쪽, B문서 1쪽, A문서 5쪽) 새로운 학습 자료를 조립하는
    복잡한 재구성(re-ordering/extracting) 시나리오에 대응하는 핵심 로직입니다. 
    
    사용자(또는 자동화 파이프라인)가 동일한 파일을 여러 번 번갈아가며 반복적으로 발췌 요청할 수 있습니다. 
    이 때 매번 동일한 파일을 열고 닫기를 반복하면 심각한 디스크 I/O 오버헤드가 발생하여 성능이 저하됩니다. 
    이를 방지하고자 내부 딕셔너리(`opened_pdfs`)를 이용한 파일 핸들 캐싱(메모이제이션) 기법을 사용하여 한 번 열린 파일은 재사용합니다. 
    또한 가변적인 개수의 파일 핸들을 사용하더라도 예외 발생 시 안전하고 누수 없이 한꺼번에 닫아주기 위해 
    파이썬의 `contextlib.ExitStack`을 활용한 고도화된 동적 컨텍스트 관리를 수행합니다.

    Args:
        page_recipe (List[Tuple[PathLike, int]]): 발췌 및 병합할 페이지들의 순서와 출처 정보가 담긴 레시피 리스트입니다.
            각 요소는 `(소스 PDF 파일 경로, 추출할 페이지 번호(0-based))` 형태의 튜플로 구성됩니다.
        output_path (PathLike): 발췌된 페이지들이 하나로 조립되어 저장될 최종 PDF 파일의 경로입니다.

    Returns:
        str: 맞춤 병합 및 최적화(압축) 저장이 완료되어 생성된 최종 조립 PDF 파일의 경로 문자열입니다.

    Raises:
        ValueError: `page_recipe` 리스트가 비어 있어 병합할 페이지 정보가 하나도 입력되지 않은 경우 발생합니다.
    """
    if not page_recipe:
        raise ValueError("❌ 페이지 레시피 목록이 비어있습니다.")

    # 저장할 출력 경로 확보
    out_path = ensure_parent_dir(output_path)
    
    # ExitStack을 활용하여 가변적인 개수의 PDF 객체를 안전하게 자동 해제
    with pymupdf.open() as out_pdf, ExitStack() as stack:
        opened_pdfs = {}  # 동일 파일의 반복 오픈 I/O 오버헤드를 막기 위한 메모리 캐싱
        
        for path, page_num in page_recipe:
            p_str = str(path)
            
            # 캐시에 해당 문서가 없다면 새로 열기 시도
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
            # 페이지 번호가 유효한지 검사한 후 삽입
            if src_pdf and 0 <= page_num < len(src_pdf):
                out_pdf.insert_pdf(src_pdf, from_page=page_num, to_page=page_num)
            else:
                print(f"⚠️ 범위를 벗어난 페이지 스킵: {p_str} ({page_num}p)")

        # 최적화 압축 저장
        out_pdf.save(str(out_path), garbage=4, deflate=True)
        return str(out_path)