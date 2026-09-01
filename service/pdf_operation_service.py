"""PDF 분할 및 병합 I/O 오케스트레이션 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
단순한 물리적 PDF 조작(Core Utils)과 파일 저장소 통신(로컬/드라이브 API) 사이의 흐름을 제어하고 연결합니다.

사용자 인터페이스(Controller)나 자동화 파이프라인(Worker)으로부터 PDF 파일의 분할(Split) 및 병합(Merge) 요청을 받아, 
임시 디렉토리(Temporary Directory) 격리 환경에서 `pdf_core_util`을 통해 물리적 파일 조작을 안전하게 수행하고, 
생성된 결과물을 최종 목적지(로컬 디스크 또는 Google Drive)로 업로드 및 전송하는 
고수준(High-level) 비즈니스 워크플로우를 담당합니다.
"""

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
    """단순 PDF 분할(Split) 및 병합(Merge) 연산과 결과물의 로컬 저장 및 구글 드라이브 업로드를 전담하는 서비스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 PDF 바이너리 데이터를 직접 깎거나 수정하지 않으며(Core Utils에 위임), 
    연산이 수행될 '안전한 공간(임시 폴더)'을 마련하고 완성된 파일의 '배송(I/O Routing)'만을 책임집니다.

    의존성:
    - 물리적 조작: `utils.pdf_core_util`의 `split_pdf_two_parts`, `merge_pdfs`
    - 클라우드 저장: `utils.drive_api.upload_to_drive`, `utils.auth_util.get_drive_service`
    - 부모 클래스: `BaseService` (공통 로깅 인터페이스 상속)
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """PdfOperationService를 초기화하고 Google Drive 서비스 객체를 준비합니다.

        Args:            logger_callback (Optional[Callable[[str], None]], optional): 비동기 작업 중 
                발생하는 상태 메시지를 UI 등 상위 계층으로 전달하기 위한 콜백 함수. Defaults to None.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        super().__init__(logger_callback=logger_callback)
        self.drive_service = get_drive_service()
        self.target_folder_id: str = Config.TARGET_DRIVE_DIR

    def split_and_save(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        local_path: PathLike, 
        split_page: int, 
        out1_name: str, 
        out2_name: str, 
        is_drive: bool, 
        target_dir: Optional[PathLike] = None
    ) -> Tuple[bool, str]:
        """하나의 PDF를 두 개로 분할하고, 지정된 저장소(로컬/드라이브)에 안전하게 배포합니다.        학습 자료 처리 파이프라인에서, 너무 용량이 큰 강의록이나 필기본이 인입되었을 때 
        API 페이로드 제한(Gemini 토큰 리밋 등)을 피하기 위해 파일을 쪼개야 하는 경우가 발생합니다. 
        이 메서드는 이러한 분할 요청을 처리할 때, 시스템 디스크 공간을 오염시키지 않도록 
        `tempfile.TemporaryDirectory()`를 활용한 격리 샌드박스를 구성합니다.
        
        격리된 공간에서 PDF 코어 유틸을 통해 두 개의 파트로 분할을 완료한 뒤, 
        `is_drive` 플래그에 따라 로컬 폴더로 복사하거나 구글 드라이브로 네트워크 업로드를 수행합니다. 
        작업이 완료되거나 예외가 발생하면 샌드박스(임시 폴더)는 파이썬의 컨텍스트 매니저에 의해 
        찌꺼기 없이 100% 자동 삭제(Clean-up)되므로, 24시간 가동되는 백그라운드 Worker 환경에서도 
        메모리나 디스크 누수 없이 안정적으로 동작합니다.

        Args:
            local_path (PathLike): 분할 대상이 되는 원본 PDF 파일의 로컬 경로.
            split_page (int): 분할 기준이 되는 페이지 번호 (1-based index 기준, 해당 페이지 뒤에서 분할됨).
            out1_name (str): 분할되어 생성될 첫 번째 파트의 결과물 파일명.
            out2_name (str): 분할되어 생성될 두 번째 파트의 결과물 파일명.
            is_drive (bool): **True**일 경우 구글 드라이브로 업로드, **False**일 경우 로컬 `target_dir`로 저장.
            target_dir (Optional[PathLike], optional): 로컬 저장을 선택했을 때 목적지 디렉토리 경로. 
                `is_drive`가 False일 때 필수값입니다. Defaults to None.

        Returns:
            Tuple[bool, str]: 
                - 첫 번째 요소 (bool): 작업의 성공 여부 플래그 (True: 성공, False: 실패).
                - 두 번째 요소 (str): UI에 출력할 성공 메시지 또는 구체적인 에러 원인 메시지.
        """
        
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
                split_pdf_two_parts(local_path, split_page, temp_out1, temp_out2)
                
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
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        paths_to_merge: List[PathLike], 
        save_name: str, 
        is_drive: bool, 
        target_dir: Optional[PathLike] = None
    ) -> Tuple[bool, str]:
        """여러 PDF 파일을 하나로 병합하고, 지정된 저장소(로컬/드라이브)에 안전하게 배포합니다.        여러 개로 흩어져 있던 필기본이나, LLM 요약 파이프라인의 결과로 나온 개별 스크립트들을 
        최종 배포용 단일 학습 자료(합본)로 묶어낼 때 호출되는 필수 워크플로우입니다. 
        
        멀티스레드 기반의 비동기 큐(Queue) 환경에서는 여러 병합 작업이 동시에 발생할 수 있습니다. 
        이때 고정된 임시 파일명(예: `temp.pdf`)을 사용하면 스레드 간 덮어쓰기(Race Condition)가 발생해 
        데이터 오염이 생길 수 있습니다. 이를 방지하기 위해 완전히 독립되고 고유한 경로를 가지는 
        `tempfile.TemporaryDirectory()`를 매 호출마다 할당받아, 그 안에서만 병합 연산을 수행하여 원자성(Atomicity)을 확보합니다. 
        연산이 끝나면 `shutil` 또는 `upload_to_drive`를 통해 결과물만 대상지로 쏙 빼내어 저장합니다.

        Args:
            paths_to_merge (List[PathLike]): 하나로 병합할 대상 PDF 파일들의 로컬 경로 리스트. (리스트 순서대로 병합됨)
            save_name (str): 병합되어 생성될 결과물 PDF의 최종 파일명.
            is_drive (bool): **True**일 경우 구글 드라이브로 업로드, **False**일 경우 로컬 `target_dir`로 복사 저장.
            target_dir (Optional[PathLike], optional): 로컬 저장을 선택했을 때 결과물이 위치할 목적지 디렉토리. 
                `is_drive`가 False일 때 필수값입니다. Defaults to None.

        Returns:
            Tuple[bool, str]: 
                - 첫 번째 요소 (bool): 병합 및 저장 작업의 성공 여부 플래그 (True: 성공, False: 실패).
                - 두 번째 요소 (str): UI 테이블이나 알림창에 출력할 성공/에러 메시지.
        """
        
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