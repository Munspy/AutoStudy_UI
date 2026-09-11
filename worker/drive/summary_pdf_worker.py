from utils.constants import FileSuffix, Extensions
import os
import tempfile

import pymupdf

from core.logger import GlobalLogger
from base.base_worker import BaseWorker
from core.container import AppContainer
from utils.auth_util import get_drive_service
from utils.drive_api import in_memory_download_from_drive


class SummaryPdfDownloadWorker(BaseWorker):
    """체크된 수업들의 _요약본.txt 파일을 읽어 요약 PDF 커버를 생성한 뒤 하나로 병합하여 로컬에 저장합니다."""
    def __init__(self, checked_lessons: list[str], output_path: str):
        super().__init__()
        self.checked_lessons = checked_lessons
        self.output_path = output_path

    def do_work(self):
        if not self.checked_lessons:
            self.error_signal.emit("선택된 수업이 없습니다.")
            return None

        GlobalLogger.info(f"🚀 총 {len(self.checked_lessons)}개 선택된 수업의 요약본 PDF 다운로드 및 병합 작업을 시작합니다...")
        

        sync_service = AppContainer.get_instance().drive_sync
        drive_service = get_drive_service()
        summary_service = AppContainer.get_instance().summary_pdf

        # 1. Google Drive 파일 스캔
        GlobalLogger.info("☁️ 구글 드라이브 파일 목록을 조회하는 중...")
        drive_files, drive_filenames, _ = sync_service.fetch_all_files("")
        
        if self.is_cancelled():
            return None

        sorted_lessons = sorted(self.checked_lessons)
        
        merged_doc = pymupdf.Document()
        docs_to_close = []
        temp_files = []

        try:
            for lesson in sorted_lessons:
                if self.is_cancelled():
                    GlobalLogger.info("요약본 병합 작업이 취소되었습니다.")
                    break
                    
                GlobalLogger.info(f"[{lesson}] 데이터 탐색 중...")
                
                # 해당 교시의 파일 필터링
                summary_file = next((f for f in drive_files if f['name'].startswith(lesson) and f['name'].endswith(f'_{FileSuffix.SUMMARY_TXT}.txt')), None)
                orig_pdf_file = next((f for f in drive_files if f['name'].startswith(lesson) and f['name'].endswith('.pdf') and not f['name'].endswith(f'_{FileSuffix.SCRIPTED}{Extensions.PDF}')), None)

                if not summary_file:
                    GlobalLogger.info(f"   ⚠️ [{lesson}] '_요약본.txt' 파일을 찾을 수 없습니다. 건너뜁니다.")
                    continue
                if not orig_pdf_file:
                    GlobalLogger.info(f"   ⚠️ [{lesson}] 원본 PDF 파일을 찾을 수 없습니다(썸네일 렌더링 불가). 건너뜁니다.")
                    continue

                GlobalLogger.info(f"   ➔ 요약본 다운로드 및 커버 PDF 렌더링 중...")
                
                summary_text = ""
                with in_memory_download_from_drive(summary_file['id'], drive_service=drive_service) as io_stream:
                    summary_text = io_stream.getvalue().decode('utf-8', errors='ignore')

                temp_orig_pdf_path = ""
                with in_memory_download_from_drive(orig_pdf_file['id'], drive_service=drive_service) as pdf_io:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_orig:
                        temp_orig.write(pdf_io.getvalue())
                        temp_orig_pdf_path = temp_orig.name
                        temp_files.append(temp_orig_pdf_path)

                if self.is_cancelled():
                    break

                try:
                    summary_doc = summary_service.create_summary_cover_pdf(
                        base_name=lesson,
                        summary_text=summary_text,
                        temp_orig_pdf_path=temp_orig_pdf_path,
                        drive_service=drive_service
                    )
                    
                    merged_doc.insert_pdf(summary_doc)
                    docs_to_close.append(summary_doc)
                except Exception as e:
                    GlobalLogger.info(f"   ❌ [{lesson}] 커버 렌더링 실패: {e}")

            if self.is_cancelled():
                return None

            if len(merged_doc) > 0:
                GlobalLogger.info(f"💾 병합 완료. 로컬에 저장합니다: {self.output_path}")
                merged_doc.save(self.output_path, garbage=4, deflate=True)
                return "요약본 PDF 병합 및 저장이 완료되었습니다."
            else:
                self.error_signal.emit("병합할 요약본 데이터가 없습니다.")
                return None
        finally:
            merged_doc.close()
            for doc in docs_to_close:
                if not doc.is_closed:
                    doc.close()
            for tf in temp_files:
                if os.path.exists(tf):
                    try:
                        os.unlink(tf)
                    except:
                        pass

