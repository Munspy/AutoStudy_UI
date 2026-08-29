import shutil
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Callable, Union

from utils.pdf_core_util import split_pdf_two_parts, merge_pdfs
from utils.drive_api import upload_to_drive
from utils.auth_util import get_drive_service
from base.base_service import BaseService
from utils.config import Config

# 모던 파이썬 타입 힌팅 적용
PathLike = Union[str, Path]

class PdfOperationService(BaseService):
    """
    단순 PDF 분할(Split) 및 병합(Merge) 연산과 
    결과물의 로컬 저장 및 구글 드라이브 업로드를 전담하는 서비스입니다.
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        self.drive_service = get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR

    def split_and_save(
        self, 
        current_pdf_path: PathLike, 
        split_page: int, 
        out1_name: str, 
        out2_name: str, 
        is_drive: bool, 
        target_dir: Optional[PathLike] = None
    ) -> Tuple[bool, str]:
        """PDF를 분할하고 사용자가 선택한 저장소(로컬/드라이브)에 저장합니다."""
        
        # [최적화 3] 의도된 로직 오류(디렉토리 누락 등)는 Exception을 던지지 않고 즉시 실패 반환
        if not is_drive:
            if not target_dir:
                return False, "❌ 로컬 저장 폴더가 지정되지 않았습니다."
            target_p = Path(target_dir)
            if not target_p.exists() or not target_p.is_dir():
                return False, f"❌ 로컬 저장 폴더가 유효하지 않습니다: {target_dir}"

        # [최적화 1] 컨텍스트 매니저를 사용하여 함수가 끝나면 임시 디렉토리 100% 자동 삭제 보장
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # [최적화 2] pathlib.Path를 이용한 직관적인 경로 조작
                temp_p = Path(temp_dir)
                temp_out1 = temp_p / out1_name
                temp_out2 = temp_p / out2_name
                
                self._log(f"✂️ 물리적 PDF 분할을 시작합니다 (기준: {split_page}페이지 뒤)")
                
                # 1. 물리적 PDF 분할 연산
                split_pdf_two_parts(current_pdf_path, split_page, temp_out1, temp_out2)
                
                # 2. 지정된 위치로 파일 전송
                if is_drive:
                    self._log("☁️ 구글 드라이브에 분할된 파일을 업로드 중입니다...")
                    upload_to_drive(str(temp_out1), self.target_folder_id, mime_type='application/pdf', drive_service=self.drive_service)
                    upload_to_drive(str(temp_out2), self.target_folder_id, mime_type='application/pdf', drive_service=self.drive_service)
                    msg = f"✅ 드라이브 업로드 성공! ({out1_name}, {out2_name})"
                    self._log(msg)
                    return True, msg
                else:
                    self._log("💾 로컬 디렉토리로 분할된 파일을 복사합니다...")
                    shutil.copy(temp_out1, target_p / out1_name)
                    shutil.copy(temp_out2, target_p / out2_name)
                    msg = f"✅ 로컬 저장 성공! ({out1_name}, {out2_name})"
                    self._log(msg)
                    return True, msg
                    
        except Exception as e:
            # 예상치 못한 시스템(IO 등) 오류만 Exception으로 처리
            msg = f"❌ 분할/저장 중 시스템 오류 발생: {str(e)}"
            self._log(msg)
            return False, msg

    def merge_and_save(
        self, 
        paths_to_merge: List[PathLike], 
        save_name: str, 
        is_drive: bool, 
        target_dir: Optional[PathLike] = None
    ) -> Tuple[bool, str]:
        """여러 PDF를 병합하고 사용자가 선택한 저장소(로컬/드라이브)에 저장합니다."""
        
        # [최적화 3] 의도된 검증 실패 조기 반환 (Early Return)
        if not is_drive:
            if not target_dir:
                return False, "❌ 로컬 저장 폴더가 지정되지 않았습니다."
            target_p = Path(target_dir)
            if not target_p.exists() or not target_p.is_dir():
                return False, f"❌ 로컬 저장 폴더가 유효하지 않습니다: {target_dir}"

        # [최적화 1] 기존의 공용 temp 디렉토리 대신, 완전히 격리된 고유 TemporaryDirectory 사용 (병렬 처리 충돌 방지)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_merged_path = Path(temp_dir) / save_name
                
                self._log(f"🔗 {len(paths_to_merge)}개의 PDF 파일 병합을 시작합니다...")
                
                # 1. 물리적 PDF 병합 연산
                merge_pdfs(paths_to_merge, temp_merged_path)
                
                # 2. 지정된 위치로 파일 전송
                if is_drive:
                    self._log("☁️ 구글 드라이브에 병합된 파일을 업로드 중입니다...")
                    upload_to_drive(str(temp_merged_path), self.target_folder_id, mime_type='application/pdf', drive_service=self.drive_service)
                    msg = f"✅ 드라이브 업로드 성공! 파일명: {save_name}"
                    self._log(msg)
                    return True, msg
                else:
                    self._log("💾 로컬 디렉토리로 병합된 파일을 복사합니다...")
                    save_path = target_p / save_name
                    shutil.copy(temp_merged_path, save_path)
                    msg = f"✅ 병합 성공! 저장 위치: {save_path}"
                    self._log(msg)
                    return True, msg
                    
        except Exception as e:
            msg = f"❌ 병합/저장 중 시스템 오류 발생: {str(e)}"
            self._log(msg)
            return False, msg