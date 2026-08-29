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
import yt_dlp
from typing import Any
from googleapiclient.http import MediaFileUpload
from utils.auth_util import get_drive_service

class YoutubeMediaService:
    """유튜브 음원 추출(yt-dlp) 및 구글 드라이브 업로드를 전담하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라 이 클래스는 재생목록의 메타데이터를 관리하거나 
    상태를 추적하지 않고, 오직 단일 영상 URL을 전달받아 물리적 오디오(WAV)로 추출하고 
    클라우드에 전송하는 미디어 스트리밍 및 I/O 연산만을 책임집니다.

    의존성:
    - 음원 추출: 외부 패키지인 `yt_dlp`와 시스템에 설치된 `FFmpeg`에 강하게 의존하여 포맷을 변환합니다.
    - 클라우드 전송: `utils.auth_util.get_drive_service`를 통해 인증된 API 리소스와 통신합니다.
    """
    
    def download_and_upload_audio(self, url: str, prefix: str, drive_folder_id: str, drive_service: Any) -> None:
        """단일 유튜브 영상을 WAV 포맷으로 추출한 뒤 구글 드라이브에 안전하게 업로드합니다.

        자동화된 학습 자료 파이프라인에서 Whisper AI가 음성을 텍스트로 원활하게 변환하기 
        위해서는 입력 오디오의 엄격한 규격화가 필수적입니다. 
        이 메서드는 단순한 영상 다운로드를 넘어, `yt-dlp`와 `FFmpeg` 후처리(post-processor)를 연계하여 
        스트리밍된 미디어를 강제로 **16kHz, 1채널(Mono)** WAV 파일로 트랜스코딩합니다. 
        이 규격은 Whisper STT 엔진이 요구하는 최적의 오디오 포맷이므로, 하위 파이프라인에서 
        오디오 리샘플링 작업을 다시 수행하는 오버헤드를 원천적으로 제거합니다.

        또한, 장시간 연속으로 영상을 다운로드하는 배치(Batch) 처리 환경에서 
        로컬 디스크 공간이 고갈되거나 파일 덮어쓰기 충돌이 발생하지 않도록 
        `tempfile.TemporaryDirectory` 격리 공간 내에서 다운로드와 변환을 수행합니다. 
        네트워크 업로드가 끝난 후 `with` 블록을 빠져나가면 즉시 찌꺼기 미디어 파일들을 휘발(Clean-up)시켜 
        시스템 리소스를 안전하게 회수합니다.

        Args:
            url (str): 음원을 추출할 대상 유튜브 영상의 단일 URL.
            prefix (str): 로컬 임시 파일 생성 및 구글 드라이브 저장 시 사용할 파일명 (확장자 제외). 
                일반적으로 파이프라인 상태 관리를 위한 '날짜_교시' 형태의 식별자가 주입됩니다.
            drive_folder_id (str): 추출된 WAV 파일이 업로드될 구글 드라이브 대상 폴더의 고유 ID.
            drive_service (Any): 인증이 완료된 구글 드라이브 API 서비스 객체. 
                (내부 구현상 `get_drive_service()` 호출을 통해 최신 객체로 한 번 더 덮어씌워 
                장기 실행 시 토큰 만료 문제를 방어합니다.)

        Returns:
            None: 반환값 없이 외부 스토리지(구글 드라이브)에 업로드를 수행하고 종료됩니다.

        Raises:
            FileNotFoundError: `yt-dlp` 다운로드 및 FFmpeg 변환 프로세스가 실패하여 
                임시 디렉토리 내에 지정된 이름의 WAV 파일이 정상적으로 생성되지 않았을 때 발생합니다.
            Exception: 구글 드라이브 네트워크 업로드 중 토큰 만료, 클라우드 용량 초과, 
                네트워크 단절 등의 이유로 `MediaFileUpload` 객체의 `.execute()`가 실패할 때 발생합니다.
        """
        drive_service = get_drive_service()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_wav_path = os.path.join(temp_dir, f'{prefix}.wav')
            
            ydl_opts = {
                'format': 'ba[ext=m4a]/bestaudio/best', 
                'outtmpl': os.path.join(temp_dir, f'{prefix}.%(ext)s'),
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
                'postprocessor_args': {'ffmpeg': ['-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1']},
                'quiet': True, 'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if not os.path.exists(temp_wav_path):
                raise FileNotFoundError(f"변환 실패 (파일 미생성): {prefix}")

            file_metadata = {'name': f'{prefix}.wav', 'parents': [drive_folder_id]}
            media = MediaFileUpload(temp_wav_path, mimetype='audio/wav', resumable=True)
            drive_service.files().create(body=file_metadata, media_body=media).execute()