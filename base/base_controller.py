"""기본 컨트롤러(Base Controller) 모듈입니다.

이 모듈은 UI(View)와 Worker(Model/Business Logic) 간의 통신을 중계하는 
`BaseController` 클래스를 제공합니다. 프로그램 전체의 비동기 작업(단일 작업 및
배치 작업)을 관리하며, PyQt의 시그널/슬롯 메커니즘을 기반으로 동작합니다.

주요 클래스:
    BaseController: 단일 스레드 작업 및 다중 배치 작업을 관리하고 신호를 중계하는 기반 컨트롤러.

의존성:
    PyQt6.QtCore: QObject 및 pyqtSignal을 통한 스레드 및 이벤트 관리.
"""

from PyQt6.QtCore import QObject, pyqtSignal

class BaseController(QObject):
    """UI와 Worker 사이에서 신호를 중계하고 스레드의 생명 주기를 관리하는 중앙 통제실(Base Controller)입니다.
    
    UI의 메서드를 직접 호출하지 않으며, 오직 시그널(Signal)만을 사용해 통신합니다. 
    단일 작업과 글로벌 대기열을 이용한 배치 작업을 모두 지원합니다.

    Attributes:
        log_signal (pyqtSignal): 실시간 로그 텍스트를 전달하는 시그널 (str).
        error_signal (pyqtSignal): 에러 팝업을 띄우기 위한 제목과 내용을 전달하는 시그널 (str, str).
        progress_signal (pyqtSignal): 진행률(0~100) 및 상태 메시지를 전달하는 시그널 (int, str).
        loading_signal (pyqtSignal): UI 화면 차단/활성화 및 커서 상태 제어를 위한 시그널 (bool).
        worker (BaseWorker, optional): 현재 실행 중인 단일 작업 워커 인스턴스.
        task_manager (BaseTaskManager, optional): 다중/배치 작업을 큐로 관리하는 글로벌 매니저 인스턴스.

    Inherits:
        QObject: Qt의 이벤트 루프와 시그널/슬롯 시스템을 사용하기 위해 상속.

    Collaborating Classes:
        BaseWorker: 실제 백그라운드 작업을 수행하며, 이 컨트롤러로 상태 시그널을 보냄.
        BaseTaskManager: 배치 작업 시 워커들을 큐에 등록하고 스케줄링.
    """
    # 📡 UI로 쏴줄 4개의 공통 중계 안테나 (BaseWorker의 시그널과 매칭됨)
    log_signal = pyqtSignal(str)              # 실시간 로그 텍스트
    error_signal = pyqtSignal(str, str)       # 에러 팝업용 (제목, 에러 내용)
    progress_signal = pyqtSignal(int, str)    # 진행률(0~100) 및 상태 메시지
    loading_signal = pyqtSignal(bool)         # UI 화면 차단/활성화 및 커서 모래시계 제어용

    def __init__(self, task_manager=None):
        """컨트롤러를 초기화하고 필요한 시그널을 연결합니다.

        Args:
            task_manager (BaseTaskManager, optional): main에서 생성한 글로벌 BaseTaskManager 객체.
                다중 스레드(Batch) 작업 시 큐(Queue) 관리를 위해 주입받습니다. Defaults to None.
        
        Returns:
            None
        
        Note:
            컨트롤러 생성 시점에 `task_manager`가 제공되면, 전체 대기열 진행 상태를 
            현재 컨트롤러의 진행률 시그널에 자동으로 연결합니다.
        """
        # ===========================
        # [초기화 및 속성 설정]
        # ===========================
        # 부모 클래스 초기화
        super().__init__()
        # 단일 작업용 변수
        self.worker = None 
        
        # 다중/병렬 작업용 글로벌 매니저 장착
        self.task_manager = task_manager
        
        # ===========================
        # [작업 관리자 연동]
        # ===========================
        # 글로벌 매니저가 장착되었다면, 전체 대기열 진행 상태를 이 컨트롤러의 진행률 안테나로 연결
        if self.task_manager:
            self.task_manager.queue_progress_signal.connect(self._on_queue_progress)
            self.task_manager.queue_finished_signal.connect(self._on_queue_finished)

    # ==========================================
    # [모드 1] 단일 작업 전용 (기존 작업 취소 후 1개만 실행)
    # ==========================================
    def start_worker(self, worker_instance):
        """단발성 작업을 실행하고 워커의 시그널을 컨트롤러와 연결합니다.

        기존에 실행 중인 단일 작업이 있다면 취소(cleanup)한 뒤 새로운 작업을 시작합니다. 
        사용자가 버튼을 여러 번 누르더라도 최신 작업 1개만 실행되도록 보장하기 위해 호출됩니다.

        Args:
            worker_instance (BaseWorker): 실행할 단일 백그라운드 작업 인스턴스.

        Returns:
            None
        
        Raises:
            Exception: 워커 실행 중 발생할 수 있는 런타임 에러(내부적으로 시그널로 처리됨).
        """
        # ===========================
        # [단일 워커 실행 준비]
        # ===========================
        # 기존 작업 취소 및 초기화
        self.cleanup_worker() 
        # 새 워커 할당
        self.worker = worker_instance
        
        # ===========================
        # [시그널 연결 및 실행]
        # ===========================
        # BaseWorker 상속 객체임을 확신하므로 hasattr 검사 없이 다이렉트 연결
        self.worker.log_signal.connect(self.log_signal.emit)
        self.worker.progress_signal.connect(self.progress_signal.emit)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.finished_signal.connect(self._on_worker_finished)
        
        # 메모리 누수 방지: 작업이 끝나면 알아서 삭제되도록 설정
        self.worker.finished.connect(self.worker.deleteLater)

        # UI에 로딩 상태 켜기 신호 발사
        self.loading_signal.emit(True)
        
        # 작업 시작
        self.worker.start()

    def _on_worker_finished(self, result):
        """단일 작업이 성공적으로 종료되었을 때 호출되는 콜백입니다.

        로딩 상태를 해제하기 위해 UI에 완료 신호를 보냅니다. 작업이 끝났음을
        사용자 인터페이스에 반영하고 입력 잠금을 풀기 위해 호출됩니다.

        Args:
            result (Any): 워커에서 전달받은 작업 결과 데이터.

        Returns:
            None
        """

        # UI에 로딩 상태 끄기 신호 발사 (일 끝났으니)
        self.loading_signal.emit(False)

    def _on_worker_error(self, error_msg: str):
        """단일 작업 중 에러가 발생했을 때 호출되는 콜백입니다.

        UI의 로딩 상태를 해제하고, 에러 메시지를 팝업으로 띄우도록 신호를 발생시킵니다.
        사용자에게 오류 원인을 안내하고 시스템을 대기 상태로 복구하기 위해 호출됩니다.

        Args:
            error_msg (str): 발생한 오류에 대한 설명 메시지.

        Returns:
            None
        """

        # UI에 로딩 상태 끄기 신호 발사 (일 망했으니)
        self.loading_signal.emit(False)

        # 왜 고장났는지를 위로 보내기; "작업 오류"
        self.error_signal.emit("작업 오류", error_msg)


    # ==========================================
    # [모드 2] 멀티/배치 작업 전용 (매니저의 Queue에 밀어넣기)
    # ==========================================
    def start_batch_workers(self, worker_list: list, channel="general"):
        """대량의 작업을 글로벌 큐에 추가하여 병렬 실행합니다.

        여러 파일이나 독립적인 작업을 한 번에 처리해야 할 때 글로벌 `task_manager`에
        작업을 위임하기 위해 호출됩니다.

        Args:
            worker_list (list): 큐에 추가할 `BaseWorker` 인스턴스들의 리스트.
            channel (str, optional): 작업을 할당할 큐 채널명. Defaults to "general".

        Returns:
            None

        Raises:
            None: 대신 task_manager가 없을 경우 error_signal을 통해 UI로 오류를 전달합니다.
        """
        # ===========================
        # [배치 작업 검증]
        # ===========================
        # 글로벌 매니저 존재 여부 확인
        if not self.task_manager:
            self.error_signal.emit("시스템 오류", "글로벌 TaskManager가 연결되지 않았습니다.")
            return

        # 리스트 비어있는지 검증
        if not worker_list:
            return

        # UI 로딩 상태 활성화
        self.loading_signal.emit(True)
        
        # ===========================
        # [워커 큐 등록]
        # ===========================
        for w in worker_list:
            # 개별 워커의 로그와 에러는 현재 컨트롤러의 안테나를 타도록 연결
            w.log_signal.connect(self.log_signal.emit)
            w.error_signal.connect(lambda msg: self.error_signal.emit("배치 작업 오류", msg))
            
            # 워커를 글로벌 큐에 던짐 (이후의 스케줄링과 시작은 매니저가 알아서 함)
            self.task_manager.add_task(w, channel=channel)

    def _on_queue_progress(self, completed: int, total: int):
        """큐의 전체 진행률을 계산하여 UI 시그널로 전달합니다.

        글로벌 Task Manager의 진행 상태가 변경될 때마다 이를 수신하여 퍼센티지(%)로 
        변환 후 진행률 바 등을 갱신하기 위해 호출됩니다.

        Args:
            completed (int): 현재까지 완료된 작업 수.
            total (int): 큐에 등록된 총 작업 수.

        Returns:
            None
        """
        if total > 0:
            percent = int((completed / total) * 100)
            self.progress_signal.emit(percent, f"대기열 처리 중 ({completed}/{total})")

    def _on_queue_finished(self):
        """글로벌 대기열의 모든 작업이 끝났을 때 호출됩니다.
        
        대기열이 비워졌으므로 UI의 로딩 상태를 해제하기 위해 호출됩니다.
        """
        self.loading_signal.emit(False)

    # ==========================================
    # 메모리 및 스레드 정리 로직
    # ==========================================
    def cleanup_worker(self):
        """실행 중인 단일 워커를 안전하게 중지하고 폐기합니다.

        프로그램 종료 시 혹은 새로운 단일 작업 시작 시 리소스 누수를 방지하고 
        충돌을 피하기 위해 기존 스레드를 정리하고자 호출됩니다.

        Args:
            None

        Returns:
            None
        """
        # ===========================
        # [기존 워커 정리]
        # ===========================
        try:
            # 워커가 존재하고 현재 실행 중인지 확인
            if self.worker and self.worker.isRunning():
                self.worker.stop() # 자연스러운 종료 유도
                
                # 2초간 대기 후 종료되지 않으면 강제 종료
                if not self.worker.wait(2000): # 2초간 기다림
                    self.worker.terminate()    # 그래도 안 끝나면 강제 종료
                    self.worker.wait()
        except RuntimeError:
            # C++ QThread 객체가 이미 deleteLater()로 인해 소멸된 경우 무시
            pass
        finally:
            # 참조 해제
            self.worker = None