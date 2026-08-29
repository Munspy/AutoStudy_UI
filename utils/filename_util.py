# utils/filename_util.py
import unicodedata

def normalize_text(text: str) -> str:
    """
    [순수 유틸리티]
    macOS(NFD)와 Windows(NFC) 간 자소 분리 불일치 해결을 위한 정규화.
    특정 도메인 규칙 없이 문자열 양끝의 공백을 제거하고 NFC로 통일합니다.
    """
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text).strip())