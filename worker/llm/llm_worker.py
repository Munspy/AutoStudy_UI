"""
LLM 백그라운드 작업 처리를 위한 워커 모듈입니다.

구글 드라이브의 파일 상태를 스캔하여 AI 처리 파이프라인의 진행 상태를 점검하는
`LLMScanWorker`와, 큐에 등록된 AI 처리 작업을 백그라운드에서 순차적으로 실행하는
`LLMTaskWorker`를 제공합니다.
"""
from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker

from service.llm_service import LlmService
from service.pipeline_status_service import PipelineStatusService
from service.file_naming_service import FileNamingService
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files
from utils.filename_util import normalize_text
from utils.config import Config



class LLMScanWorker(BaseWorker):
    """구글 드라이브를 스캔하여 교시별 AI 파이프라인 작업 상태를 파악하는 워커.
    
    Attributes:
        is_force_rerun (bool): 강제 재실행 모드 활성화 여부.
        target_mmdd (str or None): 재실행 시 타겟팅할 특정 날짜(MMDD).
    """
    def __init__(self, is_force_rerun=False, target_mmdd=None):
        """LLMScanWorker 초기화.
        
        Args:
            is_force_rerun (bool): 특정 날짜로 강제로 재탐색할지 여부.
            target_mmdd (str, optional): MMDD 형태의 강제 대상 날짜.
        """
        super().__init__()
        self.is_force_rerun = is_force_rerun
        self.target_mmdd = target_mmdd

    def do_work(self):
        """드라이브의 상태를 스캔하여 파이프라인 처리 정보를 반환합니다.
        
        드라이브에서 모든 파일을 가져온 후, 교시(Lesson ID)별로 
        최종 PDF, 스크립트 텍스트, AI 교정, 요약, Anki 파일의 생성 여부를 점검합니다.
        
        Returns:
            list: 각 교시별 파이프라인 완료 상태(dict)를 담은 리스트.
        """
        pipeline_service = PipelineStatusService(logger_callback=self.log_signal.emit)
        naming_service = FileNamingService(logger_callback=self.log_signal.emit)

        self.log_signal.emit("구글 드라이브에서 실제 데이터를 스캔하는 중입니다. 잠시만 기다려주세요...")
        drive_service = get_drive_service()
        root_folder_id = Config.TARGET_DRIVE_DIR
        
        name_filter = self.target_mmdd if (self.is_force_rerun and self.target_mmdd) else None
        drive_files = get_all_drive_files(root_folder_id, name_filter=name_filter, drive_service=drive_service)
        drive_file_names = [normalize_text(f.get('name', '')) for f in drive_files]
        
        all_lesson_ids = set()
        for fname in drive_file_names:
            lid = naming_service.extract_lesson_id(fname)
            if lid:
                all_lesson_ids.add(lid)
                
        all_lesson_ids = sorted(list(all_lesson_ids))
        real_data = []
        
        pipeline_service.drive_service = drive_service
        
        total = len(all_lesson_ids)
        for i, lesson_id in enumerate(all_lesson_ids):
            if self.is_cancelled():
                break
            
            has_final_pdf = pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "final_pdf")
            has_script_txt = pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "script")
            anki_done = pipeline_service.check_lesson_file_status(drive_file_names, lesson_id, "anki")
            
            has_corrected, has_summary = pipeline_service.get_ai_task_status_from_json(drive_files, lesson_id)
            
            is_all_completed = has_final_pdf and has_script_txt and has_corrected and has_summary and anki_done
            
            if self.is_force_rerun:
                if self.target_mmdd and not lesson_id.startswith(self.target_mmdd):
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
            self.progress_signal.emit(int(((i+1)/total)*100), "")
            
        return real_data


class LLMTaskWorker(BaseWorker):
    """지정된 AI 작업을 순차적으로 백그라운드 처리하는 워커 클래스.
    
    큐 형태로 저장된 여러 AI 작업(교정, 요약, Anki 생성 등)을 
    하나씩 LlmService를 통해 처리하고, 상태를 UI 시그널로 보고합니다.
    
    Attributes:
        task_queue (list): 수행해야 할 AI 작업 목록 데이터.
    """
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_queue: list):
        """LLMTaskWorker 초기화.
        
        Args:
            task_queue (list): AI 처리가 필요한 작업 딕셔너리 리스트.
        """
        super().__init__()
        self.task_queue = task_queue

    def do_work(self):
        """태스크 큐에 있는 모든 AI 작업을 순차적으로 실행합니다.
        
        Returns:
            str: 처리된 총 작업 수 및 성공 개수를 담은 결과 문자열.
        """
        # ===========================
        # [작업 초기화]
        # ===========================
        # LLM 서비스를 초기화하고 처리 카운터를 설정합니다.
        llm_service = LlmService(logger_callback=self.log_signal.emit)
        completed_count = 0
        total_tasks = len(self.task_queue)
        
        self.log_signal.emit(f"🚀 총 {total_tasks}개의 AI 작업을 백그라운드에서 시작합니다...")
        
        # ===========================
        # [AI 작업 순차 처리]
        # ===========================
        for index, task in enumerate(self.task_queue):
            # 사용자에 의한 취소 요청이 있는지 확인합니다.
            if self.is_cancelled():
                self.log_signal.emit("⚠️ 사용자에 의해 AI 작업이 중단되었습니다.")
                break
                
            row, col = task['row'], task['col']
            task_type, base_name = task['task_type'], task['base_name']
            model_name = task['model']
            
            self.log_signal.emit(f"⏳ [{index+1}/{total_tasks}] [AI 작업 시작] {base_name} - {task_type}")
            
            # 📈 전체 프로그레스 바 업데이트
            progress = int((index / total_tasks) * 100)
            self.progress_signal.emit(progress, "")
            
            try:
                # ===========================
                # [AI 모델 호출 및 결과 처리]
                # ===========================
                # 더미 데이터를 설정합니다.
                dummy_audio = f"[{base_name}] 로드된 음성 텍스트"
                dummy_pdf = f"[{base_name}] 로드된 강의록 텍스트"
                
                # 작업 타입에 따라 적절한 LLM 서비스 메서드를 호출합니다.
                if task_type == "교정":
                    result = llm_service.correct_script_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "요약":
                    result = llm_service.key_summary_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "Anki":
                    result = llm_service.generate_anki_csv_text(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                else:
                    result = False
                
                # 결과 여부에 따라 성공 또는 실패 시그널을 방출합니다.
                if result:
                    self.log_signal.emit(f"✅ [{index+1}/{total_tasks}] [AI 작업 완료] {base_name} - {task_type}")
                    self.cell_update_signal.emit(row, col, "DONE")
                    completed_count += 1
                else:
                    self.log_signal.emit(f"❌ [{index+1}/{total_tasks}] [AI 작업 실패] {base_name} - {task_type} (결과물 없음)")
                    self.cell_update_signal.emit(row, col, "ERROR")
                    
            except Exception as e:
                # 예외 발생 시 에러 시그널을 방출합니다.
                self.log_signal.emit(f"⚠️ [{index+1}/{total_tasks}] [AI 예외 발생] {base_name}: {str(e)}")
                self.cell_update_signal.emit(row, col, "ERROR")
                
        # 취소되지 않았다면 최종 완료 메시지를 출력합니다.
        if not self.is_cancelled():
            self.progress_signal.emit(100, "")
            self.log_signal.emit("🎉 대기열의 모든 AI 작업이 종료되었습니다.")
            
        return f"총 {total_tasks}개 작업 중 {completed_count}개 성공"
