"""음성 인식 스크립트 관리 및 Whisper AI 처리 워커 모듈.

이 패키지는 변환된 텍스트 스크립트(.txt) 파일을 구글 드라이브에서 검색 및 다운로드하고,
텍스트 병합 및 분할 처리를 담당하는 Worker 클래스들과, 로컬 미디어 파일을
Whisper AI를 이용해 텍스트로 변환하는 작업을 백그라운드에서 수행하는 Worker들을 포함합니다.
"""
from .transcript_worker import TranscriptDriveSearchWorker, TranscriptReadWorker, TranscriptSplitSaveWorker, TranscriptMergeSaveWorker
from .whisper_worker import WhisperScannerWorker, WhisperExecutionWorker

__all__ = [
    'TranscriptDriveSearchWorker', 'TranscriptReadWorker', 'TranscriptSplitSaveWorker', 'TranscriptMergeSaveWorker',
    'WhisperScannerWorker', 'WhisperExecutionWorker'
]
