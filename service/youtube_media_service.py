from base.base_service import BaseService

"""유튜브 미디어 다운로드 및 구글 드라이브 업로드 전담 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
사용자가 지정한 유튜브 URL로부터 음원 데이터를 추출하고, 이를 Whisper AI 전사(STT)에 
적합한 형태의 물리적 파일로 변환하여 구글 드라이브(클라우드)에 적재하는 핵심 I/O 브리지 역할을 수행합니다.

백그라운드 Worker 스레드(또는 YoutubePlaylistController)에 의해 호출되어 메인 UI의 
차단(Freezing) 없이 무거운 미디어 트랜스코딩과 대용량 네트워크 업로드를 비동기적이고 
안전하게 파이프라이닝(Pipelining) 할 수 있도록 돕습니다.
"""
import os
import tempfile
from typing import Any, Callable, Optional

import yt_dlp



class YoutubeMediaService(BaseService):
    def __init__(self):
        super().__init__()
    """유튜브 음원 추출(yt-dlp) 및 구글 드라이브 업로드를 전담하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라 이 클래스는 재생목록의 메타데이터를 관리하거나 
    상태를 추적하지 않고, 오직 단일 영상 URL을 전달받아 물리적 오디오(WAV)로 추출하고 
    클라우드에 전송하는 미디어 스트리밍 및 I/O 연산만을 책임집니다.

    의존성:
    - 음원 추출: 외부 패키지인 `yt_dlp`와 시스템에 설치된 `FFmpeg`에 강하게 의존하여 포맷을 변환합니다.
    - 클라우드 전송: `utils.auth_util.get_drive_service`를 통해 인증된 API 리소스와 통신합니다.
    """
    
    # ===========================
    # [오디오 다운로드 및 업로드]
    # ===========================
    def download_and_upload_audio(self, url: str, prefix: str, drive_folder_id: str, cancel_checker: Optional[Callable[[], bool]] = None) -> None:
        
        # 임시 디렉토리를 생성하여 변환 후 찌꺼기 파일 자동 삭제 보장
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_wav_path = os.path.join(temp_dir, f'{prefix}.wav')
            
            def progress_hook(d):
                if cancel_checker and cancel_checker():
                    raise InterruptedError("사용자에 의해 다운로드가 취소되었습니다.")

            # yt-dlp 옵션 설정: 최고 품질의 오디오를 다운로드하여 16kHz 모노 WAV로 후처리
            ydl_opts = {
                'format': 'ba[ext=m4a]/bestaudio/best', 
                'outtmpl': os.path.join(temp_dir, f'{prefix}.%(ext)s'),
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
                'postprocessor_args': {'ffmpeg': ['-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1']},
                'quiet': True, 'no_warnings': True,
                'progress_hooks': [progress_hook]
            }
            
            # 오디오 다운로드 및 트랜스코딩 수행
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cancel_checker and cancel_checker():
                raise InterruptedError("다운로드 완료 후 업로드 전 취소되었습니다.")

            # 파일이 정상적으로 생성되었는지 검증
            if not os.path.exists(temp_wav_path):
                raise FileNotFoundError(f"변환 실패 (파일 미생성): {prefix}")

            # 구글 드라이브 업로드 실행
            self.app.drive_client.upload_to_drive(temp_wav_path, drive_folder_id, mime_type='audio/wav', new_file_name=f'{prefix}.wav')
