# service/llm_service.py
import time
import uuid
import threading
from typing import Dict, Optional, Callable

from base.base_service import BaseService
from utils.llm_client import call_gemini_api, GeminiAPIError
from service.api_key_tracker import api_mgr

# 순수 통신을 담당하는 유틸리티 임포트
from utils.llm_client import call_gemini_api

class LlmService(BaseService):
    """
    LLM 프롬프트를 구성하고 작업을 할당 및 추적하는 도메인 서비스입니다.
    실제 프롬프트를 조립하여 utils.llm_client를 통해 API 호출을 수행합니다.
    """
    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        # BaseService 초기화 시 콜백을 등록하여 내부에서 self._log()로 일괄 처리
        super().__init__(logger_callback=logger_callback)
        self.active_processes: Dict[str, str] = {}
        self.process_lock = threading.Lock()

    def _update_process_status(self, task_id: str, task_name: str, status: str = "START") -> None:
        """내부적으로 진행 중인 AI 태스크의 상태를 로깅합니다."""
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
        task_id: Optional[str] = None
    ) -> Optional[str]:
        """LLM 호출 시 반복되는 상태 로깅 및 예외 처리를 전담하는 내부 래퍼입니다."""
        if task_id is None: 
            task_id = str(uuid.uuid4())[:8]
            
        task_name = f"{task_title} ({model_name})"
        self._update_process_status(task_id, task_name, "START")
        
        # 1. 사용 가능한 키 확보 (대기 발생 가능)
        key_id, api_key = api_mgr.get_available_key(model_name)
        error_code = None
        
        try:
            self._log(f"🔄 [AI 팀 - {task_id}] '{model_name}' API로 {task_title}을(를) 시작합니다...")
            
            # 2. 통신 모듈에는 키 문자열만 넘겨줌
            result_text = call_gemini_api(api_key, model_name, system_instruction, user_prompt, temperature=0.1)
            
            self._log(f"✨ [AI 팀 - {task_id}] {task_title} 성공적으로 완료!")
            self._update_process_status(task_id, task_name, "DONE")
            return result_text
            
        except GeminiAPIError as e:
            # 3-1. 통신 에러 발생 시 커스텀 예외에서 코드 추출
            error_code = e.code
            self._log(f"❌ [AI 팀 - {task_id}] {task_title} 오류 [HTTP {error_code}]: {str(e)}")
            self._update_process_status(task_id, task_name, "ERROR")
            return None
            
        except Exception as e:
            # 3-2. 그 외 예상치 못한 에러
            error_code = "unknown"
            self._log(f"❌ [AI 팀 - {task_id}] {task_title} 시스템 오류: {str(e)}")
            self._update_process_status(task_id, task_name, "ERROR")
            return None
            
        finally:
            # 4. 성공/실패 여부와 관계없이 키를 반납 (쿨타임 타이머 시작)
            api_mgr.end_task(key_id, model_name, error_code)

    # ==========================================
    # 1. 교정본 생성 (준비물: 음성 스크립트 + 강의록)
    # ==========================================
    def correct_script_with_gemini(
        self, 
        audio_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None
    ) -> Optional[str]:
        """음성 스크립트와 강의록을 비교하여 강사의 발화를 보존하며 오타를 교정합니다."""
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

        return self._execute_llm_task("Gemini 교정 작업", model_name, system_instruction, user_prompt, task_id)
    # ==========================================
    # 2. 요약본 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def key_summary_with_gemini(
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None
    ) -> Optional[str]:
        """강의록과 교정본을 바탕으로 핵심 단권화 노트를 생성합니다."""
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

        return self._execute_llm_task("Gemini 요약 작업", model_name, system_instruction, user_prompt, task_id)

    # ==========================================
    # 3. Anki 데이터 생성 (준비물: 교정본 + 강의록)
    # ==========================================
    def generate_anki_csv_text(
        self, 
        corrected_text: str, 
        pdf_text: str, 
        model_name: str, 
        task_id: Optional[str] = None
    ) -> Optional[str]:
        """강의록과 교정본을 바탕으로 Anki 카드 생성을 위한 파이프(|) 구분 CSV 텍스트를 생성합니다."""
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

        result_text = self._execute_llm_task("Anki CSV 데이터 생성", model_name, system_instruction, user_prompt, task_id)        
        if result_text:
            return result_text.replace("```csv", "").replace("```", "").strip()
        return None