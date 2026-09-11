import tempfile
from pathlib import Path

from core.logger import GlobalLogger
from base.base_worker import BaseWorker
from core.container import AppContainer
from utils.drive_api import download_from_drive


class ScriptedPdfMergeWorker(BaseWorker):
    """체크된 수업(Lesson)들의 _scripted.pdf 파일을 Google Drive에서 다운로드하고,
    강의 순서대로 목차(TOC)를 삽입하여 병합 PDF를 생성하는 워커 클래스.
    """
    def __init__(self, checked_lessons: list[str], output_path: str):
        super().__init__()
        self.checked_lessons = checked_lessons
        self.output_path = output_path

    def do_work(self):
        if not self.checked_lessons:
            self.error_signal.emit("선택된 수업이 없습니다.")
            return None

        GlobalLogger.info(f"🚀 총 {len(self.checked_lessons)}개 선택된 수업의 스크립트 합본 다운로드 및 병합 작업을 시작합니다...")
        
        sync_service = AppContainer.get_instance().drive_sync
        naming_service = AppContainer.get_instance().file_naming
        pdf_service = AppContainer.get_instance().pdf_operation

        # 1. Google Drive 파일 스캔
        GlobalLogger.info("☁️ 구글 드라이브 파일 목록을 조회하는 중...")
        drive_files, drive_filenames, _ = sync_service.fetch_all_files("")
        
        if self.is_cancelled():
            return None

        # 2. 체크된 수업들의 _scripted.pdf 메타데이터 매핑 (강의 순서 오름차순 정렬)
        sorted_lessons = sorted(self.checked_lessons)
        
        lesson_file_map = {}
        for f in drive_files:
            fname = f.get('name', '')
            if 'scripted.pdf' in fname.lower():
                lid = naming_service.extract_lesson_id(fname)
                if lid:
                    lesson_file_map[lid] = f

        # 3. 임시 폴더에 다운로드
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_entries = []  # (lesson_id, local_pdf_path)
            
            total = len(sorted_lessons)
            for idx, lesson_id in enumerate(sorted_lessons, 1):
                if self.is_cancelled():
                    GlobalLogger.info("작업이 사용자에 의해 중단되었습니다.")
                    return None

                file_info = lesson_file_map.get(lesson_id)
                if not file_info:
                    GlobalLogger.info(f"⚠️ [{lesson_id}] _scripted.pdf 파일이 구글 드라이브에 존재하지 않아 건너뜁니다.")
                    continue

                local_file = temp_path / f"{lesson_id}_scripted.pdf"
                GlobalLogger.info(f"📥 [{idx}/{total}] [{lesson_id}] _scripted.pdf 다운로드 중...")
                self.progress_signal.emit(int((idx / total) * 80), f"[{lesson_id}] 다운로드 중...")
                
                try:
                    download_from_drive(file_info['id'], str(local_file), drive_service=sync_service.drive_service)
                    # timetable 기반 목차(TOC) 제목 설정
                    tt_info = sync_service.timetable_service.find_timetable_info_for_lesson(lesson_id)
                    prof = tt_info.get("professor", "").strip() if tt_info else ""
                    lec = tt_info.get("lecture_name", "").strip() if tt_info else ""
                    if prof and lec:
                        toc_title = f"{lesson_id} {prof} - {lec}"
                    else:
                        toc_title = lesson_id
                    pdf_entries.append((toc_title, local_file))
                except Exception as e:
                    GlobalLogger.info(f"❌ [{lesson_id}] 다운로드 실패: {str(e)}")

            if not pdf_entries:
                msg = "❌ 병합 가능한 _scripted.pdf 파일을 찾을 수 없거나 다운로드에 실패했습니다."
                self.error_signal.emit(msg)
                return None

            # 4. 목차가 포함된 PDF 병합 생성
            GlobalLogger.info(f"🔗 {len(pdf_entries)}개 수업 PDF를 목차(TOC)와 함께 강의 순서대로 병합하는 중...")
            self.progress_signal.emit(90, "PDF 병합 및 목차 생성 중...")
            
            success, msg = pdf_service.merge_scripted_pdfs_and_save(pdf_entries=pdf_entries, output_path=self.output_path, cancel_checker=self.is_cancelled)
            if not success:
                self.error_signal.emit(msg)
                return None

            self.progress_signal.emit(100, "완료")
            GlobalLogger.info(f"🎉 스크립트 합본 다운로드 및 병합 완료! (저장 위치: {self.output_path})")
            return msg

