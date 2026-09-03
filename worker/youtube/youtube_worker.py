from base.base_worker import BaseWorker
from service.youtube_playlist_service import YoutubePlaylistService
from service.youtube_media_service import YoutubeMediaService
from service.file_naming_service import FileNamingService
from utils.auth_util import get_drive_service
from utils.config import Config

class PlaylistFetchWorker(BaseWorker):
    """유튜브 재생목록 데이터를 수집하는 워커 클래스입니다."""
    
    def __init__(self, playlist_id: str):
        """PlaylistFetchWorker 초기화."""
        super().__init__()
        self.playlist_id = playlist_id
        self.yt_service = YoutubePlaylistService(logger_callback=self.log_signal.emit)
        self.naming_service = FileNamingService(logger_callback=self.log_signal.emit)

    def do_work(self):
        """재생목록 내의 비디오 목록을 가져옵니다."""
        drive_folder_id = Config.TARGET_DRIVE_DIR
        
        # ===========================
        # [드라이브 상태 조회]
        # ===========================
        self.log_signal.emit("구글 계정 연동 확인 및 드라이브 상태를 조회합니다...")
        if self.is_cancelled(): return
        # 드라이브 내에 이미 존재하는 접두사(prefix) 목록을 조회합니다.
        existing_prefixes = self.yt_service.get_existing_prefixes_in_drive(get_drive_service(), drive_folder_id)
        
        # ===========================
        # [재생목록 영상 조회]
        # ===========================
        if self.is_cancelled(): return
        self.log_signal.emit("공식 YouTube API를 통해 영상 목록과 길이를 일괄 조회합니다 🚀")
        # 비디오 목록을 가져와서 반환합니다.
        videos = self.yt_service.fetch_playlist_videos(self.playlist_id, existing_prefixes, self.naming_service)
        
        return videos


class YoutubeUploadWorker(BaseWorker):
    """선택된 유튜브 영상을 다운로드하고 드라이브에 업로드하는 워커 클래스입니다."""
    
    def __init__(self, target_videos: list):
        """YoutubeUploadWorker 초기화."""
        super().__init__()
        self.target_videos = target_videos
        self.media_service = YoutubeMediaService(logger_callback=self.log_signal.emit)

    def do_work(self):
        """대상 비디오들의 다운로드 및 업로드 작업을 수행합니다."""
        drive_folder_id = Config.TARGET_DRIVE_DIR
        total_videos = len(self.target_videos)
        
        # ===========================
        # [비디오 업로드 루프]
        # ===========================
        for idx, item in enumerate(self.target_videos):
            if self.is_cancelled(): break
            
            prefix = item['prefix']
            self.log_signal.emit(f"📥 다운로드 및 드라이브 업로드 중 ({idx+1}/{total_videos}): {prefix}")
            self.progress_signal.emit(int((idx / total_videos) * 100), "")
            
            # ===========================
            # [오디오 다운로드 및 업로드]
            # ===========================
            try:
                # 오디오를 다운로드하여 구글 드라이브에 업로드합니다.
                self.media_service.download_and_upload_audio(
                    url=item['url'],
                    prefix=prefix,
                    drive_folder_id=drive_folder_id
                )
                self.log_signal.emit(f"✅ 업로드 완료: {prefix}.wav")
            except Exception as e:
                # 예외 발생 시 로그 시그널 방출
                self.log_signal.emit(f"❌ {str(e)}")
                
        # 모든 작업이 완료되면 진행도를 100%로 설정합니다.
        self.progress_signal.emit(100, "")
        return "UPLOAD_DONE"


class PlaylistUpdateCheckerWorker(BaseWorker):
    """저장된 재생목록의 업데이트 여부를 확인하는 워커 클래스입니다."""
    
    def __init__(self, playlists: list):
        """PlaylistUpdateCheckerWorker 초기화."""
        super().__init__()
        self.playlists = playlists
        self.yt_service = YoutubePlaylistService(logger_callback=self.log_signal.emit)

    def do_work(self):
        """각 재생목록의 최신 업데이트 상태를 확인합니다."""
        # ===========================
        # [업데이트 상태 확인]
        # ===========================
        self.log_signal.emit(f"유튜브 서버에 접속하여 {len(self.playlists)}개 재생목록의 업데이트 날짜를 확인합니다...")
        if self.is_cancelled(): return
        
        # 유튜브 서비스 모듈을 통해 업데이트 여부를 체크합니다.
        updated_playlists = self.yt_service.check_playlists_updates(self.playlists)
        return updated_playlists