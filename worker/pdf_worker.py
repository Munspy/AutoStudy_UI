# Threads/pdf_thread.py

from base.base_worker import BaseThread
import func.func2_combine_notes as backend_combine

class PdfInspectionThread(BaseThread):
    """
    [Tab 2] 선택된 줄필기와 야붙필기 PDF들을 분석하고 매칭 검수 데이터를 생성하는 스레드
    수십 페이지의 PDF를 렌더링하고 이미지 해시/OCR을 비교하는 무거운 연산을 백그라운드에서 처리합니다.
    """
    def __init__(self, folder_path, selected_keys, matched_groups):
        super().__init__()
        self.folder_path = folder_path
        self.selected_keys = selected_keys
        self.matched_groups = matched_groups

    def _task(self):
        self.log_signal.emit("🔍 PDF 파일 분석 및 페이지 매칭을 진행 중입니다. 잠시만 기다려주세요...")
        
        # 🛑 스위치 확인
        if not self._is_running:
            return []
            
        # 연산량이 많은 데이터 제너레이션 작업 실행
        # (추후 backend_combine 내부에 콜백을 넘겨 세밀한 progress_signal(int)을 쏘게 고도화할 수 있습니다)
        base_data = backend_combine.generate_real_data(
            self.folder_path, 
            self.selected_keys, 
            self.matched_groups
        )
        
        # 🛑 스위치 확인
        if not self._is_running:
            return []
            
        self.log_signal.emit("✅ PDF 매칭 데이터 검수가 완료되었습니다.")
        return base_data


class PdfCombineSaveThread(BaseThread):
    """
    [Tab 2] 검수가 완료된 데이터를 바탕으로 최종 PDF를 병합하고 로컬에 저장하는 스레드
    I/O 병목으로 인한 멈춤을 방지합니다.
    """
    def __init__(self, base_data, folder_path):
        super().__init__()
        self.base_data = base_data
        self.folder_path = folder_path

    def _task(self):
        self.log_signal.emit("💾 최종 PDF 병합 및 저장을 시작합니다...")
        
        if not self._is_running:
            return []
            
        # 실제 병합 후 저장된 파일 리스트 반환
        saved_files = backend_combine.execute_merge(self.base_data, self.folder_path)
        
        if not self._is_running:
            return []
            
        self.log_signal.emit(f"✅ 성공적으로 {len(saved_files)}개의 파일을 병합 및 저장했습니다.")
        return saved_files


class PdfSimpleOperationThread(BaseThread):
    """
    [Tab 3, 4 공통] 단순 PDF 병합(Merge) 및 분할(Split) 작업을 처리하는 범용 스레드
    """
    def __init__(self, controller, action_type):
        super().__init__()
        self.controller = controller
        self.action_type = action_type  # 'MERGE' 또는 'SPLIT'

    def _task(self):
        if not self._is_running:
            return None
            
        self.log_signal.emit(f"🚀 PDF {self.action_type} 작업을 백그라운드에서 시작합니다...")

        # 컨트롤러 단에 구현되어 있는 병합/분할 함수를 래핑하여 백그라운드에서 실행
        if self.action_type == 'MERGE' and hasattr(self.controller, 'execute_merge_logic'):
            result = self.controller.execute_merge_logic()
        elif self.action_type == 'SPLIT' and hasattr(self.controller, 'execute_split_logic'):
            result = self.controller.execute_split_logic()
        else:
            raise ValueError(f"지원하지 않는 작업이거나 컨트롤러에 메서드가 없습니다: {self.action_type}")

        if not self._is_running:
            return None
            
        return result