# utils/constants.py
"""
애플리케이션 전반에서 사용되는 매직 스트링, 설정값, 확장자 목록 등을 중앙에서 관리하는 파일입니다.
"""

# ==========================================
# 1. 파일 이름 및 접미사 식별자 (File Suffixes)
# ==========================================
class FileSuffix:
    YABOOT = "야붙필기"
    JUL = "줄필기"
    TRANSCRIPT_RAW = "음성스크립트"
    TRANSCRIPT_CORRECTED = "최종교정본"
    ANKI_PACKAGE = "통합본"
    SCRIPTED = "scripted"
    SUMMARY_TXT = "요약본"

# ==========================================
# 2. 지원되는 확장자 목록 (Extensions)
# ==========================================
class Extensions:
    AUDIO = ('.wav', '.m4a', '.mp3', '.mp4', '.aac', '.flac')
    PDF = ".pdf"
    TXT = ".txt"
    APKG = ".apkg"

# ==========================================
