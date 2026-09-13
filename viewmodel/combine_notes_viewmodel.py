from PyQt6.QtCore import pyqtSignal
from core.logger import GlobalLogger
from base.base_viewmodel import BaseViewModel
from worker.pdf import (PdfCombineSaveWorker, PdfInspectionWorker,
                        PdfMatchListWorker)

class CombineNotesViewModel(BaseViewModel):
    # 1. 데이터를 싣지 않는 순수 '알람(Trigger)' 시그널로 변경
    matched_groups_changed = pyqtSignal()
    inspection_data_changed = pyqtSignal()
    merge_completed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 2. UI가 들고 있던 비즈니스 데이터를 ViewModel이 전적으로 소유함!
        self.matched_groups = {}
        self.base_data = []

    def start_get_matched_groups(self, folder_path):
        worker = PdfMatchListWorker(folder_path)
        # 워커가 끝나면 중간 가로채기 함수(_on_match_list_ready)로 연결
        worker.finished_signal.connect(self._on_match_list_ready)
        self.start_worker(worker)

    def _on_match_list_ready(self, result):
        # 뷰모델이 자신의 상태(데이터)를 업데이트한 뒤, 화면에 알람만 발사
        self.matched_groups = result
        self.matched_groups_changed.emit()

    def start_inspection(self, folder_path, selected_keys):
        # UI에서 데이터를 받을 필요 없이, 자신이 들고 있는 self.matched_groups를 사용
        worker = PdfInspectionWorker(folder_path, selected_keys, self.matched_groups)
        worker.finished_signal.connect(self._on_inspection_ready)
        self.start_worker(worker)

    def _on_inspection_ready(self, result):
        self.base_data = result
        self.inspection_data_changed.emit()

    def start_merge(self, folder_path, is_drive=True):
        # 병합할 때도 UI가 주는 게 아니라 자신이 들고 있는 self.base_data를 사용
        worker = PdfCombineSaveWorker(self.base_data, folder_path, is_drive=is_drive)
        worker.finished_signal.connect(self.merge_completed.emit)
        self.start_worker(worker)

    def delete_files(self, paths):
        # 뷰모델은 묻지도 따지지도 않고 컨테이너의 서비스에 위임
        self.app.file.delete_files(
            file_paths_or_ids=paths,
            is_drive=False,
            log_callback=GlobalLogger.info
        )