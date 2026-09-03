"""AI 파이프라인 오케스트레이션 및 처리 서비스 모듈.

이 모듈은 AutoStudy_UI의 Service 계층에 속하며,
단일 교시(Lesson)에 대한 AI 작업(교정, 요약, Anki) 파이프라인의 전체 실행 흐름을 제어합니다.
폴더 관리, 강의자료 OCR 텍스트 확보, 스크립트 취득, 단계별 의존성(교정 -> 요약/Anki 병렬) 제어
및 결과물의 Google Drive 업로드를 전담합니다.
"""

import os
import tempfile
import traceback
import concurrent.futures
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

from base.base_service import BaseService
from service.llm_service import LlmService
from service.folder_management_service import FolderManagementService
from service.summary_pdf_service import SummaryPdfService
from service.anki_service import AnkiGenerationService
from service.pdf_ocr_service import PdfOcrService
from utils.auth_util import get_drive_service
from utils.drive_api import (
    upload_to_drive,
    temp_download_from_drive,
    in_memory_download_from_drive
)


class AiPipelineService(BaseService):
    """교시별 AI 파이프라인 작업의 실행과 드라이브 동기화를 전담하는 오케스트레이션 서비스 클래스."""

    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """AiPipelineService 인스턴스를 초기화합니다.

        Args:
            logger_callback (Optional[Callable[[str], None]], optional): 로그 출력 콜백 함수.
        """
        super().__init__(logger_callback=logger_callback)
        self.llm_service = LlmService(logger_callback=logger_callback)
        self.folder_service = FolderManagementService(logger_callback=logger_callback)
        self.summary_pdf_service = SummaryPdfService(logger_callback=logger_callback)
        self.anki_gen_service = AnkiGenerationService(logger_callback=logger_callback)
        self.pdf_ocr_service = PdfOcrService(logger_callback=logger_callback)

    def get_text_from_drive(self, folder_id: str, file_name: str, drive_service=None) -> Optional[str]:
        """구글 드라이브의 특정 폴더에서 텍스트 파일 내용을 읽어 반환합니다."""
        if drive_service is None:
            drive_service = get_drive_service()
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        if not files:
            return None
        file_id = files[0]['id']
        with in_memory_download_from_drive(file_id, drive_service=drive_service) as buffer:
            return buffer.read().decode('utf-8', errors='replace')

    def get_pdf_file_id(self, folder_id: str, base_name: str, drive_service=None) -> Optional[str]:
        """구글 드라이브의 대상 폴더 내에서 PDF 파일의 ID를 검색합니다."""
        if drive_service is None:
            drive_service = get_drive_service()
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and name contains '{base_name}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def upload_text_to_drive(self, folder_id: str, file_name: str, text: str, drive_service=None) -> None:
        """구글 드라이브의 지정된 폴더에 텍스트 파일을 업로드합니다. 동일 이름의 이전 파일은 삭제합니다."""
        if drive_service is None:
            drive_service = get_drive_service()

        # 기존 동일 이름의 구버전 파일 삭제 (중복 생성 방지)
        try:
            query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
            res = drive_service.files().list(q=query, fields="files(id, name)").execute()
            for old_f in res.get('files', []):
                drive_service.files().delete(fileId=old_f['id']).execute()
        except Exception:
            pass

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, file_name)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(text)
            mime_type = "application/json" if file_name.endswith('.json') else "text/plain"
            if file_name.endswith('.csv'):
                mime_type = "text/csv"
            upload_to_drive(temp_path, folder_id, mime_type=mime_type, drive_service=drive_service)

    def run_pipeline_for_group(
        self,
        base_name: str,
        task_queue: List[Dict[str, Any]],
        cell_update_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """동일 교시(base_name)에 묶인 AI 작업 큐를 선후관계(Phase 1 -> Phase 2)에 따라 실행합니다.

        Args:
            base_name (str): 대상 교시 기본 이름.
            task_queue (List[Dict[str, Any]]): 실행할 작업 명세 목록.
            cell_update_callback (Optional[Callable[[int, int, str], None]], optional): 
                작업 상태 변경 알림 콜백 (row, col, status).
            cancel_checker (Optional[Callable[[], bool]], optional): 작업 취소 여부 판별 콜백.
            progress_callback (Optional[Callable[[int, str], None]], optional): 진행률 알림 콜백.

        Returns:
            bool: 파이프라인 정상 완료 여부.
        """
        def update_cell(row: int, col: int, status: str):
            if cell_update_callback:
                cell_update_callback(row, col, status)

        if not task_queue:
            return True

        total_tasks = len(task_queue)
        self._log(f"🚀 [{base_name}] 총 {total_tasks}개의 AI 작업 파이프라인을 시작합니다...")
        drive_service = get_drive_service()

        try:
            # 1. 대상 폴더 생성 및 이동 (교시당 1회)
            target_folder_id = self.folder_service.ensure_and_organize_lesson_folder(base_name)
            if not target_folder_id:
                self._log(f"❌ {base_name} 대상 폴더 구성에 실패했습니다.")
                for t in task_queue:
                    update_cell(t['row'], t['col'], "ERROR")
                return False

            if cancel_checker and cancel_checker():
                return False

            # 2. 강의자료(PDF OCR) 확보 (교시당 1회)
            lecture_txt_name = f"{base_name}_강의자료.txt"
            pdf_text = self.get_text_from_drive(target_folder_id, lecture_txt_name, drive_service)

            if not pdf_text:
                self._log(f"🔍 [{base_name}] 강의자료.txt가 없습니다. PDF에서 OCR 추출을 시도합니다.")
                pdf_id = self.get_pdf_file_id(target_folder_id, base_name, drive_service)
                if not pdf_id:
                    self._log(f"❌ {base_name} PDF 파일을 찾을 수 없습니다.")
                    for t in task_queue:
                        update_cell(t['row'], t['col'], "ERROR")
                    return False

                with temp_download_from_drive(pdf_id, extension=".pdf", drive_service=drive_service) as temp_pdf:
                    pdf_text = self.pdf_ocr_service.extract_text_with_ocr(str(temp_pdf))
                    if pdf_text:
                        self.upload_text_to_drive(target_folder_id, lecture_txt_name, pdf_text, drive_service)
                    else:
                        self._log(f"❌ [{base_name}] PDF 텍스트 추출에 실패했습니다.")
                        for t in task_queue:
                            update_cell(t['row'], t['col'], "ERROR")
                        return False

            if cancel_checker and cancel_checker():
                return False

            # 3. 음성스크립트 확보 (교시당 1회)
            audio_txt_name = f"{base_name}_음성스크립트.txt"
            audio_text = self.get_text_from_drive(target_folder_id, audio_txt_name, drive_service)
            if not audio_text:
                audio_text = "음성 스크립트 없음"

            # 4. 작업 분류 (Phase 1: 교정 / Phase 2: 요약, Anki)
            phase1_task = None
            phase2_tasks = []

            for t in task_queue:
                if t['task_type'] == "교정":
                    phase1_task = t
                else:
                    phase2_tasks.append(t)

            # 5. Phase 1 (교정) 단독 실행 및 검증
            phase1_success = True
            if phase1_task:
                phase1_success = self._execute_single_task(
                    phase1_task, audio_text, pdf_text, target_folder_id, base_name, cell_update_callback
                )
            else:
                # 큐에 교정이 없는 경우, 드라이브에 최종교정본.txt가 있는지 선행 검사
                corrected_text = self.get_text_from_drive(target_folder_id, f"{base_name}_최종교정본.txt", drive_service)
                if not corrected_text and audio_text == "음성 스크립트 없음":
                    phase1_success = False

            if cancel_checker and cancel_checker():
                return False

            # 6. Phase 2 (요약, Anki) 병렬 실행 - 교정이 성공했을 때만 실행
            if phase2_tasks:
                if not phase1_success:
                    self._log(f"⛔ [{base_name}] 교정 작업이 성공하지 않았으므로 요약 및 Anki 작업을 중단/취소합니다.")
                    for t in phase2_tasks:
                        update_cell(t['row'], t['col'], "ERROR")
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=len(phase2_tasks)) as executor:
                        futures = [
                            executor.submit(
                                self._execute_single_task,
                                t, audio_text, pdf_text, target_folder_id, base_name, cell_update_callback
                            )
                            for t in phase2_tasks
                        ]
                        concurrent.futures.wait(futures)

            if progress_callback:
                progress_callback(100, "")

            self._log(f"🎉 [{base_name}] 모든 AI 작업이 성공적으로 종료되었습니다.")
            return True

        except Exception as e:
            err_msg = traceback.format_exc()
            self._log(f"⚠️ [{base_name}] 파이프라인 예외 발생: {str(e)}")
            print(f"Error details for {base_name}:\n{err_msg}")
            for t in task_queue:
                update_cell(t['row'], t['col'], "ERROR")
            return False

    def _execute_single_task(
        self,
        task: Dict[str, Any],
        audio_text: str,
        pdf_text: str,
        target_folder_id: str,
        base_name: str,
        cell_update_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """단일 AI 태스크(교정, 요약, Anki)를 실행하고 구글 드라이브에 결과물을 저장합니다."""
        def update_cell(row: int, col: int, status: str):
            if cell_update_callback:
                cell_update_callback(row, col, status)

        # 멀티스레드 환경의 안전성을 위해 각 태스크 스레드마다 전용 drive_service 인스턴스 생성
        drive_service = get_drive_service()
        row, col = task['row'], task['col']
        task_type = task['task_type']
        model_name = task['model']

        self._log(f"⏳ [AI 작업 시작] {base_name} - {task_type}")

        try:
            result = None
            if task_type == "교정":
                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.llm_service.correct_script_with_gemini(
                    audio_text, pdf_text, model_name, on_start_callback=on_start
                )
                if result:
                    corrected_text = result.text if hasattr(result, 'text') else str(result)
                    self.upload_text_to_drive(
                        target_folder_id, f"{base_name}_최종교정본.txt", corrected_text, drive_service
                    )

            elif task_type == "요약":
                corrected_text = self.get_text_from_drive(
                    target_folder_id, f"{base_name}_최종교정본.txt", drive_service
                )
                src_text = corrected_text if corrected_text else audio_text

                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.llm_service.key_summary_with_gemini(
                    src_text, pdf_text, model_name, on_start_callback=on_start
                )
                if result:
                    summary_text = result.text if hasattr(result, 'text') else str(result)
                    self.upload_text_to_drive(
                        target_folder_id, f"{base_name}_요약본.txt", summary_text, drive_service
                    )

                    try:
                        self.summary_pdf_service.generate_and_upload_scripted_pdf(
                            base_name, summary_text, src_text, target_folder_id, drive_service
                        )
                    except Exception as pdf_e:
                        self._log(f"❌ {base_name} _scripted.pdf 생성 실패: {str(pdf_e)}")

            elif task_type == "Anki":
                corrected_text = self.get_text_from_drive(
                    target_folder_id, f"{base_name}_최종교정본.txt", drive_service
                )
                src_text = corrected_text if corrected_text else audio_text

                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.llm_service.generate_anki_csv_text(
                    src_text, pdf_text, model_name, on_start_callback=on_start
                )
                if result:
                    csv_text = result.text if hasattr(result, 'text') else str(result)
                    csv_text = csv_text.replace("```csv\n", "").replace("```", "").strip()

                    with tempfile.TemporaryDirectory() as tmpdir:
                        # AnkiGenerationService를 통해 표준 [base_name]_통합본.apkg 빌드
                        apkg_path = self.anki_gen_service.build_apkg_from_csv(base_name, csv_text, tmpdir)

                        # CSV 백업 업로드
                        parsed_dict = self.anki_gen_service._parse_anki_csv_text(csv_text)
                        for d_name, d_lines in parsed_dict.items():
                            if d_lines:
                                text_content = "\n".join(d_lines)
                                self.upload_text_to_drive(
                                    target_folder_id, f"{base_name}_{d_name}.csv", text_content, drive_service
                                )

                        if apkg_path and os.path.exists(apkg_path):
                            filename_to_upload = f"{base_name}_통합본.apkg"
                            try:
                                query = f"'{target_folder_id}' in parents and name = '{filename_to_upload}' and trashed = false"
                                res = drive_service.files().list(q=query, fields="files(id, name)").execute()
                                for old_f in res.get('files', []):
                                    drive_service.files().delete(fileId=old_f['id']).execute()
                            except Exception:
                                pass
                            upload_to_drive(
                                apkg_path, target_folder_id,
                                mime_type="application/apkg",
                                new_file_name=filename_to_upload,
                                drive_service=drive_service
                            )
                            self._log(f"✅ {base_name} Anki {filename_to_upload} 구글 드라이브 업로드 완료")
                        else:
                            raise Exception("Anki .apkg 패키징 실패")

            if result:
                self._log(f"✅ [AI 작업 완료] {base_name} - {task_type}")
                update_cell(row, col, "DONE")
                return True
            else:
                self._log(f"❌ [AI 작업 실패] {base_name} - {task_type}")
                update_cell(row, col, "ERROR")
                return False

        except Exception as e:
            err_msg = traceback.format_exc()
            self._log(f"⚠️ [AI 예외 발생] {base_name} ({task_type}): {str(e)}")
            print(f"Error details for {base_name} - {task_type}:\n{err_msg}")
            update_cell(row, col, "ERROR")
            return False

