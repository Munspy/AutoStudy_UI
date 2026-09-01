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
        
        self.channels = {
            "general": {"max": max_concurrent_tasks, "pending": [], "active": []},
            "llm": {"max": 1, "pending": [], "active": []}
        }
        
        self._total_tasks = 0
        self._completed_tasks = 0

    def add_task(self, worker_instance, channel="general"):
        """
        생성된 스레드 객체를 특정 채널의 큐에 추가합니다.
        """
        if channel not in self.channels:
            channel = "general"
            
        self.channels[channel]["pending"].append(worker_instance)
        self._total_tasks += 1
        
        # 스레드가 끝났을 때 큐 매니저가 이를 알아채도록 시그널 연결 (채널 정보 포함)
        worker_instance.finished.connect(lambda: self._on_task_finished(worker_instance, channel))
        
        # 슬롯에 여유가 있다면 바로 실행
        self._process_queue(channel)

    def _process_queue(self, channel):
        """
        지정된 차선의 대기열을 확인하여 실행 가능한 만큼 스레드를 시작합니다.
        """
        ch = self.channels[channel]
        while len(ch["active"]) < ch["max"] and ch["pending"]:
            next_task = ch["pending"].pop(0)
            ch["active"].append(next_task)
            next_task.start()

    def _on_task_finished(self, worker_instance, channel):
        """
        스레드 작업이 하나 끝날 때마다 호출되어 다음 작업을 큐에서 꺼내 실행합니다.
        """
        ch = self.channels[channel]
        if worker_instance in ch["active"]:
            ch["active"].remove(worker_instance)
            
        self._completed_tasks += 1
        self.queue_progress_signal.emit(self._completed_tasks, self._total_tasks)
        
        # 메모리 누수 방지
        worker_instance.deleteLater()
        
        # 대기 중인 다음 작업 실행
        self._process_queue(channel)
        
        # 큐가 완전히 비워지고 실행 중인 작업도 없다면 완료 시그널 방출
        is_empty = all(not c["pending"] and not c["active"] for c in self.channels.values())
        if is_empty:
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
        for channel in self.channels.values():
            channel["pending"].clear()
        self._reset_counters()