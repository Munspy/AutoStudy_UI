import os
import re
import io
import unicodedata
import fitz  # PyMuPDF
import tempfile
import markdown
from xhtml2pdf import pisa
from dotenv import dotenv_values
import yt_dlp
from typing import Optional, Callable

from base.base_service import BaseService
from service.pdf_render_service import PdfRenderService
from service.youtube_playlist_service import YoutubePlaylistService
from utils.drive_api import in_memory_download_from_drive, upload_to_drive

MAC_FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

class SummaryPdfService(BaseService):
    """요약본과 원본 슬라이드 및 스크립트를 결합한 _scripted.pdf 생성을 전담하는 서비스."""

    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        self.playlist_cache = {}
        self.pdf_renderer = PdfRenderService(logger_callback=logger_callback)
        self.yt_service = YoutubePlaylistService(logger_callback=logger_callback)

    def get_playlist_videos(self, playlist_url):
        if not playlist_url:
            return []
        if "list=" in playlist_url:
            match = re.search(r'list=([^&]+)', playlist_url)
            if match:
                playlist_url = f"https://www.youtube.com/playlist?list={match.group(1)}"

        self._log(f"   ➔ 🔗 유튜브 재생목록 API 호출 중: {playlist_url}")
        ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                if 'entries' in info:
                    titles = [entry.get('title', '') for entry in info['entries'] if entry]
                    self._log(f"   ➔ 🚀 재생목록에서 총 {len(titles)}개의 영상 제목을 수집했습니다.")
                    return titles
        except Exception as e:
            self._log(f"   ➔ ❌ 플레이리스트 로드 실패: {e}")
        return []

    def match_video_title(self, base_name, video_titles):
        parts = base_name.split('_')
        date_str = parts[0]
        base_periods = parts[1] if len(parts) > 1 else ""
        
        for title in video_titles:
            if not title.startswith(date_str):
                continue
            title_parts = title.split('_')
            if len(title_parts) > 1:
                title_periods = title_parts[1]
                base_digits = set(re.findall(r'\d', base_periods))
                title_digits = set(re.findall(r'\d', title_periods))
                if not base_digits or not title_digits or (base_digits & title_digits):
                    return title
            else:
                if not base_periods:
                    return title
                    
        return f"{base_name} - 영상을 찾을 수 없습니다"

    def preprocess_markdown(self, text: str) -> str:
        """마크다운 수식 및 특수문자 전처리를 PdfRenderService에 위임합니다."""
        return self.pdf_renderer.sanitize_markdown(text)

    def parse_slides_data(self, corrected_text: str) -> dict:
        slides_data = {}
        if not corrected_text:
            return slides_data
        parts = re.split(r'\[Slide\s*0*(\d+)\]', corrected_text, flags=re.IGNORECASE)
        for i in range(1, len(parts), 2):
            try:
                slide_num = int(parts[i])
                slide_text = parts[i+1].strip()
                slides_data[slide_num] = slide_text
            except ValueError:
                continue
        return slides_data

    def load_all_csv_video_titles(self) -> list:
        if hasattr(self, "_all_csv_titles_cache") and self._all_csv_titles_cache:
            return self._all_csv_titles_cache
            
        all_titles = []
        try:
            from service.playlist_repository import PlaylistRepository
            from utils.auth_util import get_youtube_service
            repo = PlaylistRepository()
            playlists = repo.load_playlists()
            youtube_service = get_youtube_service()
            
            for item in playlists:
                pid = item.get("playlist_id")
                url = item.get("url")
                if not pid and url:
                    pid = self.yt_service.parse_playlist_id(url)
                    
                if pid:
                    try:
                        next_token = None
                        while True:
                            res = youtube_service.playlistItems().list(
                                part="snippet",
                                playlistId=pid,
                                maxResults=50,
                                pageToken=next_token
                            ).execute()
                            for v in res.get("items", []):
                                title = v.get("snippet", {}).get("title", "")
                                if title:
                                    all_titles.append(title)
                            next_token = res.get("nextPageToken")
                            if not next_token:
                                break
                    except Exception as e:
                        self._log(f"   ➔ ⚠️ 유튜브 API 재생목록({pid}) 조회 실패, yt-dlp 시도: {e}")
                        if url:
                            all_titles.extend(self.get_playlist_videos(url))
        except Exception as outer_e:
            self._log(f"   ➔ ⚠️ CSV 유튜브 제목 로드 중 오류: {outer_e}")
            
        self._all_csv_titles_cache = all_titles
        return all_titles

    def generate_and_upload_scripted_pdf(self, base_name: str, summary_text: str, corrected_text: str, target_folder_id: str, drive_service):
        self._log(f"📄 [{base_name}] _scripted.pdf 생성 시작...")
        
        # 1. 대상 폴더에서 파일 목록 조회
        query = f"'{target_folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files_in_dir = {f['name']: f['id'] for f in results.get('files', [])}
        
        pdf_name = next((name for name in files_in_dir.keys() if name.endswith(".pdf") and base_name in name and "scripted" not in name), None)

        # 2. 비디오 제목 매칭
        video_title = f"{base_name} - 영상을 찾을 수 없습니다"
        playlist_url = os.environ.get("YOUTUBE_PLAYLIST_URL")
        
        if not playlist_url:
            env_name = next((name for name in files_in_dir.keys() if "env" in name), None)
            if env_name:
                with in_memory_download_from_drive(files_in_dir[env_name], drive_service=drive_service) as env_io:
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_env:
                        temp_env.write(env_io.getvalue())
                        temp_env_path = temp_env.name
                    local_env = dotenv_values(temp_env_path)
                    os.unlink(temp_env_path)
                    playlist_url = local_env.get("YOUTUBE_PLAYLIST_URL")
        
        # CSV (Tab 8 목록) 기반 전체 유튜브 제목 데이터베이스 탐색
        all_titles = self.load_all_csv_video_titles()
        if all_titles:
            video_title = self.match_video_title(base_name, all_titles)
            self._log(f"   ➔ 유튜브 매칭: {video_title}")
        elif playlist_url:
            if playlist_url not in self.playlist_cache:
                self.playlist_cache[playlist_url] = self.get_playlist_videos(playlist_url)
            videos = self.playlist_cache[playlist_url]
            video_title = self.match_video_title(base_name, videos)
            self._log(f"   ➔ 유튜브 매칭 (단일 URL): {video_title}")
        else:
            self._log("   ➔ ⚠️ 매칭할 유튜브 비디오 제목을 찾을 수 없습니다.")
            
        video_title = unicodedata.normalize('NFC', video_title)


        # 3. HTML/PDF 변환
        md_summary = self.preprocess_markdown(summary_text)
        html_summary_body = markdown.markdown(md_summary, extensions=['tables', 'sane_lists', 'fenced_code'])
        
        common_css = f"""
            @font-face {{ font-family: 'KoreanFont'; src: url('{MAC_FONT_PATH}'); }}
            body {{ font-family: 'KoreanFont', sans-serif; font-size: 10pt; line-height: 1.6; color: #1d1d1f; word-wrap: cjk; word-break: keep-all; }}
            pre {{ font-family: 'KoreanFont', monospace; font-size: 7.5pt; line-height: 1.2; white-space: pre; background-color: #f4f5f7; padding: 10px; border: 1pt solid #ddd; }}
            h1 {{ font-size: 18pt; border-bottom: 1.5pt solid #333; padding-bottom: 5px; margin-bottom: 15px; -pdf-keep-with-next: true; }}
            h2 {{ font-size: 14pt; margin-top: 15px; margin-bottom: 10px; border-bottom: 0.5pt solid #ccc; -pdf-keep-with-next: true; }}
            h3 {{ font-size: 12pt; margin-top: 12px; margin-bottom: 8px; -pdf-keep-with-next: true; }}
            p {{ margin-bottom: 8px; text-align: justify; }}
            ul, ol {{ margin-bottom: 10pt; margin-left: 25pt; }}
            li {{ margin-bottom: 5pt; padding-left: 2pt; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            th, td {{ border: 0.5pt solid #999; padding: 8px; text-align: left; vertical-align: top; }}
            th {{ background-color: #f0f0f0; font-weight: bold; text-align: center; }}
        """

        html_content = f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><style>
            {common_css}
            @page {{ size: a4 portrait; margin: 40pt; }}
        </style></head>
        <body>
            <pdf:spacer height="160pt" />
            {html_summary_body}
        </body></html>
        """

        summary_pdf_io = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_content), dest=summary_pdf_io)
        summary_doc = fitz.open("pdf", summary_pdf_io.getvalue())
        
        # 4. 원본 PDF 다운로드 및 합성
        temp_orig_pdf_path = None
        slides_pdf_path = None
        
        if pdf_name and pdf_name in files_in_dir:
            try:
                # 원본 강의록 다운로드
                with in_memory_download_from_drive(files_in_dir[pdf_name], drive_service=drive_service) as orig_pdf_io:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_orig:
                        temp_orig.write(orig_pdf_io.getvalue())
                        temp_orig_pdf_path = temp_orig.name
                        
                # 요약본 커버에 썸네일 합성
                orig_doc = fitz.open(temp_orig_pdf_path)
                first_page = summary_doc[0]
                
                a4_width = 595.0
                thumb_width = a4_width / 3.0
                orig_rect = orig_doc[0].rect
                thumb_height = (orig_rect.height / orig_rect.width) * thumb_width
                
                thumb_rect = fitz.Rect(40, 40, 40 + thumb_width, 40 + thumb_height)
                first_page.show_pdf_page(thumb_rect, orig_doc, 0)
                orig_doc.close()

                first_page.insert_font(fontname="ko", fontfile=MAC_FONT_PATH)
                text_rect = fitz.Rect(40 + thumb_width + 20, 40, a4_width - 40, 40 + thumb_height)
                
                first_page.insert_textbox(
                    text_rect, 
                    video_title, 
                    fontname="ko", 
                    fontsize=20, 
                    color=(0, 0, 0),
                    align=0
                )
                
                # 교정본 스크립트를 슬라이드별로 파싱하여 표준 형태 PDF(위 슬라이드, 아래 스크립트) 생성
                slides_data_dict = self.parse_slides_data(corrected_text)
                if slides_data_dict:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_slides:
                        slides_pdf_path = temp_slides.name
                        
                    self._log(f"   ➔ 🛠️ 표준 슬라이드-스크립트 병합본 렌더링 중...")
                    self.pdf_renderer.create_slide_script_pdf(temp_orig_pdf_path, slides_data_dict, slides_pdf_path)
                    
                    # 요약본 PDF(summary_doc) 뒤에 슬라이드-스크립트 PDF(slides_doc) 병합
                    slides_doc = fitz.open(slides_pdf_path)
                    summary_doc.insert_pdf(slides_doc)
                    slides_doc.close()
                    
            except Exception as e:
                import traceback
                self._log(f"   ➔ ⚠️ 합성 및 병합 실패: {e}")
                print(traceback.format_exc())

        # 5. 드라이브 업로드
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name
            summary_doc.save(temp_pdf_path, garbage=4, deflate=True)
            
        summary_doc.close()
        
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
        try:
            upload_to_drive(temp_pdf_path, target_folder_id, drive_service=drive_service, new_file_name=upload_name)
            self._log(f"✅ [{base_name}] _scripted.pdf 생성 및 업로드 완료")
        except Exception as e:
            self._log(f"❌ 업로드 실패: {e}")
        finally:
            if os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
            if temp_orig_pdf_path and os.path.exists(temp_orig_pdf_path):
                os.unlink(temp_orig_pdf_path)
            if slides_pdf_path and os.path.exists(slides_pdf_path):
                os.unlink(slides_pdf_path)
