import os
from typing import List, Set, Optional, Callable, Any

from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.filename_util import normalize_text
from base.base_service import BaseService
from utils.config import Config

class WhisperService(BaseService):
    """Whisper 전사가 필요한 미처리 오디오 파일을 탐색하고 필터링하는 서비스입니다."""
    
    # [최적화 1] 매직 스트링 상수화 및 중복 제거
    AUDIO_EXTENSIONS = ('.wav', '.m4a', '.mp3', '.mp4', '.aac', '.flac')
    INDICATOR_EXTENSIONS = ('_음성스크립트.txt', '_최종교정본.txt', '_done.json', '_scripted.pdf')
    
    def __init__(
        self, 
        drive_service: Optional[Any] = None, 
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        super().__init__(logger_callback=logger_callback)
        # [최적화 3] 의존성 주입(DI) 허용으로 유연성 및 테스트 용이성 확보
        self.drive_service = drive_service or get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR

    def get_pending_audio_files(self) -> List[str]:
        """드라이브를 스캔하여 전사가 아직 완료되지 않은 오디오 파일 목록을 반환합니다."""
        self._log("📂 대상 폴더의 모든 파일을 탐색 중입니다...")
        all_files = get_all_drive_files(self.target_folder_id, drive_service=self.drive_service)
        
        audio_files: List[str] = []
        completed_bases: Set[str] = set()
        
        # 1. 파일 분류 및 식별자(base_name) 캐싱
        for f in all_files:
            name: str = normalize_text(f.get('name', ''))
            name_lower = name.lower()
            
            if name_lower.endswith(self.AUDIO_EXTENSIONS):
                audio_files.append(name)
            else:
                # [최적화 2] 식별 파일일 경우 확장자를 제외한 base_name만 추출하여 Set에 저장
                for ext in self.INDICATOR_EXTENSIONS:
                    if name_lower.endswith(ext):
                        # 대소문자 원본을 유지하기 위해 원래 name에서 슬라이싱
                        base_name = name[:-len(ext)]
                        completed_bases.add(base_name)
                        break  # 하나의 완료 식별자만 확인되면 충분함
        
        incomplete_audio_files: List[str] = []
        
        self._log("🔍 전사 여부를 교차 검증 중입니다...")
        # 2. 미완료 파일 필터링 로직 (O(1) 단일 탐색)
        for audio_name in audio_files:
            base_name: str = os.path.splitext(audio_name)[0]
            
            # 단 한 번의 Set 탐색으로 교차 검증 완료
            if base_name not in completed_bases:
                incomplete_audio_files.append(audio_name)
                
        self._log(f"🔎 스캔 완료: 총 {len(incomplete_audio_files)}개의 미전사 음성 파일 발견")
        return sorted(incomplete_audio_files)