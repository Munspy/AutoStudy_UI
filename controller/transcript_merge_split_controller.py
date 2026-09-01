# controller/transcript_merge_split_controller.py
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from utils.file_util import list_local_files
from worker.transcript.transcript_worker import (
    TranscriptDriveSearchWorker, 
    TranscriptReadWorker, 
    TranscriptSplitSaveWorker, 
    TranscriptMergeSaveWorker
)

class TranscriptController(BaseController):
    search_completed = pyqtSignal(list)
    files_read_completed = pyqtSignal(int, list, list)
    split_save_completed = pyqtSignal(list)
    merge_save_completed = pyqtSignal(str)

    def __init__(self, task_manager=None):
        super().__init__(task_manager)
        self.drive_files_cache = {}

    def get_local_text_files(self, directory: str):
        return list_local_files(directory, extension=".txt")

    def execute_drive_search(self, start_date, end_date):
        worker = TranscriptDriveSearchWorker(start_date, end_date)
        def on_search_completed(result):
            if result:
                files, cache = result
                self.drive_files_cache = cache
                self.search_completed.emit(files)
        worker.finished_signal.connect(on_search_completed)
        self.start_worker(worker)

    def execute_read_files(self, filenames, folder_path, is_drive):
        worker = TranscriptReadWorker(filenames, folder_path, is_drive, drive_cache=self.drive_files_cache if is_drive else None)
        worker.finished_signal.connect(
            lambda res: self.files_read_completed.emit(len(res["filenames"]), res["filenames"], res["contents"]) if res else None
        )
        self.start_worker(worker)

    def execute_split_save(self, folder_path, filename, text_content, name1, name2, is_drive):
        worker = TranscriptSplitSaveWorker(folder_path, filename, text_content, name1, name2, is_drive)
        worker.finished_signal.connect(self.split_save_completed.emit)
        self.start_worker(worker)

    def execute_merge_save(self, folder_path, files_to_merge, merged_content, custom_name, is_drive):
        worker = TranscriptMergeSaveWorker(folder_path, files_to_merge, merged_content, custom_name, is_drive)
        worker.finished_signal.connect(self.merge_save_completed.emit)
        self.start_worker(worker)

def generate_split_filenames(filename: str) -> list:
    from service.file_naming_service import FileNamingService
    return FileNamingService().generate_split_filenames(filename)

def generate_merged_filename(filenames: list) -> str:
    from service.file_naming_service import FileNamingService
    return FileNamingService().generate_merged_filename(filenames)
