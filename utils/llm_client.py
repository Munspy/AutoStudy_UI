"""LLM API 통신을 전담하는 유틸리티 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 파이프라인 중 **Utils(유틸리티) 계층**에 속합니다.
Google Gemini API와의 직접적인 네트워크 통신과 예외 처리를 담당하며, 
Service 계층(예: LLMService)이나 Worker 계층이 모델에 프롬프트를 전송하고 
응답을 받아올 때 사용하는 최하단(Low-level) I/O 인터페이스 역할을 수행합니다.

API 키 관리, 요청 쿨타임(Rate Limit), 로테이션 등 복잡한 상위 비즈니스 로직에 대한 의존성 없이, 
순수하게 데이터를 전송하고 결과를 수신하는 단일 책임(Single Responsibility)을 가집니다.
또한, 발생 가능한 다양한 네트워크 및 API 예외를 규격화된 커스텀 예외로 변환하여 
상위 호출자(Caller)가 일관되게 에러를 핸들링하고 재시도(Retry) 로직을 구성할 수 있도록 돕습니다.
"""

import google.genai as genai
from google.genai import types
from google.genai import errors 


class GeminiAPIError(Exception):
    """LLM API 통신 중 발생한 에러를 캡슐화하는 커스텀 예외 클래스.

    단일 책임 원칙(SRP)에 따라 API 호출 중 발생하는 다양한 하위 레벨 오류(HTTP 오류, 
    네트워크 연결 끊김, 타임아웃 등)를 애플리케이션 내부의 통일된 예외 타입으로 
    변환 및 정의하는 책임을 가집니다. 
    
    주요 상태로 에러 메시지와 구체적인 에러 코드(`code`)를 보관하며, 
    Service 계층이나 백그라운드 Worker가 이 예외를 포착(Catch)하여 
    재시도할지, 아니면 파이프라인을 중단하고 UI에 에러를 보고할지 결정하는 데 활용됩니다.
    """
    def __init__(self, message: str, code: str):
        """예외 객체를 초기화합니다.

        Args:
            message (str): 발생한 에러에 대한 상세 설명 및 로깅용 메시지.
            code (str): HTTP 상태 코드(예: '404', '500') 또는 에러의 종류를 나타내는 식별 문자열(예: 'network_error').
        """
        super().__init__(message)
        self.code = code


def call_gemini_api(api_key: str, model_name: str, system_instruction: str, user_prompt: str, temperature: float = 0.1) -> str:
    """Google Gemini API를 호출하여 텍스트를 생성하는 코어 유틸리티 함수.

    이 함수는 사용자 프롬프트와 시스템 인스트럭션을 조합하여 제미나이 모델에 텍스트 생성을 요청합니다.
    자동화된 비동기 처리 관점에서, 수많은 PDF 페이지나 음성 변환 스크립트(Whisper 결과물)가 
    Worker를 통해 쏟아져 들어올 때 빠르고 독립적으로 API와 통신해야 합니다. 
    
    이 로직은 시스템의 복잡한 비즈니스 로직(예: 사용량 추적, DB 저장, 키 로테이션 등)과는 완전히 
    격리되어 작동하도록 설계되었습니다. 이러한 격리 설계는 API 통신이라는 본연의 목적에만 집중하게 함으로써 
    코드의 응집도를 높이고, 향후 SDK 버전 업데이트나 인증 방식이 변경되더라도 수정 범위를 이 함수 내부로만 
    제한하여 유지보수성을 극대화합니다. 내부적으로 `google.genai.Client`를 초기화하고 주어진 
    환경 설정값(`temperature`)을 바탕으로 콘텐츠 생성을 요청한 뒤, 결과물만 추출하여 안전하게 반환합니다.

    Args:
        api_key (str): Gemini API 서비스에 접근하고 인증하기 위한 사용자의 API 키.
        model_name (str): 텍스트 생성에 사용할 대상 Gemini 모델의 이름 (예: 'gemini-1.5-pro', 'gemini-2.5-flash').
        system_instruction (str): 모델의 페르소나, 역할, 어조 및 전반적인 행동 지침을 정의하는 시스템 프롬프트.
        user_prompt (str): 모델에게 전달하여 실제 답변 생성을 유도하는 사용자의 구체적인 질문 또는 입력 텍스트.
        temperature (float, optional): 모델 응답의 창의성과 무작위성을 제어하는 하이퍼파라미터. 
            0.0에 가까울수록 결정론적이고 일관된 응답을, 높은 값일수록 다양하고 예상치 못한 응답을 
            생성합니다. 기본값은 0.1로, 학습 자료 자동화 생성 시 요구되는 안정적이고 사실적인 텍스트 생성에 맞춰져 있습니다.

    Returns:
        str: 제미나이 모델이 성공적으로 생성하여 반환한 순수 텍스트 결과물(response.text).

    Raises:
        GeminiAPIError: 아래와 같은 다양한 원인으로 인해 정상적인 API 통신이 실패할 경우, 
            구체적인 에러 메시지와 에러 코드를 담아 발생시킵니다.
            - API 통신 오류: 잘못된 API 키, 할당량 초과, 서버 내부 오류 등 (errors.APIError)
            - 네트워크 오류: 인터넷 연결 단절 또는 요청 시간 초과 (TimeoutError, ConnectionError)
            - 기타 알 수 없는 오류 (Exception)
    """
    client = genai.Client(api_key=api_key)
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature
            )
        )
        return response.text
        
    except errors.APIError as e:
        raise GeminiAPIError(f"LLM API 통신 오류: {e.message}", str(e.code))
        
    except (TimeoutError, ConnectionError) as e:
        # 네트워크 단절 및 타임아웃 오류 명시적 포착
        raise GeminiAPIError(f"네트워크 연결 오류 또는 타임아웃 발생: {str(e)}", "network_error")
        
    except Exception as e:
        raise GeminiAPIError(f"알 수 없는 LLM API 오류: {str(e)}", "unknown")