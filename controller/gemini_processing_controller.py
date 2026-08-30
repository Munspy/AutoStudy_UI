from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.llm_worker import LLMTaskWorker, LLMScanWorker

class GeminiProcessingController(BaseController):
    scan_completed = pyqtSignal(list, bool)
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_manager=None):
        super().__init__(task_manager)
        self.ui = None

    def start_scan(self, is_force_rerun=False, target_mmdd=None):
        worker = LLMScanWorker(is_force_rerun, target_mmdd)
        worker.finished_signal.connect(lambda result: self.scan_completed.emit(result, is_force_rerun))
        self.start_worker(worker)

    def start_tasks(self, task_queue: list):
        # 1. 받은 데이터를 워커 객체들로 변환만 싹 해줍니다.
        worker_list = []
        for task in task_queue:
            worker = LLMTaskWorker(task)
            # LLM만의 특수한 시그널 연결은 여기서 해줌
            worker.cell_update_signal.connect(self.cell_update_signal.emit)
            worker_list.append(worker)
            
        # 2. 공통 로그/에러 연결과 큐에 던지는 건 이미 만들어둔 갓-메서드에게 위임!
        self.start_batch_workers(worker_list, channel="LLM")

