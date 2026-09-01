# Threads/drive_thread.py
from base.base_worker import BaseWorker
from service.drive_sync_service import DriveSyncService

class DriveSyncWorker(BaseWorker):
    """드라이브 동기화 및 상태 조회를 백그라운드에서 전담하는 스레드"""

    def __init__(self, search_mode: str, filter_value, local_path: str):
        super().__init__()
        self.search_mode = search_mode
        self.filter_value = filter_value
        self.local_path = local_path

    def do_work(self):
        # 1. 서비스 초기화 (인증 및 타겟 폴더 획득은 서비스 내부에서 처리)
        self.log_signal.emit("구글 드라이브 인증 및 폴더 정보를 가져오는 중입니다...")
        sync_service = DriveSyncService(logger_callback=self.log_signal.emit)

        # 2. 파일 전체 스캔
        self.log_signal.emit("로컬 및 드라이브의 파일 목록을 스캔하고 있습니다...")
        drive_files, drive_filenames, local_files = sync_service.fetch_all_files(self.local_path)
        
        # 🛑 스위치 확인
        if self.is_cancelled():
            return []

        # 3. 고유 교시(Lesson ID) 추출
        self.log_signal.emit("파일 데이터 분석 및 수업 교시를 추출하는 중...")
        combined_filenames = drive_filenames + local_files
        sorted_lessons = sync_service.extract_and_filter_lessons(
            combined_filenames, 
            self.search_mode, 
            self.filter_value
        )

        # 4. 테이블 렌더링용 데이터 조립
        table_data = []
        json_cache = {}
        total_lessons = len(sorted_lessons)
        
        for index, lesson_id in enumerate(sorted_lessons):
            # 🛑 루프 중간 취소 요청 확인
            if self.is_cancelled():
                self.log_signal.emit("작업이 사용자에 의해 중단되었습니다.")
                break
                
            # 📈 진행률 및 로그 업데이트
            self.log_signal.emit(f"[{index + 1}/{total_lessons}] 교시 데이터({lesson_id}) 상태 판별 중...")
            progress = int(((index + 1) / total_lessons) * 100)
            self.progress_signal.emit(progress, "상태 판별 중...")

            # 비즈니스 로직 위임 (상태 판별, "")
            lesson_data = sync_service.build_lesson_status_data(
                lesson_id, 
                drive_files, 
                drive_filenames, 
                json_cache
            )
            table_data.append(lesson_data)

        if not self.is_cancelled():
            self.log_signal.emit("✅ 모든 데이터 분석이 완료되었습니다.")
            
        return table_data