"""Whisper AI 음성 전사 대기열 탐색 및 필터링 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.[cite: 1]
Google Drive와 연동하여 아직 텍스트로 변환(Transcription)되지 않은 원본 오디오/비디오 미디어 파일들을 
탐색하고 필터링하는 핵심 비즈니스 로직을 담당합니다. 
백그라운드에서 동작하는 Worker 스레드나 Controller가 Whisper AI 변환 작업을 시작하기 전, 
어떤 파일을 처리해야 할지 결정하는 작업 큐(Queue) 생성의 전처리 역할을 수행합니다.
"""
import os
from typing import List, Set, Optional, Callable, Any

from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.filename_util import normalize_text
from base.base_service import BaseService
from utils.config import Config

class WhisperService(BaseService):
    """Whisper 전사가 필요한 미처리 오디오 파일을 탐색하고 필터링하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 직접 Whisper AI 모델을 구동하거나 오디오를 처리하지 않고, 
    오직 클라우드(Google Drive) 상의 파일 메타데이터를 분석하여 '처리 대상 파일 목록'을 추출하는 책임만 가집니다.[cite: 1]

    의존성:
    - 구글 드라이브 API 연동을 위해 `utils.auth_util.get_drive_service` 및 `utils.drive_api.get_all_drive_files`를 사용합니다.[cite: 1]
    - 이 서비스의 결과물은 Controller나 Whisper를 구동하는 하위 Worker 계층으로 전달됩니다.
    """
    
    # [최적화 1] 매직 스트링 상수화 및 중복 제거
    AUDIO_EXTENSIONS = ('.wav', '.m4a', '.mp3', '.mp4', '.aac', '.flac')
    INDICATOR_EXTENSIONS = ('_음성스크립트.txt', '_최종교정본.txt', '_done.json', '_scripted.pdf')
    
    # ===========================
    # [초기화 및 설정]
    # ===========================
    def __init__(
        self, 
        drive_service: Optional[Any] = None, 
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """WhisperService 인스턴스를 초기화하고 드라이브 API 통신 환경을 설정합니다.

        Args:
            drive_service (Optional[Any], optional): 외부에서 주입할 수 있는 인증된 Google Drive API 서비스 객체. 
                테스트 용이성(DI)을 위해 제공되며, None일 경우 기본 인증 유틸리티를 통해 자동 생성합니다. Defaults to None.
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 스레드 환경에서 
                발생하는 스캔 진행 상태 로그를 UI로 안전하게 전달하기 위한 콜백 함수. Defaults to None.
        """
        super().__init__(logger_callback=logger_callback)
        # [최적화 3] 의존성 주입(DI) 허용으로 유연성 및 테스트 용이성 확보
        self.drive_service = drive_service or get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR

    # ===========================
    # [미처리 오디오 탐색 및 필터링]
    # ===========================
    def get_pending_audio_files(self) -> List[str]:
        """드라이브를 스캔하여 전사가 아직 완료되지 않은 오디오 파일 목록을 반환합니다.

        자동화 파이프라인에서 중복 처리를 방지(멱등성 보장)하기 위한 핵심 판별 로직입니다. 
        드라이브에 수많은 파일이 누적되어 있을 때, 오디오 파일(`.mp4`, `.mp3` 등)과 처리 완료를 나타내는 
        식별 파일(`_음성스크립트.txt`, `_done.json` 등)을 한 번에 스캔합니다. 
        
        완료된 파일들의 `base_name`(확장자를 제외한 순수 파일명)을 Set(집합) 자료구조에 캐싱해두고, 
        오디오 파일들의 `base_name`이 이 Set에 존재하는지 단일 탐색(O(1))으로 교차 검증합니다. 
        이를 통해 불필요한 API 다중 호출이나 디스크 I/O 없이 빠르고 정확하게 미처리된 새 오디오 파일만 
        걸러내어 비동기 파이프라인의 작업 대기열(Queue)로 넘길 수 있습니다.

        Args:
            없음

        Returns:
            List[str]: 아직 처리 완료 식별 파일이 존재하지 않는 미전사 오디오 파일명 리스트. 
                결과는 알파벳/숫자 오름차순으로 정렬(sorted)되어 반환됩니다.
        """
        self._log("📂 대상 폴더의 모든 파일을 탐색 중입니다...")
        # 구글 드라이브 타겟 폴더의 모든 파일을 조회
        all_files = get_all_drive_files(self.target_folder_id, drive_service=self.drive_service)
        
        audio_files: List[str] = []
        completed_bases: Set[str] = set()
        
        # 1. 파일 분류 및 식별자(base_name) 캐싱
        for f in all_files:
            # 파일명을 가져와서 공백 등을 정규화
            name: str = normalize_text(f.get('name', ''))
            name_lower = name.lower()
            
            # 오디오 확장자인 경우 목록에 추가
            if name_lower.endswith(self.AUDIO_EXTENSIONS):
                audio_files.append(name)
            else:
                # [최적화 2] 식별 파일일 경우 확장자를 제외한 base_name만 추출하여 Set에 저장
                for ext in self.INDICATOR_EXTENSIONS:
                    # 완료 식별자를 포함하고 있는지 검사
                    if name_lower.endswith(ext):
                        # 대소문자 원본을 유지하기 위해 원래 name에서 슬라이싱하여 base_name 추출
                        base_name = name[:-len(ext)]
                        completed_bases.add(base_name)
                        break  # 하나의 완료 식별자만 확인되면 충분함
        
        incomplete_audio_files: List[str] = []
        
        self._log("🔍 전사 여부를 교차 검증 중입니다...")
        # 2. 미완료 파일 필터링 로직 (O(1) 단일 탐색)
        for audio_name in audio_files:
            base_name: str = os.path.splitext(audio_name)[0]
            
            # 단 한 번의 Set 탐색으로 교차 검증 완료: 캐시된 식별자에 없으면 미완료
            if base_name not in completed_bases:
                incomplete_audio_files.append(audio_name)
                
        self._log(f"🔎 스캔 완료: 총 {len(incomplete_audio_files)}개의 미전사 음성 파일 발견")
        # 발견된 오디오 파일을 오름차순 정렬하여 반환
        return sorted(incomplete_audio_files)
