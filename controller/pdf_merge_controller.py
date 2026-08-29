# func/func3_pdf_merge.py
import os
import re
import tempfile
import shutil
from functools import partial
from PyQt6.QtWidgets import (QListWidgetItem, QFrame, QVBoxLayout, QLabel, 
                             QHBoxLayout, QScrollArea, QWidget, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from base.base_controller import BaseController
from worker.pdf_worker import PdfSimpleOperationThread

from utils.file_util import list_local_files
from utils.drive_api import (
    get_drive_service, 
    get_all_drive_files, 
    download_from_drive,
)
from utils.pdf_core_util import get_page_image_bytes
from utils.config import Config
from service.pdf_operation_service import PdfOperationService

class PreviewState:
    def __init__(self, pdf_path, layout):
        self.pdf_path = pdf_path
        self.layout = layout
        self.current_page = 0
        self.is_eof = False
        self.is_rendering = False

class PdfMergeController(BaseController):
    # 완료 시 UI에 알리기 위한 추가 시그널
    merge_completed = pyqtSignal(str)

    def __init__(self, ui_instance):
        super().__init__()
        self.ui = ui_instance
        self.file_paths = {}
        
        self.temp_dir = tempfile.mkdtemp()
        self.drive_cache = {}
        self.preview_states = []
        
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._do_update_preview)
        
        # 스레드로 넘길 데이터를 담아두는 임시 변수
        self._current_merge_task = {}

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def populate_file_list(self):
        self.ui.file_list.clear()
        self.file_paths.clear()
        
        is_drive = self.ui.drive_check.isChecked()
        
        if not is_drive:
            target_dir = self.ui.folder_input.text()
            if not os.path.exists(target_dir):
                self.emit_log("❌ 대상 폴더가 존재하지 않습니다.")
                return
                
            files = list_local_files(target_dir, extension=".pdf")
            if not files:
                self.emit_log("⚠️ 폴더 내에 PDF 파일이 없습니다.")
                return
                
            files.sort(key=lambda x: (0 if '_scripted.pdf' in x.lower() else 1, x))
                
            for f in files:
                item_text = f"📄 {f}"
                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.ui.file_list.addItem(item)
                self.file_paths[item_text] = os.path.join(target_dir, f)
                
            self.emit_log(f"✅ 로컬 폴더에서 {len(files)}개의 PDF를 불러왔습니다.")
            
        else:
            self.emit_log("🔄 구글 드라이브에서 조건에 맞는 PDF 파일을 조회 중입니다...")
            try:
                drive_service, _ = get_drive_service()
                
                try:
                    folder_id = Config.TARGET_DRIVE_DIR
                except ValueError:
                    self.emit_log("❌ .env 설정 오류: TARGET_DRIVE_DIR 폴더 ID를 찾을 수 없습니다.")
                    return 
                
                files = get_all_drive_files(folder_id, drive_service=drive_service)
                pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]
                
                start_str = self.ui.start_date.date().toString("MMdd")
                end_str = self.ui.end_date.date().toString("MMdd")
                
                # --- 다이어트 로직: 서비스 클래스에 필터링 위임 ---
                from service.file_naming_service import FileNamingService
                naming_service = FileNamingService(logger_callback=self.emit_log)
                filtered_pdfs = naming_service.filter_files_by_date_range(pdf_files, start_str, end_str)
                # ----------------------------------------------------
        
                filtered_pdfs.sort(key=lambda x: (0 if '_scripted.pdf' in x['name'].lower() else 1, x['name']))

                for f in filtered_pdfs:
                    item_text = f"☁️ {f['name']}"
                    item = QListWidgetItem(item_text)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.ui.file_list.addItem(item)
                    self.file_paths[item_text] = f['id']
                    
                self.emit_log(f"✅ 구글 드라이브에서 {len(filtered_pdfs)}개의 PDF를 불러왔습니다.")
            except Exception as e:
                self.emit_log(f"❌ 구글 드라이브 파일 로드 실패: {str(e)}")
        
        self.ui.update_select_all_ui()
        self.update_preview()

    def update_preview(self):
        self.preview_timer.start(500)

    def _do_update_preview(self):
        # (기존 코드와 동일하여 미리보기 렌더링 로직 유지)
        for i in reversed(range(self.ui.preview_layout.count())): 
            item = self.ui.preview_layout.itemAt(i)
            if item.layout():
                for j in reversed(range(item.layout().count())):
                    widget = item.layout().itemAt(j).widget()
                    if widget: widget.deleteLater()
                item.layout().deleteLater()
                
        selected = self.get_selected_files()
        self.update_save_name(selected)
        
        self.preview_states.clear() 

        is_drive = self.ui.drive_check.isChecked()
        drive_service = None
        
        if is_drive and selected:
            drive_service, _ = get_drive_service()
            
        for name, path_or_id in selected: 
            file_group_frame = QFrame()
            file_group_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFFFFF;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }
            """)
            group_layout = QVBoxLayout(file_group_frame)
            group_layout.setContentsMargins(12, 12, 12, 12)
            group_layout.setSpacing(8)
            
            file_name_label = QLabel(name.replace("📄 ", "").replace("☁️ ", ""))
            file_name_label.setStyleSheet("color: #1E293B; font-weight: bold; font-size: 13px; border: none; background: transparent;")
            group_layout.addWidget(file_name_label)
            
            thumbnails_container = QWidget()
            thumbnails_container.setStyleSheet("background: transparent; border: none;")
            
            thumb_layout = QHBoxLayout(thumbnails_container)
            thumb_layout.setContentsMargins(0, 0, 0, 0)
            thumb_layout.setSpacing(10)
            thumb_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFixedHeight(170)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            
            scroll_area.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:horizontal {
                    height: 8px; background: #F1F5F9; border-radius: 4px; margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:horizontal {
                    background: #CBD5E1; border-radius: 4px; min-width: 20px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #94A3B8;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px; background: none;
                }
            """)
            scroll_area.setWidget(thumbnails_container)
            
            group_layout.addWidget(scroll_area)
            
            if is_drive:
                if path_or_id not in self.drive_cache:
                    temp_path = os.path.join(self.temp_dir, f"{path_or_id}.pdf")
                    download_from_drive(path_or_id, temp_path, drive_service=drive_service)
                    self.drive_cache[path_or_id] = temp_path
                local_pdf_path = self.drive_cache[path_or_id]
            else:
                local_pdf_path = path_or_id

            state = PreviewState(local_pdf_path, thumb_layout)
            self.preview_states.append(state)
            
            h_scrollbar = scroll_area.horizontalScrollBar()
            h_scrollbar.valueChanged.connect(partial(self.on_scroll, scrollbar=h_scrollbar, state=state))
            
            self.load_more_pages(state, batch_size=5)
            self.ui.preview_layout.addWidget(file_group_frame)
            
            QApplication.processEvents()
            while h_scrollbar.maximum() == 0 and not state.is_eof:
                self.load_more_pages(state, batch_size=3)
                QApplication.processEvents()

    def on_scroll(self, value, scrollbar, state):
        threshold = max(0, scrollbar.maximum() - 150)
        if scrollbar.maximum() > 0 and value >= threshold:
            self.load_more_pages(state, batch_size=5)

    def load_more_pages(self, state, batch_size=5):
        if state.is_eof or state.is_rendering:
            return
            
        state.is_rendering = True

        # 이제 업데이트 되서 원래 pixmap 바로 받아오건 거를 get_page_image_bytes 바이트 기반으로 바꿨고 이제 찐 랜더링은 UI의 몫이라 UI level에서 base_ui_componet에 들어있는 componet 기반으로 해야 하는데 일단 이 대로 냅두고 나중에 controller 수정할 대 같이 수정하자!!
        for _ in range(batch_size):
            pixmap = get_page_image_bytes(state.pdf_path, state.current_page, zoom=0.15)

            if not pixmap:
                state.is_eof = True
                break
            
            scaled_pixmap = pixmap.scaledToHeight(140, Qt.TransformationMode.SmoothTransformation)
                
            page_frame = QFrame()
            page_frame.setFixedSize(scaled_pixmap.width() + 2, scaled_pixmap.height() + 2) 
            page_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px;")
            
            v_layout = QVBoxLayout(page_frame)
            v_layout.setContentsMargins(1, 1, 1, 1)
            
            img_label = QLabel()
            img_label.setPixmap(scaled_pixmap)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            v_layout.addWidget(img_label)
            state.layout.addWidget(page_frame)
            
            state.current_page += 1
            
        state.is_rendering = False

    def update_save_name(self, selected):
        if len(selected) < 2:
            self.ui.save_name_input.setText("")
            return
            
        file_names = [name.replace("📄 ", "").replace("☁️ ", "") for name, _ in selected]
        is_all_scripted = all('_scripted.pdf' in f.lower() for f in file_names)
        
        dates = set()
        periods = []
        
        for f in file_names:
            match = re.search(r'^(\d{4})_(\d+)', f)
            if match:
                dates.add(match.group(1))
                periods.append(match.group(2))
                
        if len(dates) == 1:
            date_str = dates.pop()
            if is_all_scripted:
                self.ui.save_name_input.setText(f"{date_str}_merged_scripted.pdf")
            else:
                joined_periods = "".join(periods)
                self.ui.save_name_input.setText(f"{date_str}_{joined_periods}.pdf")
        else:
            self.ui.save_name_input.setText("merged_output.pdf")

    # ==========================================
    # 🚀 스레드 연동 병합 프로세스 시작
    # ==========================================
    def merge_files(self):
        """UI에서 병합 버튼을 누르면 호출됩니다. 백그라운드 스레드를 띄웁니다."""
        selected = self.get_selected_files()
        if len(selected) < 2:
            self.emit_log("⚠️ 병합을 위해서는 2개 이상의 파일이 선택되어야 합니다.")
            return
            
        save_name = self.ui.save_name_input.text()
        if not save_name.endswith('.pdf'):
            save_name += '.pdf'
            self.ui.save_name_input.setText(save_name)
            
        # 백그라운드에서 읽을 수 있도록 컨트롤러 변수에 임시 저장
        self._current_merge_task = {
            'selected': selected,
            'save_name': save_name,
            'is_drive': self.ui.drive_check.isChecked(),
            'target_dir': self.ui.folder_input.text()
        }
        
        self.cleanup_worker()
        self.worker = PdfSimpleOperationThread(self, 'MERGE')
        
        self.worker.success_signal.connect(self.on_merge_success)
        self.worker.error_signal.connect(self.emit_error)
        self.worker.log_signal.connect(self.emit_log)
        self.worker.finished.connect(self.worker.deleteLater)
        
        self.worker.start()

    def execute_merge_logic(self):
        """PdfSimpleOperationThread 내부에서 실행되는 무거운 병합 로직입니다."""
        task = self._current_merge_task
        selected = task['selected']
        save_name = task['save_name']
        is_drive = task['is_drive']
        target_dir = task['target_dir']
        
        try:
            paths_to_merge = []
            drive_service = None
            
            if is_drive:
                drive_service, _ = get_drive_service()
                for name, file_id in selected:
                    if file_id in self.drive_cache:
                        paths_to_merge.append(self.drive_cache[file_id])
                    else:
                        temp_file = os.path.join(self.temp_dir, f"{file_id}.pdf")
                        download_from_drive(file_id, temp_file, drive_service=drive_service)
                        paths_to_merge.append(temp_file)
            else:
                paths_to_merge = [path for _, path in selected]
                
            # --- 다이어트된 핵심 로직: 서비스 클래스로 위임 ---
            operation_service = PdfOperationService(logger_callback=self.emit_log)
            success, result_msg = operation_service.merge_and_save(
                paths_to_merge=paths_to_merge,
                save_name=save_name,
                is_drive=is_drive,
                target_dir=target_dir if not is_drive else None
            )
            
            if success:
                return result_msg
            else:
                raise Exception(result_msg)
            
        except Exception as e:
            raise Exception(f"병합 실행 중 오류 발생: {str(e)}")

    def on_merge_success(self, result_msg):
        """병합이 완료되면 호출됩니다."""
        self.emit_log(result_msg)
        self.merge_completed.emit(result_msg)
        self._current_merge_task = {} # 메모리 정리

    def get_selected_files(self):
        selected = []
        for i in range(self.ui.file_list.count()):
            item = self.ui.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append((item.text(), self.file_paths.get(item.text())))
        return selected