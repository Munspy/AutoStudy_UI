from PyQt6.QtCore import pyqtSignal

from core.logger import GlobalLogger
from core.container import AppContainer
from core.config import Config
from base.base_viewmodel import BaseViewModel
from worker.llm.llm_worker import LLMScanWorker, LLMTaskWorker


class GeminiProcessingViewModel(BaseViewModel):
    """Gemini LLM 작업들의 실행 및 상태 관리를 담당하는 ViewModel 클래스입니다."""
    
    # ===========================
    # [시그널 정의]
    # ===========================
    scan_completed = pyqtSignal()
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_mmdd: str = ""
        self._is_force_rerun: bool = False
        self.scan_results: list = []

    @property
    def api_keys(self) -> list[str]:
        return [f"KEY_{i+1}" for i in range(len(Config.GEMINI_KEYS))]

    @property
    def models(self) -> list[str]:
        return Config.GEMINI_MODELS

    @property
    def target_mmdd(self) -> str:
        return self._target_mmdd
        
    @target_mmdd.setter
    def target_mmdd(self, value: str):
        self._target_mmdd = value
        
    @property
    def is_force_rerun(self) -> bool:
        return self._is_force_rerun
        
    @is_force_rerun.setter
    def is_force_rerun(self, value: bool):
        self._is_force_rerun = value

    # ===========================
    # [상태 조회 (Queries)]
    # ===========================
    def get_combo_status(self, key_name: str, model_name: str) -> dict:
        """API 키와 모델 조합의 현재 상태 및 쿨타임 정보를 반환합니다."""
        api_mgr = AppContainer.get_instance().api_mgr
        status, extra = api_mgr.check_combo_status(key_name, model_name)
        
        if status == "COOLDOWN":
            total_cd = Config.MODEL_LOCK_DURATION_503 if extra > api_mgr.cooldown_seconds else api_mgr.cooldown_seconds
            return {"status": "COOLDOWN", "remaining_cd": extra, "total_cd": total_cd}
        elif status in ["READY", "BUSY", "DAILY"]:
            return {"status": status, "remaining_cd": 0.0, "total_cd": 0.0}
        else:
            return {"status": "READY", "remaining_cd": 0.0, "total_cd": 0.0}

    # ===========================
    # [명령 (Commands)]
    # ===========================
    def start_scan(self):
        worker = LLMScanWorker(self.is_force_rerun, self.target_mmdd)
        worker.finished_signal.connect(self._on_scan_ready)
        self.start_worker(worker)

    def _on_scan_ready(self, result):
        self.scan_results = result or []
        self.scan_completed.emit()

    def start_tasks(self, task_queue: list):
        grouped_tasks: dict[str, list] = {}
        for task in task_queue:
            b_name = task['base_name']
            if b_name not in grouped_tasks:
                grouped_tasks[b_name] = []
            grouped_tasks[b_name].append(task)
            
        workers = []
        for b_name, group in grouped_tasks.items():
            w = LLMTaskWorker(group)
            w.cell_update_signal.connect(self.cell_update_signal.emit)
            workers.append(w)
            
        self.start_batch_workers(workers, channel="llm")
        GlobalLogger.info(f"🚀 총 {len(workers)}개의 교시(병렬 파이프라인)를 백그라운드에서 동시 시작합니다...")

