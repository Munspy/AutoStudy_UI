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
    def __init__(self, is_force_rerun=False, target_mmdd=None):
        super().__init__()
        self.is_force_rerun = is_force_rerun
        self.target_mmdd = target_mmdd

    def do_work(self):
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
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_queue: list):
        super().__init__()
        self.task_queue = task_queue

    def do_work(self):
        llm_service = LlmService(logger_callback=self.log_signal.emit)
        completed_count = 0
        total_tasks = len(self.task_queue)
        
        self.log_signal.emit(f"🚀 총 {total_tasks}개의 AI 작업을 백그라운드에서 시작합니다...")
        
        for index, task in enumerate(self.task_queue):
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
                dummy_audio = f"[{base_name}] 로드된 음성 텍스트"
                dummy_pdf = f"[{base_name}] 로드된 강의록 텍스트"
                
                if task_type == "교정":
                    result = llm_service.correct_script_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "요약":
                    result = llm_service.key_summary_with_gemini(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                elif task_type == "Anki":
                    result = llm_service.generate_anki_csv_text(dummy_audio, dummy_pdf, model_name, logger_callback=self.log_signal.emit)
                else:
                    result = False
                
                if result:
                    self.log_signal.emit(f"✅ [{index+1}/{total_tasks}] [AI 작업 완료] {base_name} - {task_type}")
                    self.cell_update_signal.emit(row, col, "DONE")
                    completed_count += 1
                else:
                    self.log_signal.emit(f"❌ [{index+1}/{total_tasks}] [AI 작업 실패] {base_name} - {task_type} (결과물 없음)")
                    self.cell_update_signal.emit(row, col, "ERROR")
                    
            except Exception as e:
                self.log_signal.emit(f"⚠️ [{index+1}/{total_tasks}] [AI 예외 발생] {base_name}: {str(e)}")
                self.cell_update_signal.emit(row, col, "ERROR")
                
        if not self.is_cancelled():
            self.progress_signal.emit(100, "")
            self.log_signal.emit("🎉 대기열의 모든 AI 작업이 종료되었습니다.")
            
        return f"총 {total_tasks}개 작업 중 {completed_count}개 성공"
