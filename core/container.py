# 서비스들을 전역으로 관리하는 컨테이너 (지연 초기화 지원)
from core.task_manager import TaskManager
from service.file_naming_service import FileNamingService
from service.folder_management_service import FolderManagementService
from service.llm_service import LlmService
from service.pdf_render_service import PdfRenderService
from service.timetable_service import TimetableService
from service.whisper_service import WhisperService
from service.notion_sync_service import NotionSyncService
from service.pdf_operation_service import PdfOperationService
from service.youtube_media_service import YoutubeMediaService
from service.text_processing_service import TextProcessingService
from service.pdf_ocr_service import PdfOcrService
from service.anki_service import AnkiGenerationService
from service.youtube_playlist_service import YoutubePlaylistService
from service.pipeline_status_service import PipelineStatusService
from service.pdf_analysis_service import PdfAnalysisService
from service.summary_pdf_service import SummaryPdfService
from service.notion_backup_service import NotionBackupService
from service.drive_sync_service import DriveSyncService
from service.ai_pipeline_service import AiPipelineService

class AppContainer:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # 인스턴스 캐시 딕셔너리
        self._services = {}

    def _get_or_create(self, key, factory_func):
        """지연 초기화(Lazy Initialization)를 통해 첫 호출 시에만 객체를 생성합니다."""
        if key not in self._services:
            self._services[key] = factory_func()
        return self._services[key]

    # 1. Base Services (No dependencies)
    @property
    def file_naming(self): return self._get_or_create('file_naming', lambda: FileNamingService())
    
    @property
    def folder_mgmt(self): return self._get_or_create('folder_mgmt', lambda: FolderManagementService())
    
    @property
    def llm(self): return self._get_or_create('llm', lambda: LlmService())
    
    @property
    def pdf_render(self): return self._get_or_create('pdf_render', lambda: PdfRenderService())
    
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
    def yt_playlist(self): return self._get_or_create('yt_playlist', lambda: YoutubePlaylistService(naming_service=self.file_naming))
    
    @property
    def pipeline_status(self): return self._get_or_create('pipeline_status', lambda: PipelineStatusService(naming_service=self.file_naming))
    
    @property
    def pdf_analysis(self): return self._get_or_create('pdf_analysis', lambda: PdfAnalysisService(naming_service=self.file_naming, ocr_service=self.pdf_ocr))
    
    # 3. Level 2 Dependencies
    @property
    def summary_pdf(self): return self._get_or_create('summary_pdf', lambda: SummaryPdfService(pdf_renderer=self.pdf_render, yt_service=self.youtube_media, timetable_service=self.timetable))
    
    @property
    def notion_backup(self): return self._get_or_create('notion_backup', lambda: NotionBackupService(yt_playlist_service=self.yt_playlist, timetable_service=self.timetable))
    
    # 4. Top Level Dependencies
    @property
    def ai_pipeline(self): return self._get_or_create('ai_pipeline', lambda: AiPipelineService(llm_service=self.llm, folder_service=self.folder_mgmt, summary_pdf_service=self.summary_pdf, anki_gen_service=self.anki_gen, pdf_ocr_service=self.pdf_ocr))

    @property
    def drive_sync(self): return self._get_or_create('drive_sync', lambda: DriveSyncService(naming_service=self.file_naming, pipeline_service=self.pipeline_status, yt_service=self.youtube_media, timetable_service=self.timetable))

    # 5. Core Infrastructure
    @property
    def task_manager(self): return self._get_or_create('task_manager', lambda: TaskManager(max_concurrent_tasks=5, llm_max_tasks=5))
