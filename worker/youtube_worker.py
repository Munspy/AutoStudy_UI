from base.base_worker import BaseWorker
from service.youtube_playlist_service import YoutubePlaylistService
from service.youtube_media_service import YoutubeMediaService
from service.file_naming_service import FileNamingService
from utils.auth_util import get_drive_service
from utils.config import Config

class PlaylistFetchWorker(BaseWorker):
    def __init__(self, playlist_id: str):
        super().__init__()
        self.playlist_id = playlist_id
        self.yt_service = YoutubePlaylistService()
        self.naming_service = FileNamingService()

    def _task(self):
        drive_folder_id = Config.TARGET_DRIVE_DIR
        
        self.log_signal.emit("구글 계정 연동 확인 및 드라이브 상태를 조회합니다...")
        # 팁: get_existing_prefixes_in_drive는 기존처럼 yt_service에 있다고 가정
        existing_prefixes = self.yt_service.get_existing_prefixes_in_drive(get_drive_service(), drive_folder_id)
        
        self.log_signal.emit("공식 YouTube API를 통해 영상 목록과 길이를 일괄 조회합니다 🚀")
        videos = self.yt_service.fetch_playlist_videos(self.playlist_id, existing_prefixes, self.naming_service)
        
        return videos


class YoutubeUploadWorker(BaseWorker):
    def __init__(self, target_videos: list):
        super().__init__()
        self.target_videos = target_videos
        self.media_service = YoutubeMediaService()

    def _task(self):
        drive_folder_id = Config.TARGET_DRIVE_DIR
        total_videos = len(self.target_videos)
        
        for idx, item in enumerate(self.target_videos):
            if not self._is_running: break
            
            prefix = item['prefix']
            self.log_signal.emit(f"📥 다운로드 및 드라이브 업로드 중 ({idx+1}/{total_videos}): {prefix}")
            self.progress_signal.emit(int((idx / total_videos) * 100))
            
            try:
                self.media_service.download_and_upload_audio(item['video_url'], prefix, drive_folder_id)
                self.log_signal.emit(f"✅ 업로드 완료: {prefix}.wav")
            except Exception as e:
                self.log_signal.emit(f"❌ {str(e)}")
                
        self.progress_signal.emit(100)
        return "UPLOAD_DONE"


class PlaylistUpdateCheckerWorker(BaseWorker):
    def __init__(self, playlists: list):
        super().__init__()
        self.playlists = playlists
        self.yt_service = YoutubePlaylistService()

    def _task(self):
        self.log_signal.emit(f"유튜브 서버에 접속하여 {len(self.playlists)}개 재생목록의 업데이트 날짜를 확인합니다...")
        updated_playlists = self.yt_service.check_playlists_updates(self.playlists)
        return updated_playlists