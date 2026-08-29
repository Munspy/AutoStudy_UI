# utils/config.py
import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Config:
    """
    애플리케이션 전역 설정 값 관리 및 검증 클래스
    """
    @staticmethod
    def extract_drive_id(id_or_url: str) -> str:
        if not id_or_url:
            return ""
        id_or_url = str(id_or_url).strip()
        match = re.search(r'/folders/([a-zA-Z0-9_-]+)', id_or_url)
        if match: return match.group(1)
        match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', id_or_url)
        if match: return match.group(1)
        match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', id_or_url)
        if match: return match.group(1)
        return id_or_url

    GOOGLE_API_SCOPES: List[str] = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/youtube.readonly'
    ]

    TARGET_DRIVE_DIR: str = extract_drive_id(os.getenv("TARGET_DRIVE_DIR", ""))
    PDF_RENDER_FONT_PATH: str = os.getenv(
        "PDF_RENDER_FONT_PATH", 
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    )

    GEMINI_KEYS: List[str] = [
        os.environ[k].strip() 
        for k in sorted(os.environ.keys()) 
        if k.startswith("GEMINI_KEY_") and os.environ[k].strip()
    ]

    NOTION_TOKEN: Optional[str] = os.getenv("NOTION_TOKEN")

    # [개선 1] SSOT(단일 진실 공급원): 모델 리스트 및 API 쿨타임을 전역 설정으로 이관
    API_COOLDOWN_SECONDS: float = 15.0
    GEMINI_MODELS: List[str] = [
        "gemini-2.5-flash", 
        "gemini-3.5-flash", 
        "gemini-3.6-flash", 
        "gemini-3.7-flash"
    ]

    @classmethod
    def validate(cls) -> None:
        if not cls.TARGET_DRIVE_DIR:
            raise ValueError("❌ .env 설정 오류: 'TARGET_DRIVE_DIR'가 설정되지 않았습니다.")
        if not cls.GEMINI_KEYS:
            raise ValueError("❌ .env 설정 오류: 최소 하나 이상의 'GEMINI_KEY'가 필요합니다.")
        if not cls.NOTION_TOKEN:
            print("⚠️ 경고: 'NOTION_TOKEN'이 설정되지 않았습니다. Notion 동기화 기능이 제한될 수 있습니다.")