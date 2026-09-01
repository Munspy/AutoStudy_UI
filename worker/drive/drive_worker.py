"""
드라이브 동기화 작업을 수행하는 워커 모듈입니다.

이 모듈은 구글 드라이브와 로컬 파일 간의 동기화 상태를 확인하고
수업 교시별 파일 상태를 조회하는 `DriveSyncWorker` 클래스를 포함합니다.
주로 `controller.drive_sync_controller`에서 호출되어 백그라운드 작업을 담당합니다.
"""
# Threads/drive_thread.py
from base.base_worker import BaseWorker
from service.drive_sync_service import DriveSyncService

class DriveSyncWorker(BaseWorker):
    """드라이브 동기화 및 상태 조회를 백그라운드에서 전담하는 스레드.
    
    Attributes:
        search_mode (str): 검색 모드 (예: 'ALL', 'DATE').
        filter_value (str): 필터링할 값 (예: 특정 날짜나 검색어).
        local_path (str): 로컬 파일 경로.
    """

    def __init__(self, search_mode: str, filter_value, local_path: str):
        """DriveSyncWorker 초기화.

        Args:
            search_mode (str): 파일 검색 모드.
            filter_value (str): 검색 시 사용할 필터 값.
            local_path (str): 로컬 대상 디렉토리 경로.
        """
        super().__init__()
        self.search_mode = search_mode
        self.filter_value = filter_value
        self.local_path = local_path

    def do_work(self):
        """백그라운드에서 구글 드라이브와 로컬 파일의 상태를 분석하여 반환합니다.

        구글 드라이브 API를 통해 파일 목록을 가져오고, 로컬 파일과 비교하여
        수업(교시) 별 파일 존재 여부 및 동기화 상태를 분석합니다. 이 작업은 
        메인 UI 블로킹을 방지하기 위해 백그라운드에서 실행됩니다.

        Returns:
            list: 교시별 상태 데이터를 담은 딕셔너리 리스트. 취소된 경우 빈 리스트 반환.
        """
        # ===========================
        # [서비스 초기화]
        # ===========================
        # 1. 서비스 초기화 (인증 및 타겟 폴더 획득은 서비스 내부에서 처리)
        self.log_signal.emit("구글 드라이브 인증 및 폴더 정보를 가져오는 중입니다...")
        sync_service = DriveSyncService(logger_callback=self.log_signal.emit)

        # ===========================
        # [파일 스캔 및 취소 확인]
        # ===========================
        # 2. 파일 전체 스캔
        self.log_signal.emit("로컬 및 드라이브의 파일 목록을 스캔하고 있습니다...")
        
        target_folder = sync_service.target_folder_id
        if self.search_mode == "EXAM" and self.filter_value:
            target_folder = self.filter_value

        # 로컬 경로와 드라이브를 스캔하여 파일 리스트를 가져옵니다.
        drive_files, drive_filenames, local_files = sync_service.fetch_all_files(
            self.local_path,
            target_folder_id=target_folder
        )
        
        # 🛑 스위치 확인
        # 작업이 취소되었는지 확인합니다.
        if self.is_cancelled():
            return []

        # ===========================
        # [교시 데이터 추출]
        # ===========================
        # 3. 고유 교시(Lesson ID) 추출
        self.log_signal.emit("파일 데이터 분석 및 수업 교시를 추출하는 중...")
        # 시험 기준 검색 시 해당 드라이브 폴더의 파일들만 기준으로 교시 추출
        if self.search_mode == "EXAM":
            source_filenames = drive_filenames
        else:
            source_filenames = drive_filenames + local_files

        # 정렬된 교시 리스트를 추출합니다.
        sorted_lessons = sync_service.extract_and_filter_lessons(
            source_filenames, 
            self.search_mode, 
            self.filter_value
        )

        # ===========================
        # [테이블 렌더링용 데이터 조립]
        # ===========================
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

            # 비즈니스 로직 위임
            lesson_data = sync_service.build_lesson_status_data(
                lesson_id, 
                drive_files, 
                drive_filenames, 
                json_cache
            )
            table_data.append(lesson_data)

        # 취소되지 않았다면 완료 메시지를 출력합니다.
        if not self.is_cancelled():
            self.log_signal.emit("✅ 모든 데이터 분석이 완료되었습니다.")
            
        return table_data


class ExamCategoryFetchWorker(BaseWorker):
    """구글 드라이브의 2연속 폴더 구조를 분석하여 시험 기준 목록을 가져오는 워커."""
    
    def __init__(self, force_refresh: bool = False):
        super().__init__()
        self.force_refresh = force_refresh
        
    def do_work(self):
        self.log_signal.emit("구글 드라이브에서 시험 기준(과목/차수) 폴더 목록을 조회합니다...")
        sync_service = DriveSyncService(logger_callback=self.log_signal.emit)
        if self.is_cancelled():
            return []
        categories = sync_service.fetch_exam_categories(force_refresh=self.force_refresh)
        return categories