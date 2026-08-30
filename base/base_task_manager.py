# LLM 관리도 여기서 총괄할 것.
# ### 🚀 BaseTaskManager 다중 차선(Multi-Channel) 대기열 업그레이드 지시서

# **작업 목표**
# 기존 `BaseTaskManager`의 단일 대기열(Queue) 시스템을 개편하여, 하나의 매니저 안에서 여러 개의 독립적인 '차선(Channel)'을 굴릴 수 있도록 코드를 수정해 주세요. 이를 통해 병렬 처리가 필요한 일반 작업과, API 제한 때문에 하나씩 순차 처리해야 하는 LLM 작업을 완벽하게 분리하여 관리하는 것이 목적입니다.

# **상세 구현 지침**

# * **변수 구조 개편 (`__init__`)**: 기존의 단일 리스트(`_pending_queue`, `_active_tasks`)를 삭제하고, `self.channels`라는 딕셔너리를 도입하세요. 각 채널은 `"general": {"max": 3, "pending": [], "active": []}` 형식으로 최대 동시 실행 수, 대기열, 활성 큐를 독립적으로 가집니다. 기본 차선으로 `general(max=3)`과 `llm(max=1)`을 세팅해 주세요.
# * **작업 추가 (`add_task`)**: 파라미터에 `channel="general"`을 추가하세요. 들어온 워커를 해당 채널의 대기열(`pending`)에 밀어 넣고, 워커가 끝났을 때 어떤 채널에서 끝났는지 추적할 수 있도록 `finished` 시그널 람다식에 `channel` 문자열도 같이 바인딩하여 넘겨주세요.
# * **큐 처리 로직 (`_process_queue`)**: 특정 차선만 처리할 수 있도록 파라미터에 `channel`을 받게 만드세요. 해당 채널의 `active` 스레드 수가 `max` 제한보다 적고 대기열이 남아있다면 작업을 꺼내서 실행(`start()`)하도록 수정하세요.
# * **작업 완료 처리 (`_on_task_finished`)**: 인자로 받은 `channel` 정보를 바탕으로 해당 차선의 `active` 리스트에서 스레드를 제거하세요. 그 후 그 차선의 다음 작업을 돌리기 위해 `_process_queue(channel)`을 호출하세요.
# * **진행률 및 초기화 (`_reset_counters`, `clear_queue`)**: 진행률 시그널(`queue_progress_signal`)은 전체 채널의 `_total_tasks`와 `_completed_tasks`를 통합해서 계산하여 발사하도록 수정하세요.

from PyQt6.QtCore import QObject, pyqtSignal

class BaseTaskManager(QObject):
    """
    여러 스레드(QThread)가 동시에 폭주하여 시스템이 멈추거나 API 제한에 걸리는 것을 막기 위해
    작업 대기열(Queue)을 만들고 정해진 수만큼만 순차적으로 실행시키는 중앙 관리자입니다.
    """
    # 큐 전체의 진행 상황이나 상태를 UI에 전달하기 위한 시그널
    queue_progress_signal = pyqtSignal(int, int) # (완료된 작업 수, 전체 작업 수)
    queue_finished_signal = pyqtSignal()
    
    def __init__(self, max_concurrent_tasks: int = 3):
        super().__init__()
        self.max_concurrent_tasks = max_concurrent_tasks
        
        self._pending_queue = []  # 대기 중인 스레드 리스트
        self._active_tasks = []   # 현재 실행 중인 스레드 리스트
        
        self._total_tasks = 0
        self._completed_tasks = 0

    def add_task(self, thread_instance):
        """
        생성된 스레드 객체를 큐에 추가합니다.
        (즉시 실행되지 않고 가용 슬롯이 있을 때만 실행됩니다.)
        """
        self._pending_queue.append(thread_instance)
        self._total_tasks += 1
        
        # 스레드가 끝났을 때 큐 매니저가 이를 알아채도록 시그널 연결
        thread_instance.finished.connect(lambda: self._on_task_finished(thread_instance))
        
        # 슬롯에 여유가 있다면 바로 실행
        self._process_queue()

    def _process_queue(self):
        """
        대기열을 확인하여 실행 가능한 만큼 스레드를 시작합니다.
        """
        while len(self._active_tasks) < self.max_concurrent_tasks and self._pending_queue:
            next_task = self._pending_queue.pop(0)
            self._active_tasks.append(next_task)
            next_task.start()

    def _on_task_finished(self, thread_instance):
        """
        스레드 작업이 하나 끝날 때마다 호출되어 다음 작업을 큐에서 꺼내 실행합니다.
        """
        if thread_instance in self._active_tasks:
            self._active_tasks.remove(thread_instance)
            
        self._completed_tasks += 1
        self.queue_progress_signal.emit(self._completed_tasks, self._total_tasks)
        
        # 메모리 누수 방지
        thread_instance.deleteLater()
        
        # 대기 중인 다음 작업 실행
        self._process_queue()
        
        # 큐가 완전히 비워지고 실행 중인 작업도 없다면 완료 시그널 방출
        if not self._pending_queue and not self._active_tasks:
            self.queue_finished_signal.emit()
            self._reset_counters()

    def _reset_counters(self):
        self._total_tasks = 0
        self._completed_tasks = 0

    def clear_queue(self):
        """
        대기 중인 모든 작업을 취소하고 큐를 비웁니다.
        (현재 실행 중인 작업은 강제로 멈추지 않고 스스로 끝나도록 둡니다.)
        """
        self._pending_queue.clear()
        self._reset_counters()