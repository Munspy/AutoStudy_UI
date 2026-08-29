"""
애플리케이션 환경 변수 로드 및 전역 설정 관리 모듈.

이 모듈은 `.env` 파일을 로드하여 애플리케이션 실행에 필요한 환경 변수를 셋업하고,
Google Drive, Gemini API, Notion API 등 다양한 외부 서비스 연동에 필요한 인증 정보와
전역 설정 값들을 중앙 집중식으로 관리(SSOT, Single Source of Truth)합니다. 
전체 데이터 파이프라인에서 구성 요소를 초기화할 때 필요한 주요 설정값과 상수들을 제공하며, 
애플리케이션 시작 시 검증 메서드를 통해 필수 환경 변수의 누락 여부를 선제적으로 확인하는 역할을 합니다.
"""

import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Config:
    """
    애플리케이션 전역 설정 값 관리 및 검증 클래스.

    Google API 권한 스코프, 대상 드라이브 디렉토리, PDF 렌더링 폰트 경로, 
    다중 Gemini API 키 목록, Notion 토큰, API 쿨타임 및 지원 모델 목록 등 
    전체 시스템에서 공유하고 의존하는 상태와 상수를 정의하고 제공하는 책임을 가집니다.
    """
    
    @staticmethod
    def extract_drive_id(id_or_url: str) -> str:
        """
        주어진 문자열(Google Drive URL 또는 ID)에서 실제 Drive 폴더나 파일의 고유 ID만 추출합니다.

        Google Drive의 URL은 `/folders/`, `/file/d/`, 혹은 쿼리스트링 `?id=` 등 매우 다양한 형태로 
        제공될 수 있습니다. 사용자가 `.env` 파일에 전체 URL을 그대로 복사하여 붙여넣는 경우가 빈번하게 발생하므로, 
        API 호출에 필요한 순수 식별자(ID)만을 추출하도록 정규식을 통해 유연하고 안전하게 파싱해야 합니다. 
        이 과정은 설정 값을 불러오는 시점에 자동화되어 사용자 편의성과 프로그램의 안정성을 높입니다.
        만약 입력값이 이미 순수 ID 형태인 경우에는 정규식에 매칭되지 않아 원래의 값을 그대로 반환합니다.

        Args:
            id_or_url (str): 사용자가 입력한 Google Drive의 폴더/파일 URL 문자열 또는 순수 ID 문자열.

        Returns:
            str: 정규식을 통해 파싱된 15~33자리 수준의 Google Drive 고유 ID. 
                 입력값이 비어있거나 None일 경우 빈 문자열("")을 반환합니다.
        """
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
        """
        애플리케이션 구동에 필수적인 전역 설정값들의 유효성을 사전 검증합니다.

        이 메서드는 애플리케이션 또는 파이프라인의 초기화 단계에서 명시적으로 호출되어야 합니다.
        파이프라인이 본격적으로 실행되어 중간 과정에서 API 키나 토큰이 누락된 것이 발견되면, 
        비용이 발생하거나 데이터 처리가 중단되는 불상사가 생길 수 있습니다. 따라서 이를 방지하고자 
        Fail-Fast(빠른 실패) 전략을 통해 런타임 에러를 미연에 방지하는 핵심적인 역할을 수행합니다.
        필수 설정(Drive 디렉토리, Gemini API 키) 누락 시 즉각 예외를 발생시키지만, 
        선택적 기능(Notion 토큰)의 경우 경고 로그만 남기고 시스템 실행을 중단시키지 않습니다.

        Raises:
            ValueError: 'TARGET_DRIVE_DIR' 환경 변수가 설정되지 않았거나 유효한 Drive ID를 추출하지 못한 경우.
            ValueError: 'GEMINI_KEY_' 접두사로 시작하는 API 키가 환경 변수에서 단 하나도 로드되지 않은 경우.
        """
        if not cls.TARGET_DRIVE_DIR:
            raise ValueError("❌ .env 설정 오류: 'TARGET_DRIVE_DIR'가 설정되지 않았습니다.")
        if not cls.GEMINI_KEYS:
            raise ValueError("❌ .env 설정 오류: 최소 하나 이상의 'GEMINI_KEY'가 필요합니다.")
        if not cls.NOTION_TOKEN:
            print("⚠️ 경고: 'NOTION_TOKEN'이 설정되지 않았습니다. Notion 동기화 기능이 제한될 수 있습니다.")