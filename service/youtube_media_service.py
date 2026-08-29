# service/youtube_media_service.py (신설: 다운로드/업로드 전담)
import os
import tempfile
import yt_dlp
from typing import Any
from googleapiclient.http import MediaFileUpload
from utils.auth_util import get_drive_service

class YoutubeMediaService:
    """유튜브 음원 추출(yt-dlp) 및 구글 드라이브 업로드를 전담합니다."""
    
    def download_and_upload_audio(self, url: str, prefix: str, drive_folder_id: str, drive_service: Any) -> None:
        """단일 영상을 WAV로 추출 후 드라이브에 업로드합니다."""
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