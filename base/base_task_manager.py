"""기본 작업 관리자(Base Task Manager) 모듈입니다.

이 모듈은 다수의 백그라운드 스레드(작업)가 동시에 실행될 때 발생하는 
시스템 과부하나 API 호출 제한(Rate Limit)을 방지하기 위해 큐(Queue) 기반으로
작업을 스케줄링하는 `BaseTaskManager` 클래스를 제공합니다.

주요 클래스:
    BaseTaskManager: 채널별로 스레드 큐를 관리하고 동시 실행 수를 제어하는 매니저.

의존성:
    PyQt6.QtCore: QObject 및 pyqtSignal을 통한 이벤트 기반 큐 관리.
"""

from PyQt6.QtCore import QObject, pyqtSignal

class BaseTaskManager(QObject):
    """여러 스레드(QThread)의 대기열을 관리하고 동시 실행 수를 제한하는 중앙 관리자입니다.
    
    무분별한 스레드 생성을 막고, 지정된 최대 동시 실행 수(`max_concurrent_tasks`) 내에서
    순차적으로 작업을 처리합니다. 일반 작업과 LLM 호출 같은 특수 작업을 '채널' 개념으로 분리하여 관리합니다.

    Attributes:
        queue_progress_signal (pyqtSignal): 전체 대기열 진행 상태(완료된 작업 수, 전체 작업 수)를 UI로 전달.
        queue_finished_signal (pyqtSignal): 대기열의 모든 작업이 끝났음을 알림.
        max_concurrent_tasks (int): 'general' 채널에서 동시에 실행 가능한 최대 스레드 수.
        channels (dict): 채널명별 스레드 큐 상태(최대 실행 수, 대기 중, 실행 중)를 저장하는 딕셔너리.

    Inherits:
        QObject: PyQt의 시그널 송수신을 위해 상속.
    """
    # 큐 전체의 진행 상황이나 상태를 UI에 전달하기 위한 시그널
    queue_progress_signal = pyqtSignal(int, int) # (완료된 작업 수, 전체 작업 수)
    queue_finished_signal = pyqtSignal()
    
    def __init__(self, max_concurrent_tasks: int = 3):
        """태스크 매니저를 초기화하고 채널별 큐 구조를 생성합니다.

        Args:
            max_concurrent_tasks (int, optional): 일반(general) 채널의 최대 동시 실행 스레드 수. Defaults to 3.
        
        Returns:
            None
        """
        # ===========================
        # [초기화 및 속성 설정]
        # ===========================
        super().__init__()
        # 최대 동시 작업 수 저장
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # ===========================
        # [채널별 큐 구조 생성]
        # ===========================
        self.channels = {
            "general": {"max": max_concurrent_tasks, "pending": [], "active": []},
            "llm": {"max": 1, "pending": [], "active": []}
        }
        
        self._total_tasks = 0
        self._completed_tasks = 0

    def add_task(self, worker_instance, channel="general"):
        """생성된 스레드 객체(워커)를 특정 채널의 대기열(큐)에 추가합니다.

        사용자가 대량의 작업을 요청했을 때 이를 즉시 실행하지 않고 큐에 적재하기 위해 호출됩니다.
        슬롯에 여유가 있다면 대기 없이 즉시 실행을 시도합니다.

        Args:
            worker_instance (BaseWorker): 실행할 작업 인스턴스 (QThread 상속 객체).
            channel (str, optional): 작업을 할당할 채널 이름. Defaults to "general".

        Returns:
            None
        """
        # ===========================
        # [채널 검증 및 큐 추가]
        # ===========================
        # 요청된 채널이 존재하지 않으면 기본 채널로 설정
        if channel not in self.channels:
            channel = "general"
            
        # 대기열에 작업 추가 및 전체 작업 수 증가
        self.channels[channel]["pending"].append(worker_instance)
        self._total_tasks += 1
        
        # ===========================
        # [시그널 연결 및 큐 처리]
        # ===========================
        # 스레드가 끝났을 때 큐 매니저가 이를 알아채도록 시그널 연결 (채널 정보 포함)
        worker_instance.finished.connect(lambda: self._on_task_finished(worker_instance, channel))
        
        # 슬롯에 여유가 있다면 바로 실행
        self._process_queue(channel)

    def _process_queue(self, channel):
        """지정된 채널의 대기열을 확인하여 실행 가능한 만큼 스레드를 시작합니다.

        대기열(pending)에 작업이 있고, 현재 실행 중인 작업 수(active)가 
        최대 허용치(max) 미만일 때 워커를 꺼내 실행(`start()`)하기 위해 내부적으로 호출됩니다.

        Args:
            channel (str): 큐를 확인할 채널 이름.

        Returns:
            None
        """
        # ===========================
        # [대기열 확인 및 스레드 실행]
        # ===========================
        # 해당 채널의 큐 상태 정보 가져오기
        ch = self.channels[channel]
        # 활성 작업이 최대 허용치 미만이고 대기 중인 작업이 있는 동안 반복
        while len(ch["active"]) < ch["max"] and ch["pending"]:
            # 대기열에서 가장 앞선 작업을 꺼냄
            next_task = ch["pending"].pop(0)
            # 활성 작업 목록에 추가
            ch["active"].append(next_task)
            # 작업 스레드 시작
            next_task.start()

    def _on_task_finished(self, worker_instance, channel):
        """스레드 작업이 종료되었을 때 호출되는 콜백입니다.

        완료된 스레드를 실행 목록(active)에서 제거하고 진행률을 갱신하며,
        대기열에 있는 다음 작업을 이어서 실행하기 위해 호출됩니다. 메모리 정리(`deleteLater`)도 수행합니다.

        Args:
            worker_instance (BaseWorker): 종료된 작업 인스턴스.
            channel (str): 종료된 작업이 속했던 채널 이름.

        Returns:
            None
        """
        # ===========================
        # [종료 작업 정리 및 진행 상태 업데이트]
        # ===========================
        ch = self.channels[channel]
        # 활성 목록에 존재하면 제거
        if worker_instance in ch["active"]:
            ch["active"].remove(worker_instance)
            
        # 완료된 작업 수 증가 및 진행률 시그널 발송
        self._completed_tasks += 1
        self.queue_progress_signal.emit(self._completed_tasks, self._total_tasks)
        
        # 메모리 누수 방지
        worker_instance.deleteLater()
        
        # ===========================
        # [다음 큐 처리 및 완료 확인]
        # ===========================
        # 대기 중인 다음 작업 실행
        self._process_queue(channel)
        
        # 큐가 완전히 비워지고 실행 중인 작업도 없다면 완료 시그널 방출
        is_empty = all(not c["pending"] and not c["active"] for c in self.channels.values())
        if is_empty:
            self.queue_finished_signal.emit()
            self._reset_counters()

    def _reset_counters(self):
        """대기열 카운터를 초기 상태(0)로 리셋합니다.

        모든 큐 작업이 완료되었거나 큐를 초기화할 때, 진행 상황 표시를 원점으로 되돌리기 위해 호출됩니다.

        Args:
            None

        Returns:
            None
        """
        self._total_tasks = 0
        self._completed_tasks = 0

    def clear_queue(self):
        """대기 중인 모든 작업을 취소하고 큐를 비웁니다.

        사용자가 전체 작업을 취소하거나 대기열을 강제로 비워야 할 때 호출됩니다.
        단, 현재 실행 중(active)인 작업은 강제로 종료하지 않고 스스로 끝나도록 둡니다.

        Args:
            None

        Returns:
            None
        """
        # ===========================
        # [큐 초기화]
        # ===========================
        # 모든 채널의 대기열 비우기
        for channel in self.channels.values():
            channel["pending"].clear()
            
        # 카운터 초기화
        self._reset_counters()