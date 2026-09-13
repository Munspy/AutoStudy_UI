import threading
# 서비스들을 전역으로 관리하는 컨테이너 (지연 초기화 지원)

# 다른 코드에서 container을 사용하여 함수를 부를 때 사용
# (이 코드에서 부를 이름) = AppContainer.get_instance().(container에서 지정해놓은 이름)
    # 이런 식으로 한번 부르고 (이 코드에서 부를 이름) 으로 계속 쓰면 됨 (import 필요 없어짐!)
# 근데 service와 worker에서는 미리 만들어 놓은 app이 있기 때문에 그걸로 부르면 더 깔끔
    # drive_client = self.app.drive_client


from infrastructure.auth_client         import GoogleAuthClient
from infrastructure.drive_client        import GoogleDriveClient
from infrastructure.llm_client          import GeminiLlmClient
from infrastructure.youtube_client      import YoutubeClient

from core.task_manager                  import TaskManager

from service.file_service               import FileService
from service.file_naming_service        import FileNamingService
from service.folder_management_service  import FolderManagementService
from service.llm_service                import LlmService
from service.pdf_render_service         import PdfRenderService
from service.raw_data_service           import RawDataService
from service.timetable_service          import TimetableService
from service.whisper_service            import WhisperService
from service.notion_sync_service        import NotionSyncService
from service.pdf_operation_service      import PdfOperationService
from service.youtube_media_service      import YoutubeMediaService
from service.text_processing_service    import TextProcessingService
from service.pdf_ocr_service            import PdfOcrService
from service.anki_service               import AnkiGenerationService
from service.youtube_playlist_service   import YoutubePlaylistService
from service.pipeline_status_service    import PipelineStatusService
from service.pdf_analysis_service       import PdfAnalysisService
from service.summary_pdf_service        import SummaryPdfService
from service.notion_backup_service      import NotionBackupService
from service.ai_pipeline_service        import AiPipelineService
from service.drive_sync_service         import DriveSyncService
from service.api_key_tracker            import APIManager

class AppContainer:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """앱 전체에서 단 하나의 container만 존재하도록 보장 (스레드 안전)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-checked locking
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        # 인스턴스 캐시 딕셔너리
        self._services = {}

    def _get_or_create(self, key, factory_func):
        """지연 초기화(Lazy Initialization)를 통해 첫 호출 시에만 객체를 생성합니다."""

        # __init__()에서 만들어 놓은 self._services 안에 방금 부른 객체가 없으면 생성
        if key not in self._services:
            self._services[key] = factory_func()

        # 없으면 생성, 있으면 그냥 찾아와서 반환
        return self._services[key]

    # 0. Core Infrastructure Clients
    # Singleton 보장!
        # 외부통신 담당 auth_client / drive_client / llm_client 단일 사무실에 부를 때마다 내부에서 전화기 생성
    @property
    def auth_client(self): return self._get_or_create('auth_client', lambda: GoogleAuthClient())
    @property
    def drive_client(self): return self._get_or_create('drive_client', lambda: GoogleDriveClient(auth_client=self.auth_client))
    @property
    def youtube_client(self): return self._get_or_create('youtube_client', lambda: YoutubeClient(auth_client=self.auth_client))

    @property
    def llm_client(self): return self._get_or_create('llm_client', lambda: GeminiLlmClient())

        # 멀티스레딩 관리 task_manager 단일한 개체를 만들어서 다들 불러서 사용
    @property
    def task_manager(self): return self._get_or_create('task_manager', lambda: TaskManager(max_concurrent_tasks=5, llm_max_tasks=5))

    # 1. Base Services
    @property
    def api_mgr(self): return self._get_or_create('api_mgr', lambda: APIManager())
    @property
    def file(self): return self._get_or_create('file', lambda: FileService())
    @property
    def file_naming(self): return self._get_or_create('file_naming', lambda: FileNamingService())
    @property
    def folder_mgmt(self): return self._get_or_create('folder_mgmt', lambda: FolderManagementService())
    @property
    def llm(self): return self._get_or_create('llm', lambda: LlmService())
    @property
    def pdf_render(self): return self._get_or_create('pdf_render', lambda: PdfRenderService())
    @property
    def raw_data(self): return self._get_or_create('raw_data', lambda: RawDataService())
    @property
    def timetable(self): return self._get_or_create('timetable', lambda: TimetableService())
    @property
    def whisper(self): return self._get_or_create('whisper', lambda: WhisperService())
    @property
    def notion_sync(self): return self._get_or_create('notion_sync', lambda: NotionSyncService())
    @property
    def pdf_operation(self): return self._get_or_create('pdf_operation', lambda: PdfOperationService())
    @property
    def youtube_media(self): return self._get_or_create('youtube_media', lambda: YoutubeMediaService())
    @property
    def text_processing(self): return self._get_or_create('text_processing', lambda: TextProcessingService())
    
    # 2. Level 1 Dependencies
    @property
    def pdf_ocr(self): return self._get_or_create('pdf_ocr', lambda: PdfOcrService())
    @property
    def anki_gen(self): return self._get_or_create('anki_gen', lambda: AnkiGenerationService())
    @property
    def yt_playlist(self): return self._get_or_create('yt_playlist', lambda: YoutubePlaylistService())
    @property
    def pipeline_status(self): return self._get_or_create('pipeline_status', lambda: PipelineStatusService())
    @property
    def pdf_analysis(self): return self._get_or_create('pdf_analysis', lambda: PdfAnalysisService())
    
    # 3. Level 2 Dependencies
    @property
    def summary_pdf(self): return self._get_or_create('summary_pdf', lambda: SummaryPdfService())
    @property
    def notion_backup(self): return self._get_or_create('notion_backup', lambda: NotionBackupService())
    
    # 4. Top Level Dependencies
    @property
    def ai_pipeline(self): return self._get_or_create('ai_pipeline', lambda: AiPipelineService())
    @property
    def drive_sync(self): return self._get_or_create('drive_sync', lambda: DriveSyncService())