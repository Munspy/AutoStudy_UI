from base.base_worker import BaseWorker


class ExamCategoryFetchWorker(BaseWorker):
    """구글 드라이브의 2연속 폴더 구조를 분석하여 시험 기준 목록을 가져오는 워커."""
    
    def __init__(self, force_refresh: bool = False):
        super().__init__()
        self.force_refresh = force_refresh
        
    def do_work(self):
        self._log("구글 드라이브에서 시험 기준(과목/차수) 폴더 목록을 조회합니다...")
        if self.is_cancelled():
            return []
        categories = self.app.drive_sync.fetch_exam_categories(force_refresh=self.force_refresh)
        return categories

