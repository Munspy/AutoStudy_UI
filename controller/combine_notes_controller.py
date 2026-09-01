from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController

# 지금 PDF worker 에 너무 많은 worker들이 산재해 있는데
# 이를 적절하게 쪼개서 여러 worker 파일들로 만들어야 함
# 추후에 AI 에이전트의 도움을 받아서 해결하자

# 각 실행 코드 시작부에 self.cleanup_worker() 들이 반복되는데 다른 코드에서도 이거 다 없애야 함
from worker.pdf import PdfInspectionWorker, PdfCombineSaveWorker, PdfMatchListWorker

class CombineNotesController(BaseController):
    match_list_completed = pyqtSignal(dict)
    inspection_completed = pyqtSignal(list)
    merge_completed = pyqtSignal(list)

    def __init__(self, task_manager=None):
        super().__init__(task_manager)

    def start_get_matched_groups(self, folder_path):
        worker = PdfMatchListWorker(folder_path)
        worker.finished_signal.connect(self.match_list_completed.emit)
        self.start_worker(worker)

    def start_inspection(self, folder_path, selected_keys, matched_groups):
        """UI 입력을 바탕으로 무거운 PDF 파싱 및 매칭 검수 워커를 실행합니다."""
        worker = PdfInspectionWorker(folder_path, selected_keys, matched_groups)
        worker.finished_signal.connect(self.inspection_completed.emit)
        self.start_worker(worker)

    def start_merge(self, base_data, folder_path):
        """검수 완료된 레시피를 기반으로 디스크에 실제 PDF를 병합 저장하는 워커를 실행합니다."""
        worker = PdfCombineSaveWorker(base_data, folder_path)
        worker.finished_signal.connect(self.merge_completed.emit)
        self.start_worker(worker)
