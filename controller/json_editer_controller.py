import os
import json
from pathlib import Path
from base.base_controller import BaseController
from utils.config import BASE_DIR, Config

class JsonEditerController(BaseController):
    """api_key_state.json 및 .env 파일을 직접 조회 및 수정하도록 돕는 컨트롤러"""
    
    def __init__(self, view=None):
        super().__init__(ui_view=view)
        self.state_file_path = BASE_DIR / "api_key_state.json"
        self.env_file_path = BASE_DIR / ".env"

    def load_file_content(self, file_type: str) -> str:
        """지정된 파일의 텍스트 내용을 로드합니다."""
        target_path = self._get_path_for_type(file_type)
        if not target_path.exists():
            if file_type == "json":
                # 기본 JSON 구조 생성 후 로드
                default_data = {}
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=4)
                return "{}"
            else:
                return ""
                
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            self.emit_error(f"파일을 읽는 중 오류 발생: {str(e)}")
            return ""

    def save_file_content(self, file_type: str, content: str) -> tuple[bool, str]:
        """지정된 파일의 내용을 검증하고 안전하게 덮어씁니다."""
        target_path = self._get_path_for_type(file_type)
        
        # 1. 검증 로직
        if file_type == "json":
            try:
                # JSON 구문 분석 검증
                parsed = json.loads(content)
                # 정돈된 포맷으로 변경
                content = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as jde:
                return False, f"JSON 문법 오류: {str(jde)}"
                
        # 2. 임시 파일을 활용한 원자적 쓰기 (무결성 유지)
        temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            temp_path.replace(target_path)
            
            # .env 저장 시 Config 다시 로드 시도
            if file_type == "env":
                Config.reload()
                
            return True, "성공적으로 저장되었습니다."
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False, f"파일 저장 실패: {str(e)}"

    def _get_path_for_type(self, file_type: str) -> Path:
        if file_type == "json":
            return self.state_file_path
        elif file_type == "env":
            return self.env_file_path
        else:
            raise ValueError(f"지원하지 않는 파일 타입입니다: {file_type}")

