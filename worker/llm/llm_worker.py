"""
LLM 백그라운드 작업 처리를 위한 워커 모듈입니다.

PyQt의 BaseWorker(QThread)를 상속받아, 비즈니스 로직(Service)의 실행을 백그라운드 스레드에 
위임하고 그 결과를 UI 시그널(cell_update_signal, progress_signal, log_signal 등)로 중계합니다.
"""
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker
from service.drive_sync_service import DriveSyncService
from service.ai_pipeline_service import AiPipelineService


class LLMScanWorker(BaseWorker):
    """구글 드라이브를 스캔하여 교시별 AI 파이프라인 작업 상태를 파악하는 워커.

    Attributes:
        is_force_rerun (bool): 강제 재실행 모드 활성화 여부.
        target_mmdd (str or None): 재실행 시 타겟팅할 특정 날짜(MMDD).
    """

    def __init__(self, is_force_rerun: bool = False, target_mmdd: Optional[str] = None):
        """LLMScanWorker 초기화.

        Args:
            is_force_rerun (bool): 특정 날짜로 강제로 재탐색할지 여부.
            target_mmdd (str, optional): MMDD 형태의 강제 대상 날짜.
        """
        super().__init__()
        self.is_force_rerun = is_force_rerun
        self.target_mmdd = target_mmdd

    def do_work(self) -> Optional[List[Dict[str, Any]]]:
        """구글 드라이브를 스캔하여 미완료 AI 파이프라인 작업 목록을 수집합니다."""
        self.log_signal.emit("구글 드라이브에서 실제 데이터를 스캔하는 중입니다. 잠시만 기다려주세요...")
        sync_service = DriveSyncService(logger_callback=self.log_signal.emit)

        # 1. 대상 날짜 필터를 적용하여 구글 드라이브 파일 목록 수집
        name_filter = self.target_mmdd if (self.is_force_rerun and self.target_mmdd) else None
        drive_files, drive_filenames, _ = sync_service.fetch_all_files(local_path="", name_filter=name_filter)

        # 2. 파일명 목록에서 고유 교시(Lesson ID) 추출 및 정렬
        all_lesson_ids = set()
        for fname in drive_filenames:
            lid = sync_service.naming_service.extract_lesson_id(fname)
            if lid:
                all_lesson_ids.add(lid)

        sorted_lessons = sorted(list(all_lesson_ids))
        total_lessons = len(sorted_lessons)
        real_data = []

        # 3. 각 교시별로 1단계(플래그 추출) 및 3단계(LLM UI 가공) 수행
        for i, lesson_id in enumerate(sorted_lessons):
            if self.is_cancelled():
                self.log_signal.emit("스캔 작업이 사용자에 의해 중단되었습니다.")
                break

            # 1단계: 순수 존재 유무 데이터 수집
            flags = sync_service.get_lesson_file_flags(lesson_id, drive_filenames)
            # 3단계: LLM용 가공 데이터 및 전체 완료 여부 판정
            data, is_all_completed = sync_service.format_llm_pipeline_data(lesson_id, flags)

            if self.is_force_rerun:
                if self.target_mmdd and not lesson_id.startswith(self.target_mmdd):
                    continue
            else:
                if is_all_completed:
                    continue

            real_data.append(data)
            if total_lessons > 0:
                self.progress_signal.emit(int(((i + 1) / total_lessons) * 100), "")

        return real_data


class LLMTaskWorker(BaseWorker):
    """지정된 교시 그룹의 AI 파이프라인(교정, 요약, Anki) 작업을 실행하는 백그라운드 워커."""

    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_queue: List[Dict[str, Any]]):
        """LLMTaskWorker 초기화.

        Args:
            task_queue (List[Dict[str, Any]]): 동일 교시(base_name)에 묶인 작업 명세 목록.
        """
        super().__init__()
        self.task_queue = task_queue

    def do_work(self) -> None:
        """AI 작업 파이프라인을 실행합니다.

        실제 파이프라인 오케스트레이션 및 Google Drive 연동은 AiPipelineService에 위임하며,
        워커는 UI 업데이트 시그널 및 진행 상태 중계만을 담당합니다.
        """
        if not self.task_queue:
            return

        base_name = self.task_queue[0]['base_name']
        pipeline_service = AiPipelineService(logger_callback=self.log_signal.emit)

        pipeline_service.run_pipeline_for_group(
            base_name=base_name,
            task_queue=self.task_queue,
            cell_update_callback=self.cell_update_signal.emit,
            cancel_checker=self.is_cancelled,
            progress_callback=self.progress_signal.emit
        )
