from base.base_service import BaseService
"""API 키 추적 및 상태 관리 유틸리티 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Utils(유틸리티) 계층**에 속합니다.
멀티스레드 환경에서 여러 백그라운드 Worker 스레드와 Service 계층이 Google Gemini API와 
통신할 때 발생하는 API 호출 제한(Rate Limit), 일일 할당량(Daily Quota), 동시성 충돌 문제를 
해결하기 위해 고안된 핵심 매니저입니다.

다중 API 키와 다중 모델(`key::model` 조합)의 가용성(Availability) 상태를 
로컬 JSON 파일(`api_key_state.json`)로 캐싱하여 영속적으로 추적하며, 
스레드 락(Condition Variable)을 활용하여 Worker 간의 키 쟁탈 현상(Race Condition)을 
조율하고 불필요한 대기(Sleep) 오버헤드를 최소화합니다.
"""

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
# API 상태 및 에러 코드 상수 분리
# ==========================================
ERROR_QUOTA_EXCEEDED = "429"

STATE_READY = "READY"
STATE_BUSY = "BUSY"
STATE_COOLDOWN = "COOLDOWN"
STATE_DAILY_LIMIT = "DAILY"
STATE_ERROR = "ERROR"
STATE_NOT_FOUND = "NOT_FOUND"
# ==========================================

class APIManager(BaseService):
    """Gemini API 키의 가용 상태, 에러, 쿨타임을 관리하고 동시성을 제어하는 단일 책임 클래스.

    이 클래스는 시스템 내에 하나만 존재하는 싱글톤(모듈 레벨 인스턴스 `api_mgr`)으로 동작합니다. 
    `Config` 객체로부터 다중 API 키 배열과 허용된 모델 리스트를 로드하여 관리 풀(Pool)을 생성합니다. 
    비동기 Worker나 LLMService가 API를 호출하기 전에 `get_available_key`를 통해 유효한 키를 
    스레드 안전(Thread-safe)하게 대여(Checkout)받고, 통신이 끝난 후 `end_task`를 호출하여 
    키를 반납(Checkin) 및 상태(성공, 쿨타임, 한도 초과 등)를 업데이트하도록 통제합니다.
    """
    def __init__(self, state_file_name: str = "api_key_state.json") -> None:
        """APIManager 객체를 초기화하고 로컬 상태 파일과 전역 설정을 연동합니다.

        Args:            state_file_name (str, optional): API 키 가용성 상태를 캐싱할 로컬 JSON 파일명. 기본값은 "api_key_state.json"입니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        self.state_file: Path = BASE_DIR / state_file_name
        
        self.lock = threading.Condition()
        
        # [개선 1] Config(SSOT)에서 전역 설정값 가져오기
        self.cooldown_seconds: float = Config.API_COOLDOWN_SECONDS
        self.models: List[str] = Config.GEMINI_MODELS
        
        self.key_map: Dict[str, str] = {f"KEY_{i+1}": key for i, key in enumerate(Config.GEMINI_KEYS)}
        self.keys: List[str] = list(self.key_map.keys())
        
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """로컬 파일 시스템에서 기존 API 키 상태 데이터를 로드하거나 초기화합니다.

        이 메서드는 애플리케이션 시작 시 호출되어 이전에 실패했거나 쿨타임 중이었던 
        API 키 상태를 복원합니다. 시스템이 예기치 않게 종료된 후 재시작되더라도 
        할당량 초과(429) 상태를 기억하여 무의미한 API 호출 시도를 방지합니다.
        파일이 손상(Corruption)되었을 경우를 대비해 기존 파일을 백업하고 새로운 상태로 초기화하는 
        방어 로직이 포함되어 있습니다.

        Args:            없음

        Returns:
            Dict[str, Any]: 복원되었거나 새로 초기화된 `키::모델` 조합의 상태 딕셔너리.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        initial_state = {}
        for k in self.keys:
            for m in self.models:
                combo = f"{k}::{m}"
                initial_state[combo] = {
                    "is_in_use": False,
                    "last_finished_at": 0.0,
                    "error_code": None,
                    "error_time": 0.0
                }
                
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    loaded_state = json.load(f)
                    # 누락된 키 병합 및 강제 종료로 인한 좀비 상태 초기화
                    for combo, init_val in initial_state.items():
                        if combo not in loaded_state:
                            loaded_state[combo] = init_val
                        else:
                            # 앱 재시작 시 기존 '사용 중' 플래그는 모두 무효화
                            loaded_state[combo]["is_in_use"] = False
                    return loaded_state
            except Exception as e:
                backup_path = self.state_file.with_suffix('.json.bak')
                try:
                    shutil.copy2(self.state_file, backup_path)
                    print(f"⚠️ 'api_key_state.json' 파일 손상 감지. 기존 파일을 백업했습니다: {backup_path.name} (에러: {e})")
                except Exception as backup_e:
                    print(f"⚠️ 상태 파일 백업 중 오류 발생: {backup_e}")
                
        return initial_state

    def _save_state(self) -> None:
        """메모리 내의 현재 API 키 상태를 로컬 JSON 파일에 동기화하여 영속화합니다.

        원자적(Atomic) 파일 쓰기 도입:        여러 스레드가 거의 동시에 키를 대여하거나 반납할 때 파일 I/O 충돌이나 
        크래시로 인해 JSON 구조가 0 byte로 손상되는 현상을 원천 방지합니다. 
        데이터를 임시 파일(`.tmp`)에 완전히 쓴 뒤 성공했을 때만 `replace`를 수행하여 무결성을 유지합니다.

        Args:
            없음

        Returns:
            None
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """주어진 UNIX 타임스탬프를 태평양 표준시(PT, UTC-8) 기준의 날짜 문자열로 변환합니다.

        Google Gemini API의 일일 할당량(Daily Quota)은 한국 시간이 아닌 
        태평양 표준시(PT) 자정을 기준으로 리셋됩니다. 따라서 429(할당량 초과) 에러가 발생한 
        시점과 현재 시점의 날짜가 같은지(즉, 쿨타임이 하루 지나서 풀렸는지)를 정확히 비교하기 위해 
        로컬 시간을 강제로 PT 시간대로 캐스팅하는 핵심 시간 유틸리티입니다.

        Args:            timestamp (float): 변환할 기준 UNIX 타임스탬프 (초 단위).

        Returns:
            str: "YYYY-MM-DD" 포맷의 태평양 표준시 기준 날짜 문자열.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        dt = datetime.fromtimestamp(timestamp, tz=PT_TIMEZONE)
        return dt.strftime("%Y-%m-%d")

    def end_task(self, key_id: str, model_name: str, error_code: Optional[str] = None) -> None:
        """API 호출 작업을 완료한 뒤 대여했던 키를 반납하고 상태를 업데이트합니다.

        Service 계층이 Gemini 통신을 성공적으로 마쳤거나 에러(예: 429)로 종료되었을 때 반드시 호출해야 하는 메서드입니다. 
        해당 `키::모델` 조합의 `is_in_use` 플래그를 False로 변경하고 종료 시간을 기록하여 
        이후 `cooldown_seconds` 계산의 기준점으로 삼습니다. 
        상태 업데이트 후 `lock.notify_all()`을 호출하여, 가용 키가 나오기를 기다리며 
        수면(Wait) 상태에 빠져있던 다른 워커 스레드들을 즉시 깨워(Wake-up) 처리율(Throughput)을 극대화합니다.

        Args:            key_id (str): 작업을 마친 API 키의 식별자(ID).
            model_name (str): 사용했던 LLM 모델의 이름.
            error_code (Optional[str], optional): 작업 중 발생한 에러가 있다면 그 식별 코드(예: "429"). 정상 종료 시 None.

        Returns:
            None
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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
        """특정 `키::모델` 조합의 현재 가용성 상태와 대기(쿨타임) 잔여 시간을 검사합니다.

        UI 레이어에서 각 키의 상태를 시각적으로 보여주거나 모니터링할 때 사용되는 상태 조회용 메서드입니다. 
        현재 사용 중(BUSY)인지, 요청 속도 제한 대기 중(COOLDOWN)인지, 하루 할당량을 모두 소진(DAILY_LIMIT)했는지 등 
        자세한 내부 상태를 판별합니다.

        Args:            key_id (str): 상태를 조회할 API 키의 식별자(ID).
            model_name (str): 상태를 조회할 LLM 모델의 이름.

        Returns:
            Tuple[str, float]: 
                - 첫 번째 요소: 현재 상태를 나타내는 문자열 상수 (READY, BUSY, COOLDOWN, DAILY, ERROR, NOT_FOUND 중 하나).
                - 두 번째 요소: 남은 쿨타임 초(float). 상태가 COOLDOWN이 아닐 경우 0.0을 반환합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
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

    def get_available_key(self, model_name, timeout: int = 3600):
        """현재 즉시 사용할 수 있는(Ready 상태인) 최적의 API 키를 찾아 스레드 안전하게 할당(Checkout)합니다.

        Service 계층이 LLM API 요청을 보내기 직전에 호출하는 핵심 메서드입니다. 
        다중 API 키 배열을 순회하며 사용 중(BUSY)이거나 할당량 초과(429) 상태인 키를 걸러냅니다. 
        모든 키가 쿨타임(COOLDOWN)에 걸려 있어 즉시 사용할 수 없는 경우, CPU를 점유하는 
        Busy-Waiting(무한 루프) 방식 대신 가장 먼저 쿨타임이 끝나는 키의 남은 시간(`shortest_wait`)을 계산합니다. 
        
        그 후 `lock.wait()`를 호출하여 스레드 락을 스스로 해제하고 정확히 그 시간만큼만 수면(Sleep/Wait) 
        상태에 돌입합니다. 대기 도중 다른 스레드가 `end_task`를 호출해 `notify_all()`을 날리면 
        즉시 깨어나 가용 키를 다시 탐색합니다. 이를 통해 다중 워커 환경에서 교착 상태(Deadlock)를 방지하고 
        API 호출량을 한계치까지 안전하게 밀어붙일 수 있습니다.

        Args:            model_name (str): 작업을 요청할 대상 LLM 모델의 이름.
            timeout (int, optional): 가용 키를 찾지 못할 경우 대기할 최대 허용 시간(초). 기본값은 3600(1시간)입니다.

        Returns:
            Tuple[str, str]: 할당에 성공한 최적 API 키의 식별자(ID)와 실제 API 키 문자열 값을 튜플로 반환합니다.

        Raises:
            TimeoutError: 지정된 `timeout` 시간을 모두 소진하고도 유효한 API 키를 할당받지 못한 경우 발생합니다.
        """
        # ===========================
        # [메인 비즈니스 로직]
        # ===========================
        # 입력값을 바탕으로 핵심 로직을 수행합니다.
        models = [model_name] if isinstance(model_name, str) else model_name
        model_display = ', '.join(models)
        print(f"\n🔍 [{model_display}] 사용 가능한 API Key 탐색 중...")
        start_time = time.time()
        
        with self.lock: 
            while True:
                current_time = time.time()
                if current_time - start_time > timeout:
                    raise TimeoutError(f"API Key 확보 시간 초과 ({timeout}초)")
                
                shortest_wait = timeout 

                for m_name in models:
                    for key_id, api_key in self.key_map.items():
                        if not api_key: continue
                        
                        data = self.state.get(f"{key_id}::{m_name}")
                        if not data or data["is_in_use"]: continue
                        
                        if data.get("error_code") == ERROR_QUOTA_EXCEEDED:
                            if self._get_pt_date(data["error_time"]) == self._get_pt_date(current_time):
                                continue
                                
                        time_since_finished = current_time - data["last_finished_at"]
                        if time_since_finished < self.cooldown_seconds:
                            remaining = self.cooldown_seconds - time_since_finished
                            shortest_wait = min(shortest_wait, remaining)
                            continue
                            
                        data["is_in_use"] = True
                        self._save_state()
                        print(f"✅ [{m_name}] '{key_id}' 할당 완료 및 작업 시작!")
                        return key_id, api_key, m_name
                    
                # 모든 키가 사용 중이거나 쿨타임인 경우
                # 락을 해제한 채로 가장 짧은 쿨타임만큼만 정확히 수면(Wait)
                self.lock.wait(timeout=shortest_wait)

api_mgr = APIManager()