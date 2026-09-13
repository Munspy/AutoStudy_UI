from core.exceptions import GeminiAPIError
import google.genai as genai
from google.genai import errors, types

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
        # 에러 식별 코드를 인스턴스 변수로 저장
        self.code = code

class GeminiLlmClient:
    """Gemini API 통신을 전담하는 클라이언트."""
    
    def call_api(self, api_key: str, model_name: str, system_instruction: str, user_prompt: str, temperature: float = 0.1, thinking_level: str | None = None, max_output_tokens: int = 65536) -> str:
        # 제공된 API 키를 사용하여 제미나이 클라이언트 인스턴스 생성
        client = genai.Client(api_key=api_key)
        
        try:
            config_dict = {
                "system_instruction": system_instruction,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens
            }
            
            if thinking_level:
                # google.genai 0.1+ 에서 지원하는 ThinkingConfig 사용
                config_dict["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
                
            # 프록시 게이트웨이 타임아웃(503) 방지를 위해 스트리밍 방식으로 요청
            response_stream = client.models.generate_content_stream(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(**config_dict)  # type: ignore
            )
            
            full_text_chunks = []
            last_finish_reason = None
            
            # 스트림 청크를 순회하며 텍스트를 결합하고 종료 사유 추적
            for chunk in response_stream:
                if chunk.text:
                    full_text_chunks.append(chunk.text)
                if chunk.candidates:
                    for candidate in chunk.candidates:
                        if candidate.finish_reason:
                            last_finish_reason = candidate.finish_reason
                            
            # 청크 순회 마지막에 MAX_TOKENS 절단 여부 확인
            if last_finish_reason and "MAX_TOKENS" in str(last_finish_reason).upper():
                raise GeminiAPIError("응답이 도중에 절단되었습니다 (MAX_TOKENS).", "max_tokens")
    
            return "".join(full_text_chunks)
            
        except errors.APIError as e:
            # API 레벨의 에러 발생 시 커스텀 예외로 래핑하여 던짐
            raise GeminiAPIError(f"LLM API 통신 오류: {e.message}", str(e.code))
            
        except GeminiAPIError:
            # MAX_TOKENS 등으로 직접 발생시킨 GeminiAPIError는 래핑 변조 없이 그대로 전파
            raise
            
        except (TimeoutError, ConnectionError) as e:
            # 네트워크 단절 및 타임아웃 오류 명시적 포착
            raise GeminiAPIError(f"네트워크 연결 오류 또는 타임아웃 발생: {str(e)}", "network_error")
            
        except Exception as e:
            # 그 외 예상치 못한 에러에 대한 폴백 처리
            raise GeminiAPIError(f"알 수 없는 LLM API 오류: {str(e)}", "unknown")
