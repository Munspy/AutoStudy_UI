from __future__ import annotations
from typing import TYPE_CHECKING
"""AI 파이프라인 오케스트레이션 및 처리 서비스 모듈.

이 모듈은 AutoStudy_UI의 Service 계층에 속하며,
단일 교시(Lesson)에 대한 AI 작업(교정, 요약, Anki) 파이프라인의 전체 실행 흐름을 제어합니다.
폴더 관리, 강의자료 OCR 텍스트 확보, 스크립트 취득, 단계별 의존성(교정 -> 요약/Anki 병렬) 제어
및 결과물의 Google Drive 업로드를 전담합니다.
"""

import concurrent.futures
import os
import tempfile
import traceback
from typing import Any, Callable, Dict, List, Optional

from base.base_service import BaseService
from core.constants import FileSuffix


class AiPipelineService(BaseService):
    """교시별 AI 파이프라인 작업의 실행과 드라이브 동기화를 전담하는 오케스트레이션 서비스 클래스."""

    def __init__(self):
        """AiPipelineService 인스턴스를 초기화합니다."""
        super().__init__()
    def get_text_from_drive(self, folder_id: str, file_name: str) -> Optional[str]:
        """구글 드라이브의 특정 폴더에서 텍스트 파일 내용을 읽어 반환합니다."""
        files = self.app.drive_client.get_all_drive_files(folder_id, name_filter=file_name)
        if not files:
            return None
        file_id = files[0]['id']
        with self.app.drive_client.in_memory_download_from_drive(file_id) as buffer:
            return buffer.read().decode('utf-8', errors='replace')

    def get_pdf_file_id(self, folder_id: str, base_name: str) -> Optional[str]:
        """구글 드라이브의 대상 폴더 내에서 PDF 파일의 ID를 검색합니다."""
        files = self.app.drive_client.get_all_drive_files(folder_id, name_filter=base_name)
        pdf_files = [f for f in files if f.get('name', '').lower().endswith('.pdf')]
        return pdf_files[0]['id'] if pdf_files else None

    def upload_text_to_drive(self, folder_id: str, file_name: str, text: str) -> None:
        """구글 드라이브의 지정된 폴더에 텍스트 파일을 업로드합니다. 업로드 성공 시 동일 이름의 이전 파일은 삭제합니다."""
        # 기존 동일 이름의 구버전 파일 ID 확보 (업로드 전)
        old_file_ids = []
        try:
            old_files = self.app.drive_client.get_all_drive_files(folder_id, name_filter=file_name)
            old_file_ids = [f['id'] for f in old_files if f.get('name') == file_name]
        except Exception as e:
            self._log(f"⚠️ 처리 중 무시된 오류: {e}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, file_name)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(text)
            mime_type = "application/json" if file_name.endswith('.json') else "text/plain"
            if file_name.endswith('.csv'):
                mime_type = "text/csv"
                
            # 새 파일 업로드
            self.app.drive_client.upload_to_drive(temp_path, folder_id, mime_type=mime_type)
            
        # 업로드 성공 후 기존 파일들 영구 삭제 (또는 휴지통 이동)
        for old_id in old_file_ids:
            try:
                self.app.drive_client.delete_drive_file(old_id)
            except Exception as e:
                self._log(f"⚠️ 처리 중 무시된 오류: {e}")

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

        try:
            # 1. 대상 폴더 생성 및 이동 (교시당 1회)
            target_folder_id = self.app.folder_mgmt.ensure_and_organize_lesson_folder(base_name)
            if not target_folder_id:
                self._log(f"❌ {base_name} 대상 폴더 구성에 실패했습니다.")
                for t in task_queue:
                    update_cell(t['row'], t['col'], "ERROR")
                return False

            if cancel_checker and cancel_checker():
                return False

            # 2. 강의자료(PDF OCR) 확보 (교시당 1회)
            lecture_txt_name = f"{base_name}_강의자료.txt"
            pdf_text = self.get_text_from_drive(target_folder_id, lecture_txt_name)

            if not pdf_text:
                self._log(f"🔍 [{base_name}] 강의자료.txt가 없습니다. PDF에서 OCR 추출을 시도합니다.")
                pdf_id = self.get_pdf_file_id(target_folder_id, base_name)
                if not pdf_id:
                    self._log(f"❌ {base_name} PDF 파일을 찾을 수 없습니다.")
                    for t in task_queue:
                        update_cell(t['row'], t['col'], "ERROR")
                    return False

                with self.app.drive_client.temp_download_from_drive(pdf_id, extension=".pdf") as temp_pdf:
                    pdf_text = self.app.pdf_ocr.extract_text_with_ocr(str(temp_pdf))
                    if pdf_text:
                        self.upload_text_to_drive(target_folder_id, lecture_txt_name, pdf_text)
                    else:
                        self._log(f"❌ [{base_name}] PDF 텍스트 추출에 실패했습니다.")
                        for t in task_queue:
                            update_cell(t['row'], t['col'], "ERROR")
                        return False

            if cancel_checker and cancel_checker():
                return False

            # 3. 음성스크립트 확보 (교시당 1회)
            audio_txt_name = f"{base_name}_{FileSuffix.TRANSCRIPT_RAW}.txt"
            audio_text = self.get_text_from_drive(target_folder_id, audio_txt_name)
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
                    phase1_task, audio_text, pdf_text, target_folder_id, base_name, cell_update_callback, cancel_checker
                )
            else:
                # 큐에 교정이 없는 경우, 드라이브에 최종교정본.txt가 있는지 선행 검사
                corrected_text = self.get_text_from_drive(target_folder_id, f"{base_name}_{FileSuffix.TRANSCRIPT_CORRECTED}.txt")
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
                                t, audio_text, pdf_text, target_folder_id, base_name, cell_update_callback, cancel_checker
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
        cell_update_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_checker: Optional[Callable[[], bool]] = None
    ) -> bool:
        """단일 AI 태스크(교정, 요약, Anki)를 실행하고 구글 드라이브에 결과물을 저장합니다."""
        if cancel_checker and cancel_checker():
            self._log(f"⚠️ [AI 작업 취소됨] {base_name} - {task['task_type']}")
            return False

        def update_cell(row: int, col: int, status: str):
            if cell_update_callback:
                cell_update_callback(row, col, status)

        # 멀티스레드 환경의 안전성을 위해 각 태스크 스레드마다 전용 drive_service 인스턴스 생성
        
        row, col = task['row'], task['col']
        task_type = task['task_type']
        model_name = task['model']

        self._log(f"⏳ [AI 작업 시작] {base_name} - {task_type}")

        try:
            result = None
            if task_type == "교정":
                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.app.llm.correct_script_with_gemini(
                    audio_text, pdf_text, model_name, on_start_callback=on_start, cancel_checker=cancel_checker
                )
                if result:
                    corrected_text = getattr(result, 'text', str(result))
                    self.upload_text_to_drive(
                        target_folder_id, f"{base_name}_{FileSuffix.TRANSCRIPT_CORRECTED}.txt", corrected_text)

            elif task_type == "요약":
                corrected_text = self.get_text_from_drive(
                    target_folder_id, f"{base_name}_{FileSuffix.TRANSCRIPT_CORRECTED}.txt")
                src_text = corrected_text if corrected_text else audio_text

                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.app.llm.key_summary_with_gemini(
                    src_text, pdf_text, model_name, on_start_callback=on_start, cancel_checker=cancel_checker
                )
                if result:
                    summary_text = getattr(result, 'text', str(result))
                    self.upload_text_to_drive(
                        target_folder_id, f"{base_name}_{FileSuffix.SUMMARY_TXT}.txt", summary_text)

                    try:
                        if corrected_text:
                            self.app.summary_pdf.generate_and_upload_scripted_pdf(
                                base_name, summary_text, corrected_text, target_folder_id)
                        else:
                            self._log(f"⚠️ [{base_name}] 최종교정본이 없어 _scripted.pdf 생성을 건너뜁니다.")
                    except Exception as pdf_e:
                        self._log(f"❌ {base_name} _scripted.pdf 생성 실패: {str(pdf_e)}")

            elif task_type == "Anki":
                corrected_text = self.get_text_from_drive(
                    target_folder_id, f"{base_name}_{FileSuffix.TRANSCRIPT_CORRECTED}.txt")
                src_text = corrected_text if corrected_text else audio_text

                def on_start(key, mod):
                    update_cell(row, col, f"START::{key}::{mod}")

                result = self.app.llm.generate_anki_csv_text(
                    src_text, pdf_text, model_name, on_start_callback=on_start, cancel_checker=cancel_checker
                )
                if result:
                    csv_text = getattr(result, 'text', str(result))
                    csv_text = csv_text.replace("```csv\n", "").replace("```", "").strip()

                    with tempfile.TemporaryDirectory() as tmpdir:
                        # AnkiGenerationService를 통해 표준 [base_name]_통합본.apkg 빌드
                        apkg_path = self.app.anki_gen.build_apkg_from_csv(base_name, csv_text, tmpdir)

                        # CSV 백업 업로드
                        parsed_dict = self.app.anki_gen._parse_anki_csv_text(csv_text)
                        for d_name, d_lines in parsed_dict.items():
                            if d_lines:
                                text_content = "\n".join(d_lines)
                                self.upload_text_to_drive(
                                    target_folder_id, f"{base_name}_{d_name}.csv", text_content)

                        if apkg_path and os.path.exists(apkg_path):
                            filename_to_upload = f"{base_name}_통합본.apkg"
                            try:
                                old_files = self.app.drive_client.get_all_drive_files(target_folder_id, name_filter=filename_to_upload)
                                for old_f in old_files:
                                    if old_f.get('name') == filename_to_upload:
                                        self.app.drive_client.delete_drive_file(old_f['id'])
                            except Exception as e:
                                self._log(f"⚠️ 처리 중 무시된 오류: {e}")
                            self.app.drive_client.upload_to_drive(
                                apkg_path, target_folder_id,
                                mime_type="application/apkg",
                                new_file_name=filename_to_upload,
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

