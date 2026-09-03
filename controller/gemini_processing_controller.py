"""Gemini LLM 기반 텍스트 처리 작업을 관리하는 컨트롤러 모듈입니다.

UI(Tab7GeminiProcessing)와 연동하여 LLM 스캔 및 단위 작업(Task) 워커들을 
생성하고 실행하며, 결과를 시그널을 통해 UI에 반영합니다.
"""
from PyQt6.QtCore import pyqtSignal
from base.base_controller import BaseController
from worker.llm.llm_worker import LLMTaskWorker, LLMScanWorker

class GeminiProcessingController(BaseController):
    """Gemini LLM 작업들의 실행 및 상태 관리를 담당하는 컨트롤러 클래스입니다.

    BaseController를 상속받으며, 한 번에 여러 개의 LLM 워커들을 큐에 등록하여
    일괄 처리할 수 있도록 지원합니다.

    Attributes:
        scan_completed (pyqtSignal): LLM 대상 파일 스캔 결과를 전달하는 시그널.
        cell_update_signal (pyqtSignal): 개별 작업 진행 중 UI의 특정 셀을 업데이트하기 위한 시그널.
    """
    
    # ===========================
    # [시그널 정의]
    # ===========================
    scan_completed = pyqtSignal(list, bool)
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_manager=None):
        # BaseController의 초기화 로직 실행
        super().__init__(task_manager)
        # UI 관련 변수 초기화
        self.ui = None

    # ===========================
    # [스캔 작업 관리]
    # ===========================
    def start_scan(self, is_force_rerun=False, target_mmdd=None):
        """LLM 처리가 필요한 대상 파일을 탐색하는 스캔 워커를 실행합니다.

        전체 데이터 중 아직 처리되지 않았거나 재실행이 필요한 항목들을 파악하기 위해 호출됩니다.

        Args:
            is_force_rerun (bool, optional): 이미 완료된 작업도 강제로 다시 스캔할지 여부. 기본값은 False.
            target_mmdd (str, optional): 특정 날짜(MMDD 형식) 대상만 스캔할 경우 지정합니다.

        Returns:
            None
        """
        # 지정된 조건으로 LLM 스캔 워커 객체 생성
        worker = LLMScanWorker(is_force_rerun, target_mmdd)
        # 스캔 완료 시 결과를 컨트롤러의 시그널로 전달하도록 연결
        worker.finished_signal.connect(lambda result: self.scan_completed.emit(result, is_force_rerun))
        # 생성된 스캔 워커를 실행
        self.start_worker(worker)

    # ===========================
    # [작업 큐 일괄 실행]
    # ===========================
    def start_tasks(self, task_queue: list):
        """전달받은 작업 목록을 base_name(수업 교시)별로 그룹화하여, 각 그룹을 병렬(멀티스레드)로 실행합니다."""
        if not self.task_manager:
            self.log_signal.emit("⚠️ TaskManager가 설정되지 않아 다중 작업을 실행할 수 없습니다.")
            return

        # base_name 기준으로 작업 분류
        grouped_tasks = {}
        for task in task_queue:
            b_name = task['base_name']
            if b_name not in grouped_tasks:
                grouped_tasks[b_name] = []
            grouped_tasks[b_name].append(task)
            
        workers = []
        for b_name, group in grouped_tasks.items():
            # 각 base_name 별로 하나의 워커 생성 (동일 교시 내에서는 교정 -> 요약, Anki 순차 실행 보장)
            w = LLMTaskWorker(group)
            w.cell_update_signal.connect(self.cell_update_signal.emit)
            workers.append(w)
            
        self.start_batch_workers(workers, channel="llm")
        self.log_signal.emit(f"🚀 총 {len(workers)}개의 교시(병렬 파이프라인)를 백그라운드에서 동시 시작합니다...")

