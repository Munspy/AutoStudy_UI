from __future__ import annotations
from typing import TYPE_CHECKING
"""LLM(대규모 언어 모델) 작업 오케스트레이션 및 프롬프트 관리 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
의학 학습 자료 생성 파이프라인의 핵심 지능(Intelligence) 역할을 수행하며, 
Controller나 Worker 계층으로부터 받은 텍스트 데이터(원본 PDF 내용, Whisper 추출 음성 등)를 
구조화된 프롬프트로 가공하여 하위 통신 유틸리티(`utils/llm_client.py`)를 통해 Gemini API로 전송합니다. 

이 서비스는 API 호출 로직 자체(네트워크, 에러 파싱 등)는 `llm_client`에 위임하고, 
'교정본 생성', '요약본 도출', 'Anki CSV 추출'과 같은 비즈니스 도메인(의학 교육)에 특화된 
시스템 프롬프트 관리와 비동기 태스크 상태 추적(START/DONE/ERROR 로깅)에만 집중하는 단일 책임을 가집니다.
"""
import threading
import uuid
from typing import Callable, Dict, Optional

from base.base_service import BaseService
from core.config import Config
from core.prompts import PROMPT_TRANSCRIPT_CORRECTION, PROMPT_ANKI_GENERATION, PROMPT_SUMMARY_GENERATION
# 순수 통신을 담당하는 유틸리티 임포트
from core.exceptions import GeminiAPIError


class LlmService(BaseService):
    """LLM 프롬프트를 구성하고 작업을 할당 및 추적하는 도메인 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 네트워크 통신 로직을 직접 구현하지 않으며 
    오직 의학 도메인 지식이 반영된 프롬프트 조합(Prompt Engineering)과 
    멀티스레드 환경에서의 LLM 작업(Task) 상태 로깅 및 생명주기 관리에 집중합니다. 

    의존성:
    - API 키 동시성 제어 및 쿨타임 관리를 위해 `api_mgr(APIManager)`와 통신합니다[cite: 1].
    - 순수 API 네트워크 통신을 위해 `infrastructure.llm_client.GeminiLlmClient`를 호출합니다.
    """
    def __init__(self) -> None:
        """LlmService 인스턴스를 초기화합니다."""
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        super().__init__()
        self.active_processes: Dict[str, str] = {}
        self.process_lock = threading.Lock()

    def _update_process_status(self, task_id: str, task_name: str, status: str = "START") -> None:
        """내부적으로 진행 중인 동시다발적인 비동기 AI 태스크의 상태를 추적하고 로깅합니다.

        여러 파일이 동시에 병렬(Worker Pool)로 Gemini 파이프라인을 통과할 때, 
        어떤 태스크가 현재 진행 중인지, 성공했는지, 실패했는지를 파악하여 UI(로그 창)에 반영하기 위한 
        스레드 안전(Thread-safe) 상태 관리 로직입니다. 

        Args:            task_id (str): 작업을 고유하게 식별하는 UUID 문자열.
            task_name (str): 수행 중인 작업의 이름과 모델 정보를 포함한 문자열.
            status (str, optional): 작업의 현재 상태 플래그 ("START", "DONE", "ERROR"). Defaults to "START".
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        with self.process_lock:
            if status == "START":
                self.active_processes[task_id] = task_name
                msg = f"🟢 [START] 작업 시작 - {task_name} (ID: {task_id})"
            elif status in ["DONE", "ERROR"]:
                if task_id in self.active_processes:
                    del self.active_processes[task_id]
                icon = "✅" if status == "DONE" else "❌"
                msg = f"{icon} [{status}] 작업 종료 - {task_name} (ID: {task_id})"
            
            # 별도의 print()나 파라미터 호출 없이 _log로 통일
            self._log(msg)
                
            summary = f"📊 [현재 실행 중인 전체 LLM 작업: {len(self.active_processes)}개]"
            self._log(summary)

    def _execute_llm_task(
        self, 
        task_title: str, 
        model_name: str, 
        system_instruction: str, 
        user_prompt: str, 
        task_id: Optional[str] = None,
        on_start_callback=None,
        thinking_level: Optional[str] = None,
        cancel_checker: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """LLM 호출 시 반복되는 락킹, 로깅 및 예외 처리를 전담하는 내부 템플릿(Wrapper) 메서드입니다.        개별 비즈니스 로직(교정본, 요약본 등)이 직접 API를 호출하고 예외 처리를 중복 작성하는 것을 방지합니다. 
        이 메서드는 API 호출 전 `api_mgr`로부터 사용 가능한 API 키를 안전하게 대여(Checkout) 받고, 
        `llm_client`를 통해 통신을 시도하며, 작업 완료(또는 실패) 시 
        성공 여부 및 에러 코드를 포함하여 키를 반드시 반납(Checkin)하도록 `finally` 블록으로 강제합니다. 

        Args:
            task_title (str): 로깅 및 사용자 안내 목적의 작업 제목 (예: "Gemini 요약 작업").
            model_name (str): 사용할 Gemini 모델 이름 (예: "gemini-2.5-flash").
            system_instruction (str): LLM의 페르소나 및 출력 형식을 정의하는 시스템 프롬프트.
            user_prompt (str): 모델에 전달할 실제 데이터가 담긴 사용자 프롬프트.
            task_id (Optional[str], optional): 작업 추적용 고유 ID. 입력하지 않으면 자동으로 UUID 8자리를 생성합니다.
            on_start_callback: 작업 시작 시 호출될 콜백.
            thinking_level (Optional[str], optional): Thinking Level 설정값 ("HIGH", "MEDIUM", "LOW" 등).
            cancel_checker (Optional[Callable[[], bool]], optional): 작업 취소 여부 판별 콜백.

        Returns:
            Optional[str]: LLM이 생성한 응답 텍스트. 통신 에러나 예기치 못한 시스템 오류 발생 시 None 반환.
        """
        if task_id is None: 
            task_id = str(uuid.uuid4())[:8]
            
        model_display = ', '.join(model_name) if isinstance(model_name, list) else model_name
        task_name = f"{task_title} ({model_display})"
        self._update_process_status(task_id, task_name, "START")
        
        while True:
            try:
                key_id, api_key, chosen_model = self.app.api_mgr.get_available_key(model_name, cancel_checker=cancel_checker)
            except TimeoutError:
                self._log(f"❌ [AI 팀 - {task_id}] {task_title}: 더 이상 사용 가능한 API Key가 없습니다.")
                self._update_process_status(task_id, task_name, "ERROR")
                return None
            except InterruptedError:
                self._log(f"⚠️ [AI 팀 - {task_id}] {task_title}: 대기 중 작업이 취소되었습니다.")
                self._update_process_status(task_id, task_name, "ERROR")
                return None

            task_name = f"{task_title} ({chosen_model})"
            error_code = None
            try:
                self._log(f"🔄 [AI 팀 - {task_id}] '{chosen_model}' API ({key_id})로 {task_title}을(를) 시작합니다...")
                if on_start_callback:
                    on_start_callback(key_id, chosen_model)
                
                result_text = self.app.llm_client.call_api(
                    api_key=api_key, 
                    model_name=chosen_model, 
                    system_instruction=system_instruction, 
                    user_prompt=user_prompt, 
                    temperature=0.1, 
                    thinking_level=thinking_level
                )
                
                self._log(f"✨ [AI 팀 - {task_id}] {task_title} ({key_id}) 성공적으로 완료!")
                self._update_process_status(task_id, task_name, "DONE")
                return result_text
                
            except GeminiAPIError as e:
                error_code = e.code
                if "503" in str(error_code):
                    self._log(f"🚨 [AI 팀 - {task_id}] '{chosen_model}' 모델에서 503 (Service Unavailable) 발생! 해당 모델을 {Config.MODEL_LOCK_DURATION_503:.0f}초 동안 전체 잠금 처리하고 다른 모델로 재시도합니다...")
                else:
                    self._log(f"⚠️ [AI 팀 - {task_id}] '{key_id}' ({chosen_model}) 오류 [HTTP {error_code}]. 다른 Key/모델로 재시도합니다...")
            except Exception as e:
                error_code = "unknown"
                self._log(f"⚠️ [AI 팀 - {task_id}] '{key_id}' ({chosen_model}) 예외: {str(e)}. 다른 Key/모델로 재시도합니다...")
            finally:
                self.app.api_mgr.end_task(key_id, chosen_model, error_code)

    # ==========================================
    # 1. 교정본 생성 (준비물: 음성 스크립트 + 강의록)
    # ==========================================
    def correct_script_with_gemini(
        self, 
        audio_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None,
        cancel_checker: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """음성 스크립트와 강의록을 비교하여 강사의 발화를 보존하며 오타를 교정하는 비즈니스 메서드입니다.        Whisper AI가 음성을 텍스트로 변환할 때 흔히 발생하는 전문 의학 용어의 오인식(Hallucination)을 
        해결하기 위해 설계되었습니다. 원본 PDF(강의록) 텍스트를 Ground Truth(참조 데이터)로 제공하여 
        LLM이 발음이 유사한 단어를 문맥과 강의록에 맞게 추론하여 교정하도록 프롬프트 엔지니어링이 적용되어 있습니다. 
        강사의 팁이나 중요도(시험 관련) 발언이 훼손되지 않도록 엄격한 '삭제/생략 금지' 규칙이 포함되어 있습니다.

        Args:
            audio_text (str): Whisper AI를 통해 추출된 불완전한 원본 음성 스크립트.
            pdf_text (str): PDF에서 추출된 강의록 텍스트 (참조용 정답지 역할).
            model_name (str): 사용할 모델 이름.
            task_id (Optional[str], optional): 작업 식별용 ID. Defaults to None.
            on_start_callback: 작업 시작 콜백.
            cancel_checker: 작업 취소 여부 판별 콜백.

        Returns:
            Optional[str]: 페이지별(`[Slide 00X]`) 맵핑 규칙에 따라 엄격하게 교정된 스크립트 텍스트.
        """
        system_instruction = PROMPT_TRANSCRIPT_CORRECTION

        user_prompt = f"""[강의록(PDF) 텍스트]
{pdf_text}

======================

[음성 스크립트]
{audio_text}

엄격한 출력 형식:
[Slide 001]
(1페이지에 해당하는 교정된 스크립트 내용)
[Slide 002]
(2페이지에 해당하는 교정된 스크립트 내용)
...
(반드시 PDF에 존재하는 페이지 수만큼 숫자를 증가시키며 매핑하세요. 텍스트가 없는 슬라이드는 '[Slide 00X]\\n(내용 없음)' 으로 표기하세요.)"""

        return self._execute_llm_task(
            "Gemini 교정 작업", 
            model_name, 
            system_instruction, 
            user_prompt, 
            task_id, 
            on_start_callback, 
            thinking_level="HIGH",
            cancel_checker=cancel_checker
        )
    # ==========================================
    # 2. 요약본 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def key_summary_with_gemini(
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None,
        cancel_checker: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """강의록과 교정본을 바탕으로 핵심 단권화(Summary) 노트를 생성하는 비즈니스 메서드입니다.        교정이 완료된 스크립트와 강의록 텍스트를 입력받아, 의학 교육 전문가 수준의 
        구조화된 핵심 요약본을 도출합니다. 단순 요약이 아닌, 시험 출제 시그널 식별, 감별 진단 표 구성, 
        임상적 의사 결정 흐름(Decision Flow) 작성을 강제하는 고도화된 프롬프트가 적용되어 
        학습자의 실전 지식 향상을 돕습니다.

        Args:
            corrected_text (str): 선행 작업(correct_script)을 통해 오타가 수정된 깨끗한 음성 스크립트.
            pdf_text (str): 참조용 강의록 원문 텍스트.
            model_name (str): 사용할 모델 이름.
            task_id (Optional[str], optional): 작업 식별용 ID. Defaults to None.
            on_start_callback: 작업 시작 콜백.
            cancel_checker: 작업 취소 여부 판별 콜백.

        Returns:
            Optional[str]: 프롬프트 규칙에 따라 마크다운(Markdown) 형태로 생성된 고품질 요약본 텍스트.
        """
        system_instruction = PROMPT_SUMMARY_GENERATION

        user_prompt = f"""[강의록(PDF) 텍스트]
{pdf_text}

======================

[음성 스크립트]
{corrected_text}

위 데이터를 바탕으로 System Instruction에 명시된 결과물을 출력해 줘."""

        return self._execute_llm_task(
            "Gemini 요약 작업", 
            model_name, 
            system_instruction, 
            user_prompt, 
            task_id, 
            on_start_callback, 
            thinking_level="HIGH",
            cancel_checker=cancel_checker
        )

    # ==========================================
    # 3. Anki 데이터 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def generate_anki_csv_text(
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None,
        cancel_checker: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """강의록과 교정본을 바탕으로 Anki 카드 생성을 위한 파이프(|) 구분 CSV 원시 텍스트를 생성합니다.        AnkiGenerationService(Anki 팀)가 `.apkg` 파일을 패키징하기 전, 필요한 핵심 데이터를 LLM을 통해 
        추출해내는 전처리 단계입니다. 프롬프트 내에 Basic, Cloze(빈칸뚫기), MCQ(객관식) 카드를 생성하는 
        구체적인 문법(`{{c1::}}` 등)과 CSV 포맷(`|` 구분)을 엄격하게 제한하여 기계가 쉽게 파싱할 수 있는 
        형태로 출력하도록 통제합니다.

        Args:
            corrected_text (str): 선행 작업으로 오타가 교정된 깨끗한 음성 스크립트 텍스트.
            pdf_text (str): 참조용 강의록 원문 텍스트.
            model_name (str): 사용할 모델 이름.
            task_id (Optional[str], optional): 작업 식별용 ID. Defaults to None.
            on_start_callback: 작업 시작 콜백.
            cancel_checker: 작업 취소 여부 판별 콜백.

        Returns:
            Optional[str]: 마크다운 코드블록 마커(````csv`)가 제거된 순수한 4열 CSV 문자열 텍스트 데이터.
        """
        system_instruction = PROMPT_ANKI_GENERATION
        
        user_prompt = f"""[강의록 텍스트]
{pdf_text}
[강의 스크립트]
{corrected_text}"""

        result_text = self._execute_llm_task("Anki CSV 데이터 생성", model_name, system_instruction, user_prompt, task_id, on_start_callback, cancel_checker=cancel_checker)        
        if result_text:
            return result_text.replace("```csv", "").replace("```", "").strip()
        return None