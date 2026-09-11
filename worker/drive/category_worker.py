from base.base_worker import BaseWorker
from core.container import AppContainer


class ExamCategoryFetchWorker(BaseWorker):
    """구글 드라이브의 2연속 폴더 구조를 분석하여 시험 기준 목록을 가져오는 워커."""
    
    def __init__(self, force_refresh: bool = False):
        super().__init__()
        self.force_refresh = force_refresh
        
    def do_work(self):
        self.log_signal.emit("구글 드라이브에서 시험 기준(과목/차수) 폴더 목록을 조회합니다...")
        sync_service = AppContainer.get_instance().drive_sync
        if self.is_cancelled():
            return []
        categories = sync_service.fetch_exam_categories(force_refresh=self.force_refresh)
        return categories

