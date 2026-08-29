# utils/api_key_tracker.py
import json
import time
import threading
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from utils.config import Config, BASE_DIR

PT_TIMEZONE = timezone(timedelta(hours=-8))

# ==========================================
# [개선 3] API 상태 및 에러 코드 상수 분리
# ==========================================
ERROR_QUOTA_EXCEEDED = "429"

STATE_READY = "READY"
STATE_BUSY = "BUSY"
STATE_COOLDOWN = "COOLDOWN"
STATE_DAILY_LIMIT = "DAILY"
STATE_ERROR = "ERROR"
STATE_NOT_FOUND = "NOT_FOUND"
# ==========================================

class APIManager:
    def __init__(self, state_file_name: str = "api_key_state.json") -> None:
        self.state_file: Path = BASE_DIR / state_file_name
        
        self.lock = threading.Condition()
        
        # [개선 1] Config(SSOT)에서 전역 설정값 가져오기
        self.cooldown_seconds: float = Config.API_COOLDOWN_SECONDS
        self.models: List[str] = Config.GEMINI_MODELS
        
        self.key_map: Dict[str, str] = {f"KEY_{i+1}": key for i, key in enumerate(Config.GEMINI_KEYS)}
        self.keys: List[str] = list(self.key_map.keys())
        
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                backup_path = self.state_file.with_suffix('.json.bak')
                try:
                    shutil.copy2(self.state_file, backup_path)
                    print(f"⚠️ 'api_key_state.json' 파일 손상 감지. 기존 파일을 백업했습니다: {backup_path.name} (에러: {e})")
                except Exception as backup_e:
                    print(f"⚠️ 상태 파일 백업 중 오류 발생: {backup_e}")
                
        initial_state: Dict[str, Any] = {}
        for k in self.keys:
            for m in self.models:
                combo = f"{k}::{m}"
                initial_state[combo] = {
                    "is_in_use": False,
                    "last_finished_at": 0.0,
                    "error_code": None,
                    "error_time": 0.0
                }
        return initial_state

    def _save_state(self) -> None:
        """[개선 2] 원자적(Atomic) 파일 쓰기 도입: 임시 파일 작성 후 덮어쓰기로 데이터 오염 방지"""
        temp_file: Path = self.state_file.with_suffix('.json.tmp')
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
            temp_file.replace(self.state_file)
        except Exception as e:
            print(f"⚠️ 상태 파일 저장 중 오류 발생: {e}")
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def _get_pt_date(self, timestamp: float) -> str:
        dt = datetime.fromtimestamp(timestamp, tz=PT_TIMEZONE)
        return dt.strftime("%Y-%m-%d")

    def end_task(self, key_id: str, model_name: str, error_code: Optional[str] = None) -> None:
        combo = f"{key_id}::{model_name}"
        current_time = time.time()
        
        with self.lock:
            if combo in self.state:
                self.state[combo]["is_in_use"] = False
                self.state[combo]["last_finished_at"] = current_time
                
                if error_code:
                    self.state[combo]["error_code"] = str(error_code)
                    self.state[combo]["error_time"] = current_time
                else:
                    self.state[combo]["error_code"] = None
                self._save_state()
            
            # 키가 반납(상태 변경)되었으므로 잠들어 있는 다른 스레드들을 모두 깨움
            self.lock.notify_all()

    def check_combo_status(self, key_id: str, model_name: str) -> Tuple[str, float]:
        combo = f"{key_id}::{model_name}"
        with self.lock:
            data = self.state.get(combo)
            if not data: return STATE_NOT_FOUND, 0.0
            if data["is_in_use"]: return STATE_BUSY, 0.0
            
            current_time = time.time()
            error_code = data.get("error_code")
            error_time = data.get("error_time", 0.0)
            
            if error_code:
                # 상수로 에러 코드 비교
                if error_code == ERROR_QUOTA_EXCEEDED:
                    if self._get_pt_date(error_time) == self._get_pt_date(current_time):
                        return STATE_DAILY_LIMIT, 0.0
                else:
                    return STATE_ERROR, float(error_code) if error_code.isdigit() else 0.0
            
            time_since_finished = current_time - data["last_finished_at"]
            if time_since_finished < self.cooldown_seconds:
                remaining = self.cooldown_seconds - time_since_finished
                return STATE_COOLDOWN, remaining
                
            return STATE_READY, 0.0

    def get_available_key(self, model_name: str, timeout: int = 3600) -> Tuple[str, str]:
        print(f"\n🔍 [{model_name}] 사용 가능한 API Key 탐색 중...")
        start_time = time.time()
        
        with self.lock: 
            while True:
                current_time = time.time()
                if current_time - start_time > timeout:
                    raise TimeoutError(f"API Key 확보 시간 초과 ({timeout}초)")
                
                # 가장 짧게 남은 쿨타임을 추적하기 위한 변수
                shortest_wait = timeout 

                for key_id, api_key in self.key_map.items():
                    if not api_key: continue
                    
                    data = self.state.get(f"{key_id}::{model_name}")
                    if not data or data["is_in_use"]: continue
                    
                    # 일일 한도 에러 처리 (상수 사용)
                    if data.get("error_code") == ERROR_QUOTA_EXCEEDED:
                        if self._get_pt_date(data["error_time"]) == self._get_pt_date(current_time):
                            continue
                            
                    time_since_finished = current_time - data["last_finished_at"]
                    if time_since_finished < self.cooldown_seconds:
                        # 쿨타임이 남은 경우, 남은 시간을 계산하여 가장 짧은 대기 시간 업데이트
                        remaining = self.cooldown_seconds - time_since_finished
                        shortest_wait = min(shortest_wait, remaining)
                        continue
                        
                    # 사용 가능한 키 발견 시 즉시 할당
                    data["is_in_use"] = True
                    self._save_state()
                    print(f"✅ [{model_name}] '{key_id}' 할당 완료 및 작업 시작!")
                    return key_id, api_key
                    
                # 모든 키가 사용 중이거나 쿨타임인 경우
                # 락을 해제한 채로 가장 짧은 쿨타임만큼만 정확히 수면(Wait)
                self.lock.wait(timeout=shortest_wait)

api_mgr = APIManager()