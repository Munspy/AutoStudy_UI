import re
from typing import Dict


def parse_slide_text(text: str) -> Dict[int, str]:
    """[Slide XX] 포맷의 스크립트 텍스트를 슬라이드 번호(int)를 키로 하는 딕셔너리로 파싱합니다.
    다양한 자릿수(01, 001 등)와 공백 차이를 유연하게 처리합니다.
    """
    text_dict: dict[int, str] = {}
    if not text:
        return text_dict
        
    pattern = r"\[Slide\s+0*(\d+)\]"
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    # 첫 번째 [Slide XX] 이전의 텍스트가 있다면 보존 (예: 메타데이터나 서론)
    preamble = parts[0].strip()
    if preamble:
        text_dict[0] = preamble
    
    # 정규식 split 결과는 [일반텍스트, 그룹1, 일반텍스트, 그룹2, ...] 형태로 나옵니다.
    for i in range(1, len(parts), 2):
        try:
            slide_num = int(parts[i])
            content = parts[i+1].strip()
            text_dict[slide_num] = content
        except ValueError:
            continue
            
    return text_dict

def assemble_slide_text(text_dict: Dict[int, str], total_pages: int) -> str:
    """슬라이드 번호 딕셔너리를 다시 [Slide 001] 형태의 전체 텍스트 문자열로 조립합니다."""
    lines = []
    
    # 서론(preamble)이 있다면 가장 앞에 추가
    if 0 in text_dict and text_dict[0].strip():
        lines.append(text_dict[0])
        lines.append("")
        
    for i in range(1, total_pages + 1):
        lines.append(f"[Slide {i:03d}]")
        content = text_dict.get(i, "(내용 없음)")
        if not content.strip():
            content = "(내용 없음)"
        lines.append(content)
        lines.append("") # 슬라이드 간 빈 줄 추가
    return "\n".join(lines).strip()
