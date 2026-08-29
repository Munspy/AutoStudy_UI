# Threads/llm_thread.py
from PyQt6.QtCore import pyqtSignal
from base.base_worker import BaseWorker

# 분리해둔 utils 공구함들
from utils.llm_client import correct_script_with_gemini, key_summary_with_gemini
from service.anki_service import create_anki_package

class LLMTaskThread(BaseWorker):
    """
    Gemini API를 이용한 교정, 요약 및 Anki 생성을 일괄 처리하는 스레드.
    BaseWorker를 상속받아 에러 발생 시 앱 튕김 현상을 자동으로 방어합니다.
    """
    # 개별 작업이 끝날 때마다 UI(테이블)의 특정 셀을 업데이트하기 위한 전용 시그널
    cell_update_signal = pyqtSignal(int, int, str)

    def __init__(self, task_queue: list):
        super().__init__()
        self.task_queue = task_queue

    def do_work(self):
        completed_count = 0
        total_tasks = len(self.task_queue)
        
        self.log_signal.emit(f"🚀 총 {total_tasks}개의 AI 작업을 백그라운드에서 시작합니다...")
        
        for index, task in enumerate(self.task_queue):
            # 🛑 스위치 확인 (UI에서 중단 요청 시 즉시 루프 탈출)
            if not self._is_running:
                self.log_signal.emit("⚠️ 사용자에 의해 AI 작업이 중단되었습니다.")
                break
                
            row, col = task['row'], task['col']
            task_type, base_name = task['task_type'], task['base_name']
            model_name = task['model']
            
            self.log_signal.emit(f"⏳ [{index+1}/{total_tasks}] [AI 작업 시작] {base_name} - {task_type}")
            
            # 📈 전체 프로그레스 바 업데이트
            progress = int((index / total_tasks) * 100)
            self.progress_signal.emit(progress, f"{base_name} {task_type} 처리 중...")
            
            try:
                # TODO: 실제 환경에서는 파일을 읽어와 텍스트를 주입합니다.
                dummy_audio = f"[{base_name}] 로드된 음성 텍스트"
                dummy_pdf = f"[{base_name}] 로드된 강의록 텍스트"
                
                # utils의 도구들을 호출하여 작업 수행
                if task_type == "교정":
                    result = correct_script_with_gemini(dummy_audio, dummy_pdf, model_name)
                    # 파일 저장 로직은 utils.local_file_manage 등을 활용
                    
                elif task_type == "요약":
                    result = key_summary_with_gemini(dummy_audio, dummy_pdf, model_name)
                    
                elif task_type == "Anki":
                    # Anki 생성 로직 (llm_manage.py에 프롬프트를 빼두고 호출)
                    # raw_csv = generate_anki_csv_text(...) 
                    # ???
                    result = True
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
                # 개별 API 호출 에러 방어: 다음 작업(Task)을 멈추지 않고 계속 진행하도록 개별 예외 처리
                self.log_signal.emit(f"⚠️ [{index+1}/{total_tasks}] [AI 예외 발생] {base_name}: {str(e)}")
                self.cell_update_signal.emit(row, col, "ERROR")
                
        # 100% 진행률 전송
        if self._is_running:
            self.progress_signal.emit(100, "모든 작업 완료")
            self.log_signal.emit("🎉 대기열의 모든 AI 작업이 종료되었습니다.")
            
        return f"총 {total_tasks}개 작업 중 {completed_count}개 성공"