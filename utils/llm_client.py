# utils/llm_client.py
import google.genai as genai
from google.genai import types
from google.genai import errors 

class GeminiAPIError(Exception):
    """LLM API 통신 중 발생한 에러와 HTTP 코드를 담는 커스텀 예외 클래스"""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code

def call_gemini_api(api_key: str, model_name: str, system_instruction: str, user_prompt: str, temperature: float = 0.1) -> str:
    """
    순수하게 LLM API를 호출하고 결과를 반환하는 유틸리티 함수입니다.
    키 할당이나 쿨타임 등의 비즈니스 로직은 전혀 모릅니다.
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