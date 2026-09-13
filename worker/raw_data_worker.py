from base.base_worker import BaseWorker

class RawDataLoadWorker(BaseWorker):
    """Raw Data (PDF 및 텍스트)를 드라이브에서 검색하고 로드하는 워커입니다."""
    def __init__(self, date_str: str, period_str: str):
        super().__init__()
        self.date_str = date_str
        self.period_str = period_str

    def do_work(self):
        return self.app.raw_data.fetch_raw_data(self.date_str, self.period_str)

class RawDataApplyWorker(BaseWorker):
    """모든 텍스트 수정사항을 취합하여 구글 드라이브에 업로드하는 워커입니다."""
    def __init__(self, text_dict, total_pages, text_file_id, text_file_name, text_file_parent_id):
        super().__init__()
        self.text_dict = text_dict
        self.total_pages = total_pages
        self.text_file_id = text_file_id
        self.text_file_name = text_file_name
        self.text_file_parent_id = text_file_parent_id

    def do_work(self):
        return self.app.raw_data.apply_raw_data(
            self.text_dict, 
            self.total_pages, 
            self.text_file_id, 
            self.text_file_name, 
            self.text_file_parent_id
        )
