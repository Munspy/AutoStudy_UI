"""LLM(대규모 언어 모델) 작업 오케스트레이션 및 프롬프트 관리 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
의학 학습 자료 생성 파이프라인의 핵심 지능(Intelligence) 역할을 수행하며, 
Controller나 Worker 계층으로부터 받은 텍스트 데이터(원본 PDF 내용, Whisper 추출 음성 등)를 
구조화된 프롬프트로 가공하여 하위 통신 유틸리티(`utils/llm_client.py`)를 통해 Gemini API로 전송합니다. 

이 서비스는 API 호출 로직 자체(네트워크, 에러 파싱 등)는 `llm_client`에 위임하고, 
'교정본 생성', '요약본 도출', 'Anki CSV 추출'과 같은 비즈니스 도메인(의학 교육)에 특화된 
시스템 프롬프트 관리와 비동기 태스크 상태 추적(START/DONE/ERROR 로깅)에만 집중하는 단일 책임을 가집니다.
"""
import uuid
import threading
from typing import Dict, Optional, Callable

from base.base_service import BaseService
from utils.llm_client import call_gemini_api, GeminiAPIError
from service.api_key_tracker import api_mgr

# 순수 통신을 담당하는 유틸리티 임포트
from utils.llm_client import call_gemini_api

class LlmService(BaseService):
    """LLM 프롬프트를 구성하고 작업을 할당 및 추적하는 도메인 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 네트워크 통신 로직을 직접 구현하지 않으며 
    오직 의학 도메인 지식이 반영된 프롬프트 조합(Prompt Engineering)과 
    멀티스레드 환경에서의 LLM 작업(Task) 상태 로깅 및 생명주기 관리에 집중합니다. 

    의존성:
    - API 키 동시성 제어 및 쿨타임 관리를 위해 `api_mgr(APIManager)`와 통신합니다[cite: 1].
    - 순수 API 네트워크 통신을 위해 `utils.llm_client.call_gemini_api`를 호출합니다.
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """LlmService 인스턴스를 초기화합니다.

        Args:            logger_callback (Optional[Callable[[str], None]], optional): 비동기 Worker 환경에서 
                발생하는 상태 로그를 메인 UI 스레드로 안전하게 전달하기 위한 콜백 함수. Defaults to None.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        # BaseService 초기화 시 콜백을 등록하여 내부에서 self._log()로 일괄 처리
        super().__init__(logger_callback=logger_callback)
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
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        task_title: str, 
        model_name: str, 
        system_instruction: str, 
        user_prompt: str, 
        task_id: Optional[str] = None,
        on_start_callback=None,
        thinking_level: Optional[str] = None
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
                key_id, api_key, chosen_model = api_mgr.get_available_key(model_name)
            except TimeoutError:
                self._log(f"❌ [AI 팀 - {task_id}] {task_title}: 더 이상 사용 가능한 API Key가 없습니다.")
                self._update_process_status(task_id, task_name, "ERROR")
                return None

            task_name = f"{task_title} ({chosen_model})"
            error_code = None
            try:
                self._log(f"🔄 [AI 팀 - {task_id}] '{chosen_model}' API ({key_id})로 {task_title}을(를) 시작합니다...")
                if on_start_callback:
                    on_start_callback(key_id, chosen_model)
                
                result_text = call_gemini_api(
                    api_key, 
                    chosen_model, 
                    system_instruction, 
                    user_prompt, 
                    temperature=0.1, 
                    thinking_level=thinking_level
                )
                
                self._log(f"✨ [AI 팀 - {task_id}] {task_title} ({key_id}) 성공적으로 완료!")
                self._update_process_status(task_id, task_name, "DONE")
                return result_text
                
            except GeminiAPIError as e:
                error_code = e.code
                self._log(f"⚠️ [AI 팀 - {task_id}] '{key_id}' ({chosen_model}) 오류 [HTTP {error_code}]. 다른 Key/모델로 재시도합니다...")
            except Exception as e:
                error_code = "unknown"
                self._log(f"⚠️ [AI 팀 - {task_id}] '{key_id}' ({chosen_model}) 예외: {str(e)}. 다른 Key/모델로 재시도합니다...")
            finally:
                api_mgr.end_task(key_id, chosen_model, error_code)

    # ==========================================
    # 1. 교정본 생성 (준비물: 음성 스크립트 + 강의록)
    # ==========================================
    def correct_script_with_gemini(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        audio_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None
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

        Returns:
            Optional[str]: 페이지별(`[Slide 00X]`) 맵핑 규칙에 따라 엄격하게 교정된 스크립트 텍스트.
        """
        system_instruction = """당신은 본과 의학 강의 전문 속기사입니다.
목적: Whisper로 추출된 [음성 스크립트]의 발음 오타를 [강의록(PDF) 텍스트]를 참고하여 교정하되, 강사의 실제 발화를 절대 손실 없이 보존하는 것이 최우선입니다.

[최우선 원칙]
1. 교정은 허용되지만, "삭제/생략/재구성"은 금지입니다
2. 원본 음성의 모든 발화는 반드시 유지되어야 합니다.

[엄격한 교정 규칙]
1. 강의록에 명시된 정확한 의학 용어를 사용하여 오타만 수정하세요.
2. 강사가 말하지 않은 내용을 추가하지 마세요. (환각 금지)
3. 문장을 요약하거나 줄이지 마세요.
4. 영어 의학 용어는 영어 그대로 유지하세요.
5. 외래어로 굳어진 단어는 자연스러운 한글로 표현하세요.
6. 임상 기준이 모호하면 '해리슨 내과학' 기준을 따르세요.
7. 강의 흐름과 문장 순서를 절대 변경하지 마세요.
8. 출력 형식이 요구될 경우 엄격히 따르세요.

[스크립트 삭제 절대 금지 항목]
다음과 같은 발화는 "의미 없어 보이더라도 절대 삭제 금지":
- 시험 관련 발언 (예: "시험에 나옵니다", "여기 중요합니다")
- 강조 표현 (예: "진짜 중요", "꼭 기억하세요")
- 잡담 / 사례 / 일화 (예: 연예인, 환자 케이스, 개인 경험)
- 농담, 웃음, 추임새
- 메타 발언 (예: "여기까지 했고", "다음 슬라이드로 넘어가겠습니다")
- 반복 발화 (의도적 강조 가능성 있음)

[페이지 매핑 규칙]
- 강의록에는 '--- 1 Page ---' 와 같은 페이지 구분자가 있습니다. 
- 음성 스크립트의 문맥을 파악하여, 반드시 해당 내용이 속하는 페이지 번호(Slide 001, Slide 002 등) 단위로 나누어 출력해야 합니다.

[출력 전 자기 검증]
출력하기 전 반드시 확인하세요:
- 입력 문장 수와 출력 문장 수가 크게 다르지 않은가?
- 강의록에 없는 내용이 추가되지 않았는가?
- 슬라이드 형식 및 출력 형식이 정확히 지켜졌는가?
- 요약이나 줄어든 문장이 발생하지 않았는가?
- 시험 관련/강조 발화가 삭제되지 않았는가?"""

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
            thinking_level="HIGH"
        )
    # ==========================================
    # 2. 요약본 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def key_summary_with_gemini(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None
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

        Returns:
            Optional[str]: 프롬프트 규칙에 따라 마크다운(Markdown) 형태로 생성된 고품질 요약본 텍스트.
        """
        system_instruction = """[Role & Objective]
너는 의과대학 수석 졸업생이자, 복잡한 의학 정보를 구조화하여 시험 대비와 임상 적용까지 가능하게 만드는 ‘임상 교육 전문가’다.
목표는 제공된 [강의록] + [강의 스크립트]만으로 시험 대비가 가능한 수준의 단권화 노트를 만드는 것이다.

[Core Principles - 반드시 지킬 것]
결론 중심 서술 (요약 금지)
“~을 설명함” 같은 메타 서술 금지.
→ 모든 문장은 반드시 정의, 기전, 진단 기준, 수치, 치료 기준을 직접 포함한 완결형으로 작성.

정보 통합 (슬라이드 + 구두 설명 결합)
강의록 + 스크립트를 분리하지 말고,
→ 교수의 구두 설명(비유, 임상 팁, 주의사항)을 하나의 완성된 문장으로 재구성.

중요도 기반 정보 선택
시험 및 임상적으로 중요한 정보는 절대 누락 금지
저빈도/비핵심 내용은 압축 또는 생략 가능
→ “모든 정보 포함”보다 “중요 정보의 선명도”를 우선

출제 시그널 태깅 [강조]
다음 조건에 해당하면 반드시 [강조] 태그 부착:
“중요하다 / 시험에 나온다 / 외워라 / 자주 틀린다” 등의 직접 표현
반복 언급된 개념
감별이 중요한 포인트
수치, cut-off, 진단 기준, 약물 선택 기준

전문성 유지
의학 용어는 한글 + 영어 병기 (예: 급성 췌장염, acute pancreatitis)

[Tasks & Output Format]
1. 📑 Deep-dive 상세 단권화 노트
해당 강의만으로 시험 대비가 가능하도록 정리
반드시 포함:
정의 (Definition)
병태생리 (Pathophysiology: 원인 → 변화 → 결과)
진단 기준 (수치, cut-off 포함)
검사 선택 기준 (왜 이 검사를 하는지)
치료 (1차 선택, 금기, 단계별 접근)
애매한 표현 금지 (e.g., “높다” → 수치로 명시)

2. ⚖️ 감별 진단 & High-yield 정리
(1) 감별 진단 비교표 (Table)
헷갈리는 질환들을 반드시 표로 비교
포함 항목: 원인, 핵심 증상, 결정적 검사 소견, 치료 차이
(2) [강조] 내용 모아서 재정리
[강조] 태그가 붙은 문장만 따로 모아서 요약 → 시험 직전 복습용

3. 🛣️ 실전 임상 Decision Flow
다음 구조로 작성하되, 분기 조건(if stable / if positive 등) 반드시 포함:
Primary Action (첫 대응)
Best Initial Test (가장 먼저 할 검사)
Conditional Branch (상태에 따른 분기)
Confirmatory Test (확진 검사)
Definitive Treatment (최종 치료)
→ 실제 문제 풀이 흐름처럼 “의사 사고 과정”을 재현할 것"""

        user_prompt = f"""[강의록(PDF) 텍스트]
{pdf_text}

======================

[음성 스크립트]
{corrected_text}

위 데이터를 바탕으로 System Instruction에 명시된 결과물을 출력해 줘."""

        return self._execute_llm_task("Gemini 요약 작업", model_name, system_instruction, user_prompt, task_id, on_start_callback)

    # ==========================================
    # 3. Anki 데이터 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def generate_anki_csv_text(
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None,
        on_start_callback=None
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

        Returns:
            Optional[str]: 마크다운 코드블록 마커(````csv`)가 제거된 순수한 4열 CSV 문자열 텍스트 데이터.
        """
        system_instruction = """너는 의대생의 학습을 돕는 최고 수준의 의학 튜터야. 내가 제공하는 [강의록 텍스트]를 바탕으로, 복습 및 암기를 위한 Anki 카드를 생성해 줘.

[절대 규칙 - 엄수할 것]
1. 내용의 출처: 철저하게 [강의록 텍스트]를 1순위 기준으로 삼아라. 일반적인 의학 지식(해리슨 등)과 강의록 내용이 충돌할 경우, 무조건 강의록을 우선시해라.
2. 환각 금지: 강의록에 없는 외부 지식을 임의로 덧붙이거나 지어내지 마라.
3. 출력 포맷: 무조건 파이프(|) 기호로 구분된 4열 CSV 포맷으로 출력하라. (형식: 카드타입|필드1(질문/빈칸본문)|필드2(정답/해설)|태그)
4. 텍스트 내 파이프(|) 기호 사용 절대 금지: 내용 안에 파이프 기호가 들어가면 시스템이 고장난다. 줄바꿈은 <br><br>를 사용하라.
5. 강조할 핵심 키워드는 <b>키워드</b> 또는 **키워드**로 볼드 처리하라.
6. [이미지 처리]: 해부학적 위치, 영상의학적 소견(CT, X-ray, 심전도), 슬라이드 표 등 시각적 자료가 필요한 경우, 필드1이나 필드2의 적절한 위치에 `[이미지 삽입 필요: (어떤 이미지인지 구체적인 설명)]` 태그를 삽입하라.
7. 불필요한 말 금지: 인사말이나 설명 없이 오직 CSV 데이터만 출력하라.

[정보 우선순위]
강의록 > 강의 스크립트 > 일반 의학 지식
강의록에 없는 내용 추가 금지. 강의록과 교과서 충돌 시 강의록 우선.

[좋은 Anki 카드 기준]
- Atomic: 하나의 카드에 한두개의 개념
- Testable: 질문만 보고 답이 하나로 수렴
- High-yield: 시험에 나올 내용만
- Minimal: 군더더기 제거
- Confusion-prone: 헷갈리는 개념 우선
- 5초 안에 "알거나 / 모르거나" 판단 가능

[카드 생성 우선순위]
1순위: 교수가 "시험에 나온다", "중요하다" 명시한 내용
2순위: 진단 기준 / 1st line 치료 / 수치
3순위: 감별 포인트 (A vs B)
4순위: 병태생리 흐름
5순위: 기타 고빈도 fact
→ 5순위 이하 내용은 카드 만들지 말 것

[카드 타입 선택 규칙]
- 단일 fact → Basic
- 나열 / 기전 → Cloze
- 임상 판단 → MCQ

[금지]
- 애매한 질문
- 복수 정답 가능 질문
- 문장 복붙
- 의미 없는 trivia

[해설 작성 기준]
- 단순 정답 반복 금지
- "왜 이게 정답인지" 또는 "헷갈리는 포인트" 1~2줄 추가
- 예: 정답만 쓰는 해설 ✗ → "~이기 때문에 ~~이며, ~~와 감별 필요" ✓

▶ Type 1: Basic (일반 Q&A)
- 개수 목표 : 10~15장
대상: 1:1 매핑이 명확한 fact
- 정의, 1st line 치료, 특징적 단일 소견, 수치/기준값

[좋은 질문 기준]
✓ 질문만 보고 답이 하나로 수렴
✓ 2초 안에 "알거나 / 모르거나" 판단 가능
✗ "~에 대해 설명하라" 금지
✗ 교수가 강조한 내용 우선, trivia 배제

[해설 작성 기준]
- 단순 정답 반복 금지
- "왜 이게 정답인지" 또는 "헷갈리는 포인트" 1~2줄 추가
- 예: 정답만 쓰는 해설 ✗ → "~이기 때문에 ~~이며, ~~와 감별 필요" ✓

- 출력 예시: Basic|OOO의 가장 흔한 원인균은?|<b>정답: 폐렴구균</b><br><br>해설: (필요시 짧은 해설)|#호흡기 #원인균

▶ Type 2: Cloze (빈칸 뚫기)
대상: 순서/흐름/나열이 있는 고빈도 내용만
- 진단 기준 세트, 병태생리 연쇄, 치료 단계

[작성 규칙]
- {{{{c1::답}}}}, {{{{c2::답}}}} Cloze 문법 정확히 사용
- 같이 외워야 할 묶음 → 같은 번호(c1)
- 따로 외워야 할 것 → 다른 번호(c1, c2, c3...)
- 빈칸 수: 카드 1개당 2~5개 권장 (1개는 Basic으로, 6개 이상은 분리)
- 저빈도 나열(임상에서 잘 안 쓰는 것) → Cloze 만들지 말 것

- 개수 목표 : 8~12장
- 작성 규칙: Anki의 Cloze 문법인 {{{{c1::정답}}}}, {{{{c2::정답}}}}을 정확히 사용하라. 연관된 개념을 한 번에 외워야 하면 같은 번호 {{{{c1::A}}}}와 {{{{c1::B}}}}를 쓰고, 따로 외워야 하면 번호를 나누어라.
- 출력 예시: Cloze|대동맥판 협착증(AS)의 3대 증상은 {{{{c1::Syncope}}}}, {{{{c2::Angina}}}}, {{{{c3::Dyspnea}}}} 이다.

▶ Type 3: MCQ (5지선다형 객관식)
대상: 임상 판단이 필요한 케이스, 감별이 중요한 상황

[문제 품질 기준]
- 실제 시험에 나올 법한 임상 vignette 형식 권장
- 보기 5개: 정답 1개 + 그럴듯한 오답(plausible distractor) 4개
- 오답은 "왜 틀렸는지 설명 가능한 것"으로 구성
  예) 비슷한 질환, 같은 계열 약물, 비슷한 수치 등
- "명백히 틀린 보기"(전혀 관련 없는 것) 사용 금지

[해설 기준]
- 정답 이유 + 주요 오답 1~2개의 배제 이유 포함
- 예: "3번이 정답인 이유는 ~. 2번(○○)은 ~의 경우에 해당."

- 개수 목표 : 5~10장
- 출력 예시: MCQ|문제 내용<br><br>1) 보기1<br>2) 보기2...|<b>정답: 3번</b><br><br>해설: (명확한 근거)|#객관식 #임상

[생성 프로세스 - 반드시 따를 것]
1. 강의록에서 핵심 개념을 추출
2. 중요도 순으로 정렬
3. 각 개념을 가장 적합한 카드 타입으로 변환
4. 최종 카드 생성"""
        
        user_prompt = f"""[강의록 텍스트]
{pdf_text}
[강의 스크립트]
{corrected_text}"""

        result_text = self._execute_llm_task("Anki CSV 데이터 생성", model_name, system_instruction, user_prompt, task_id, on_start_callback)        
        if result_text:
            return result_text.replace("```csv", "").replace("```", "").strip()
        return None