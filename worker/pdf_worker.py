from PyQt6.QtCore import pyqtSignal
from utils.auth_util import get_drive_service
from utils.drive_api import get_all_drive_files, download_from_drive
from utils.file_util import list_local_files
from utils.config import Config
from service.file_naming_service import FileNamingService
import os
import tempfile
import pymupdf

from base.base_worker import BaseWorker
from service.pdf_analysis_service import PdfAnalysisService


class PdfInspectionThread(BaseWorker):
    """
    [Tab 2] 선택된 줄필기와 야붙필기 PDF들을 분석하고 매칭 검수 데이터를 생성하는 스레드
    수십 페이지의 PDF를 렌더링하고 이미지 해시/OCR을 비교하는 무거운 연산을 백그라운드에서 처리합니다.
    """
    def __init__(self, folder_path, selected_keys, matched_groups):
        super().__init__()
        self.folder_path = folder_path
        self.selected_keys = selected_keys
        self.matched_groups = matched_groups

    def do_work(self):
        self.log_signal.emit("🔍 PDF 파일 분석 및 페이지 매칭을 진행 중입니다. 잠시만 기다려주세요...")
        
        # 🛑 스위치 확인
        if self.is_cancelled():
            return []
            
        # 연산량이 많은 데이터 제너레이션 작업 실행
        # (추후 backend_combine 내부에 콜백을 넘겨 세밀한 progress_signal(int)을 쏘게 고도화할 수 있습니다)
        base_data = PdfAnalysisService(logger_callback=self.log_signal.emit).generate_matching_data(
            self.folder_path, 
            self.selected_keys, 
            self.matched_groups
        )
        
        # 🛑 스위치 확인
        if self.is_cancelled():
            return []
            
        self.log_signal.emit("✅ PDF 매칭 데이터 검수가 완료되었습니다.")
        return base_data


class PdfCombineSaveThread(BaseWorker):
    """
    [Tab 2] 검수가 완료된 데이터를 바탕으로 최종 PDF를 병합하고 로컬에 저장하는 스레드
    I/O 병목으로 인한 멈춤을 방지합니다.
    """
    def __init__(self, base_data, folder_path):
        super().__init__()
        self.base_data = base_data
        self.folder_path = folder_path

    def do_work(self):
        self.log_signal.emit("💾 최종 PDF 병합 및 저장을 시작합니다...")
        
        if self.is_cancelled():
            return []
            
        # 실제 병합 후 저장된 파일 리스트 반환
        saved_files = PdfAnalysisService(logger_callback=self.log_signal.emit).execute_merge(self.base_data, self.folder_path)
        
        if self.is_cancelled():
            return []
            
        self.log_signal.emit(f"✅ 성공적으로 {len(saved_files)}개의 파일을 병합 및 저장했습니다.")
        return saved_files


class PdfSimpleOperationThread(BaseWorker):
    """
    [Tab 3, 4 공통] 단순 PDF 병합(Merge) 및 분할(Split) 작업을 처리하는 범용 스레드
    """
    def __init__(self, controller, action_type):
        super().__init__()
        self.controller = controller
        self.action_type = action_type  # 'MERGE' 또는 'SPLIT'

    def do_work(self):
        if self.is_cancelled():
            return None
            
        self.log_signal.emit(f"🚀 PDF {self.action_type} 작업을 백그라운드에서 시작합니다...")

        # 컨트롤러 단에 구현되어 있는 병합/분할 함수를 래핑하여 백그라운드에서 실행
        if self.action_type == 'MERGE' and hasattr(self.controller, 'execute_merge_logic'):
            result = self.controller.execute_merge_logic()
        elif self.action_type == 'SPLIT' and hasattr(self.controller, 'execute_split_logic'):
            result = self.controller.execute_split_logic()
        else:
            raise ValueError(f"지원하지 않는 작업이거나 컨트롤러에 메서드가 없습니다: {self.action_type}")

        if self.is_cancelled():
            return None
            
        return result
    
class PdfFileListWorker(BaseWorker):
    def __init__(self, is_drive, target_dir, start_str, end_str):
        super().__init__()
        self.is_drive = is_drive
        self.target_dir = target_dir
        self.start_str = start_str
        self.end_str = end_str

    def do_work(self):
        file_paths = {}
        if not self.is_drive:
            if not os.path.exists(self.target_dir):
                self.error_signal.emit("대상 폴더가 존재하지 않습니다.")
                return file_paths

            files = list_local_files(self.target_dir, extension=".pdf")
            if not files:
                self.error_signal.emit("폴더 내에 PDF 파일이 없습니다.")
                return file_paths

            for f in sorted(files):
                item_text = f"📄 {f}"
                file_paths[item_text] = os.path.join(self.target_dir, f)
            self.log_signal.emit(f"✅ 로컬 폴더에서 {len(files)}개의 PDF를 불러왔습니다.")
        else:
            self.log_signal.emit("🔄 구글 드라이브에서 조건에 맞는 PDF 파일을 조회 중입니다...")
            drive_service = get_drive_service()
            try:
                folder_id = Config.TARGET_DRIVE_DIR
            except ValueError:
                self.error_signal.emit(".env 설정 오류: TARGET_DRIVE_DIR 폴더 ID를 찾을 수 없습니다.")
                return file_paths

            files = get_all_drive_files(folder_id, drive_service=drive_service)
            pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]

            naming_service = FileNamingService(logger_callback=self.log_signal.emit)
            filtered_pdfs = naming_service.filter_files_by_date_range(pdf_files, self.start_str, self.end_str)

            for f in sorted(filtered_pdfs, key=lambda x: x['name']):
                item_text = f"☁️ {f['name']}"
                file_paths[item_text] = f['id']

            self.log_signal.emit(f"✅ 구글 드라이브에서 {len(filtered_pdfs)}개의 PDF를 불러왔습니다.")
        
        return file_paths


class PdfPreviewPrepareWorker(BaseWorker):
    def __init__(self, path_or_id, is_drive, temp_dir):
        super().__init__()
        self.path_or_id = path_or_id
        self.is_drive = is_drive
        self.temp_dir = temp_dir

    def do_work(self):
        local_path = None
        if self.is_drive:
            drive_service = get_drive_service()
            temp_path = os.path.join(self.temp_dir, f"{self.path_or_id}.pdf")
            if not os.path.exists(temp_path):
                self.log_signal.emit(f"🔄 구글 드라이브에서 PDF 파일 다운로드 중...")
                download_from_drive(self.path_or_id, temp_path, drive_service=drive_service)
            local_path = temp_path
        else:
            local_path = self.path_or_id

        total_pages = 0
        try:
            with pymupdf.open(local_path) as doc:
                total_pages = len(doc)
        except Exception as e:
            self.error_signal.emit(f"PDF 열기 실패: {str(e)}")
            return None
            
        return {"local_path": local_path, "total_pages": total_pages}

class PdfMatchListWorker(BaseWorker):
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def do_work(self):
        self.log_signal.emit("🔍 지정된 폴더에서 병합할 PDF 파일 그룹을 탐색합니다...")
        if self.is_cancelled(): return None
        return PdfAnalysisService(logger_callback=self.log_signal.emit).get_matched_file_groups(self.folder_path)

class PdfSplitPreviewRenderWorker(BaseWorker):
    page_rendered = pyqtSignal(int, bytes)

    def __init__(self, local_path, total_pages):
        super().__init__()
        self.local_path = local_path
        self.total_pages = total_pages

    def do_work(self):
        try:
            with pymupdf.open(self.local_path) as doc:
                for i in range(self.total_pages):
                    if self.is_cancelled():
                        break
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2))
                    img_data = pix.tobytes("png")
                    self.page_rendered.emit(i, img_data)
        except Exception as e:
            self.error_signal.emit(f"미리보기 렌더링 실패: {str(e)}")
        return None

class PdfBatchPreviewPrepareWorker(BaseWorker):
    prepared_signal = pyqtSignal(str, object, str, bool, str)

    def __init__(self, items_to_prepare, file_paths, drive_cache, temp_dir, is_drive):
        super().__init__()
        self.items_to_prepare = items_to_prepare
        self.file_paths = file_paths
        self.drive_cache = drive_cache.copy()
        self.temp_dir = temp_dir
        self.is_drive = is_drive

    def do_work(self):
        for item_text in self.items_to_prepare:
            if self.is_cancelled():
                break
            if item_text not in self.file_paths:
                continue
            path_or_id = self.file_paths[item_text]
            
            local_path = path_or_id
            if self.is_drive:
                if path_or_id not in self.drive_cache:
                    temp_path = os.path.join(self.temp_dir, f"{path_or_id}.pdf")
                    try:
                        download_from_drive(path_or_id, temp_path, drive_service=get_drive_service())
                    except Exception as e:
                        self.error_signal.emit(f"다운로드 실패: {e}")
                        continue
                    local_path = temp_path
                else:
                    local_path = self.drive_cache[path_or_id]
            
            if self.is_cancelled():
                break
                
            try:
                doc = pymupdf.open(local_path)
                self.prepared_signal.emit(item_text, doc, path_or_id, self.is_drive, local_path)
            except Exception as e:
                self.error_signal.emit(f"PDF 열기 실패: {e}")
                
        return None


class PdfMergeWorker(BaseWorker):
    def __init__(self, task_data):
        super().__init__()
        self.task = task_data

    def do_work(self):
        self.log_signal.emit("🚀 PDF 병합 작업을 백그라운드에서 시작합니다...")
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        target_files = self.task['files']
        out_name = self.task['out_name']
        is_drive = self.task['is_drive']
        target_dir = self.task['target_dir']
        
        if not out_name.endswith('.pdf'): out_name += '.pdf'
        
        if self.is_cancelled(): return None

        success, msg = operation_service.merge_and_save(
            target_files=target_files,
            out_name=out_name,
            is_drive=is_drive,
            target_dir=target_dir
        )
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg


class PdfSplitWorker(BaseWorker):
    def __init__(self, local_path, split_page, out1_name, out2_name, is_drive, target_dir):
        super().__init__()
        self.local_path = local_path
        self.split_page = split_page
        self.out1_name = out1_name
        self.out2_name = out2_name
        self.is_drive = is_drive
        self.target_dir = target_dir

    def do_work(self):
        self.log_signal.emit("🚀 PDF 분할 작업을 백그라운드에서 시작합니다...")
        operation_service = PdfOperationService(logger_callback=self.log_signal.emit)
        
        if self.is_cancelled(): return None

        success, msg = operation_service.split_and_save(
            local_path=self.local_path,
            split_page=self.split_page,
            out1_name=self.out1_name,
            out2_name=self.out2_name,
            is_drive=self.is_drive,
            target_dir=self.target_dir
        )
        if not success:
            self.error_signal.emit(msg)
            return None
        return msg