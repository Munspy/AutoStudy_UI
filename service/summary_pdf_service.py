import os
import re
import unicodedata
import pymupdf
import tempfile
from typing import Optional, Callable

from base.base_service import BaseService
from service.pdf_render_service import PdfRenderService
from service.youtube_playlist_service import YoutubePlaylistService
from service.timetable_service import TimetableService
from utils.config import Config
from utils.drive_api import in_memory_download_from_drive, upload_to_drive
from utils.text_util import parse_slide_text

MAC_FONT_PATH = Config.SUMMARY_FONT_PATH

class SummaryPdfService(BaseService):
    """요약본과 원본 슬라이드 및 스크립트를 결합한 _scripted.pdf 생성을 전담하는 서비스."""

    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        self.playlist_cache = {}
        self.pdf_renderer = PdfRenderService(logger_callback=logger_callback)
        self.yt_service = YoutubePlaylistService(logger_callback=logger_callback)
        self.timetable_service = TimetableService(logger_callback=logger_callback)




    def generate_and_upload_scripted_pdf(
        self, 
        base_name: str, 
        summary_text: Optional[str], 
        corrected_text: str, 
        target_folder_id: str, 
        drive_service
    ) -> bool:
        self._log(f"📄 [{base_name}] _scripted.pdf 생성 시작...")
        
        # 1. 대상 폴더에서 파일 목록 조회
        query = f"'{target_folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files_in_dir = {f['name']: f['id'] for f in results.get('files', [])}
        
        # [필수 재료 1: 원본 슬라이드 PDF] 원본 슬라이드가 없으면 생성하지 않음
        pdf_name = next(
            (name for name in files_in_dir.keys() if name.endswith(".pdf") and base_name in name and "scripted" not in name.lower()), 
            None
        )
        if not pdf_name:
            self._log(f"   ⚠️ [{base_name}] 원본 슬라이드 PDF가 없어 _scripted.pdf 생성을 건너뜁니다.")
            return False

        # [필수 재료 2: 최종교정본] 최종교정본 텍스트가 없으면 생성하지 않음
        if not corrected_text or not str(corrected_text).strip():
            self._log(f"   ⚠️ [{base_name}] 최종교정본 텍스트가 없어 _scripted.pdf 생성을 건너뜁니다.")
            return False

        # 최종교정본 스크립트를 슬라이드별로 파싱
        slides_data_dict = parse_slide_text(corrected_text)
        if not slides_data_dict:
            self._log(f"   ⚠️ [{base_name}] 최종교정본의 슬라이드 데이터([Slide XX])를 찾을 수 없어 _scripted.pdf 생성을 건너뜁니다.")
            return False

        temp_orig_pdf_path = None
        slides_pdf_path = None
        temp_pdf_path = None
        summary_doc = None

        try:
            # 원본 강의록 다운로드
            with in_memory_download_from_drive(files_in_dir[pdf_name], drive_service=drive_service) as orig_pdf_io:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_orig:
                    temp_orig.write(orig_pdf_io.getvalue())
                    temp_orig_pdf_path = temp_orig.name

            # 슬라이드-스크립트 PDF 생성 (상단 슬라이드, 하단 스크립트)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_slides:
                slides_pdf_path = temp_slides.name

            self._log(f"   ➔ 🛠️ 표준 슬라이드-스크립트 병합본 렌더링 중...")
            self.pdf_renderer.create_slide_script_pdf(temp_orig_pdf_path, slides_data_dict, slides_pdf_path)

            has_summary = bool(summary_text and str(summary_text).strip())

            if has_summary:
                self._log(f"   ➔ 📝 요약본 텍스트 포함: 커버 및 요약본 렌더링 진행...")

                # 2. 메타데이터 조회: timetable 우선, 유튜브 폴백
                tt_info = self.timetable_service.find_timetable_info_for_lesson(base_name, drive_service=drive_service)
                tt_prof = tt_info.get("professor", "").strip() if tt_info else ""
                tt_lec = tt_info.get("lecture_name", "").strip() if tt_info else ""
                tt_subj = tt_info.get("subject", "").strip() if tt_info else ""

                if tt_prof and tt_lec:
                    if tt_subj:
                        display_title = f"[{tt_subj}] {tt_prof} 교수 - {tt_lec} ({base_name})"
                    else:
                        display_title = f"{base_name}_{tt_prof}_{tt_lec}"
                    self._log(f"   ➔ 📊 timetable 메타데이터 적용: {display_title}")
                else:
                    # 유튜브 메타데이터 폴백 (최신 통합 서비스 활용)
                    yt_info = self.yt_service.find_youtube_info_for_lesson(base_name)
                    yt_prof = yt_info.get("professor", "-")
                    yt_lec = yt_info.get("lecture_name", f"강의_{base_name}")
                    
                    if yt_prof != "-" or yt_lec != f"강의_{base_name}":
                        display_title = f"{base_name}_{yt_prof}_{yt_lec}"
                        self._log(f"   ➔ 📺 유튜브 폴백 적용: {display_title}")
                    else:
                        display_title = f"{base_name} - 강의 정보를 찾을 수 없습니다"
                        self._log("   ➔ ⚠️ 타임테이블 및 유튜브 매칭 실패.")

                video_title = unicodedata.normalize('NFC', display_title)

                # HTML/PDF 변환 (pdf_render_service 통합 유틸 재사용)
                css_content = self.pdf_renderer._get_css_template(
                    margin="40pt",
                    font_path=Config.SUMMARY_FONT_PATH,
                    bold_font_path=Config.SUMMARY_BOLD_FONT_PATH,
                    font_family_name="NanumSummaryFont"
                )
                summary_doc = self.pdf_renderer.create_pdf_from_markdown(
                    md_text=str(summary_text),
                    custom_css=css_content,
                    body_prefix='<pdf:spacer height="160pt" />'
                )

                # 요약본 커버에 원본 1페이지 썸네일 합성
                orig_doc = pymupdf.open(temp_orig_pdf_path)
                first_page = summary_doc[0]
                
                a4_width = 595.0
                thumb_width = a4_width / 3.0
                orig_rect = orig_doc[0].rect
                thumb_height = (orig_rect.height / orig_rect.width) * thumb_width
                
                thumb_rect = pymupdf.Rect(40, 40, 40 + thumb_width, 40 + thumb_height)
                first_page.show_pdf_page(thumb_rect, orig_doc, 0)
                orig_doc.close()

                title_font_path = Config.SUMMARY_BOLD_FONT_PATH or MAC_FONT_PATH
                first_page.insert_font(fontname="ko", fontfile=title_font_path)
                text_rect = pymupdf.Rect(40 + thumb_width + 20, 40, a4_width - 40, 40 + thumb_height)
                
                first_page.insert_textbox(
                    text_rect, 
                    video_title, 
                    fontname="ko", 
                    fontsize=20, 
                    color=(0, 0, 0),
                    align=0
                )

                # 요약본 PDF(summary_doc) 뒤에 슬라이드-스크립트 PDF(slides_doc) 병합
                slides_doc = pymupdf.open(slides_pdf_path)
                summary_doc.insert_pdf(slides_doc)
                slides_doc.close()

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                    temp_pdf_path = temp_pdf.name
                summary_doc.save(temp_pdf_path, garbage=4, deflate=True)
                summary_doc.close()
                summary_doc = None
            else:
                self._log(f"   ➔ ℹ️ 요약본 텍스트 제외: 슬라이드-스크립트만으로 _scripted.pdf를 생성합니다.")
                temp_pdf_path = slides_pdf_path

            upload_name = f"{base_name}_scripted.pdf"

            # 기존에 생성되어 있던 동일 교시(base_name)의 _scripted.pdf 파일 삭제
            for fname, fid in list(files_in_dir.items()):
                if base_name in fname and "scripted" in fname.lower() and fname.endswith(".pdf"):
                    try:
                        self._log(f"   ➔ 🗑️ 기존 파일 삭제 중: {fname}")
                        drive_service.files().delete(fileId=fid).execute()
                    except Exception as del_e:
                        self._log(f"   ➔ ⚠️ 기존 파일 삭제 실패: {del_e}")

            self._log(f"   ➔ ☁️ {upload_name} 드라이브 업로드 중...")
            upload_to_drive(temp_pdf_path, target_folder_id, drive_service=drive_service, new_file_name=upload_name)
            self._log(f"✅ [{base_name}] _scripted.pdf 생성 및 업로드 완료")
            return True

        except Exception as e:
            import traceback
            self._log(f"❌ [{base_name}] _scripted.pdf 생성 및 업로드 실패: {e}")
            print(traceback.format_exc())
            return False
        finally:
            if summary_doc and not summary_doc.is_closed:
                summary_doc.close()
            if temp_pdf_path and os.path.exists(temp_pdf_path) and temp_pdf_path != slides_pdf_path:
                try:
                    os.unlink(temp_pdf_path)
                except Exception:
                    pass
            if temp_orig_pdf_path and os.path.exists(temp_orig_pdf_path):
                try:
                    os.unlink(temp_orig_pdf_path)
                except Exception:
                    pass
            if slides_pdf_path and os.path.exists(slides_pdf_path):
                try:
                    os.unlink(slides_pdf_path)
                except Exception:
                    pass
