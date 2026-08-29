# controller/gemini_processing_controller.py
from PyQt6.QtCore import QThread, pyqtSignal

# 1. 비즈니스 로직을 전담하는 도메인 서비스 임포트
from service.llm_service import LlmService
from service.pipeline_status_service import PipelineStatusService
from service.file_naming_service import FileNamingService

# 2. 범용 유틸리티 임포트
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.filename_util import normalize_text

from utils.config import Config

# 서비스 인스턴스화 (UI와 연결하기 위한 중재자 역할)
_llm_service = LlmService()
_pipeline_service = PipelineStatusService()
_naming_service = FileNamingService()

def fetch_gemini_tasks_from_drive(is_force_rerun=False, target_mmdd=None):
    """
    [컨트롤러 래퍼] UI에서 스캔 요청이 오면 PipelineStatusService를 활용해 상태를 판별하여 반환합니다.
    """
    drive_service = get_drive_service()
    root_folder_id = Config.TARGET_DRIVE_DIR
    
    # 1. 대상 폴더 파일 스캔
    name_filter = target_mmdd if (is_force_rerun and target_mmdd) else None
    drive_files = get_all_drive_files(root_folder_id, name_filter=name_filter, drive_service=drive_service)
    drive_file_names = [normalize_text(f.get('name', '')) for f in drive_files]
    
    # 2. 교시 아이디(Lesson ID) 추출
    all_lesson_ids = set()
    for fname in drive_file_names:
        lid = _naming_service.extract_lesson_id(fname)
        if lid:
            all_lesson_ids.add(lid)
            
    all_lesson_ids = sorted(list(all_lesson_ids))
    real_data = []
    
    # 파이프라인 서비스에 API 통신 객체 주입
    _pipeline_service.drive_service = drive_service
    
    # 3. 각 교시별 상태 평가 위임 (PipelineStatusService 활용)
    for lesson_id in all_lesson_ids:
        has_final_pdf = _pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "final_pdf")
        has_script_txt = _pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "script")
        anki_done = _pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "anki")
        
        has_corrected, has_summary = _pipeline_service.get_ai_task_status_from_json(drive_files, lesson_id)
        
        is_all_completed = has_final_pdf and has_script_txt and has_corrected and has_summary and anki_done
        
        # 필터링 로직
        if is_force_rerun:
            if target_mmdd and not lesson_id.startswith(target_mmdd):
                continue
        else:
            if is_all_completed:
                continue
        
        real_data.append({
            "교시": lesson_id,
            "강의록": has_final_pdf,
            "음성스크립트": has_script_txt,
            "교정": "완료" if has_corrected else "미완료",
            "요약": "완료" if has_summary else "미완료",
            "Anki": "완료" if anki_done else "미완료"
        })
        
    return real_data


class GeminiTaskWorker(QThread):
    """
    UI의 멈춤을 방지하며 백그라운드에서 LLM 작업을 큐(Queue) 순서대로 처리하는 스레드입니다.
    실제 데이터 조작은 _llm_service가 담당합니다.
    """
    log_signal = pyqtSignal(str)
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_queue):
        super().__init__()
        self.task_queue = task_queue

    def run(self):
        for task in self.task_queue:
            row = task['row']
            col = task['col']
            task_type = task['task_type']
            model_name = task['model']
            base_name = task['base_name']
            
            # TODO: 실제 환경에서는 파일을 읽어와 텍스트를 주입합니다.
            dummy_audio = f"[{base_name}] 로드된 음성 텍스트"
            dummy_pdf = f"[{base_name}] 로드된 강의록 텍스트"
            
            try:
                if task_type == "교정":
                    result = _llm_service.correct_script_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "요약":
                    result = _llm_service.key_summary_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "Anki":
                    # generate_anki_csv_text로 교정
                    result = _llm_service.generate_anki_csv_text(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                else:
                    result = False
                
                # 결과에 따라 UI 테이블 상태 업데이트 시그널 전송
                if result:
                    self.cell_update_signal.emit(row, col, "DONE")
                else:
                    self.cell_update_signal.emit(row, col, "ERROR")
                    
            except Exception as e:
                self.log_signal.emit(f"❌ {task_type} 워커 오류: {str(e)}")
                self.cell_update_signal.emit(row, col, "ERROR")