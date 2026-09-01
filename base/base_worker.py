"""기본 워커(Base Worker) 모듈입니다.

이 모듈은 PyQt의 `QThread`를 상속받아 모든 백그라운드 스레드의 
뼈대가 되는 `BaseWorker` 클래스를 제공합니다. 스레드 작업 중 발생하는 
성공, 에러, 진행률, 로그 등을 외부로 전달하기 위한 공통 시그널을 정의합니다.

주요 클래스:
    BaseWorker: 예외 처리와 작업 취소(stop) 메커니즘을 내장한 기본 스레드 작업 클래스.

의존성:
    PyQt6.QtCore: QThread, pyqtSignal을 통한 백그라운드 스레드 및 이벤트 구현.
"""

from PyQt6.QtCore import QThread, pyqtSignal

class BaseWorker(QThread):
    """모든 백그라운드 스레드의 뼈대가 되는 기본 워커 클래스입니다.
    
    UI 프리징(멈춤 현상)을 방지하기 위해 무거운 작업을 별도 스레드로 분리합니다.
    BaseController 및 BaseTaskManager와 통신하기 위한 4개의 '표준 안테나(시그널)'를 제공하며,
    강제 종료(stop) 플래그와 안전한 예외 처리 구조를 포함합니다.

    Attributes:
        finished_signal (pyqtSignal): 작업 성공 시 최종 결과물(object) 전달.
        error_signal (pyqtSignal): 에러 발생 시 예외 메시지 텍스트(str) 전달.
        progress_signal (pyqtSignal): 진행률(0~100) 및 현재 상태 메시지(int, str) 전달.
        log_signal (pyqtSignal): 실시간 작업 로그 텍스트(str) 전달.

    Inherits:
        QThread: PyQt의 스레드 구현 기반.
    """
    finished_signal = pyqtSignal(object)   # 작업 성공 시 최종 결과물 전달
    error_signal = pyqtSignal(str)         # 에러 발생 시 예외 메시지 텍스트 전달
    progress_signal = pyqtSignal(int, str) # 진행률(0~100) 및 현재 상태 메시지
    log_signal = pyqtSignal(str)           # 실시간 작업 로그 텍스트

    def __init__(self, parent=None):
        """BaseWorker 인스턴스를 초기화합니다.

        Args:
            parent (QObject, optional): 부모 객체. Defaults to None.
        
        Returns:
            None
        """
        super().__init__(parent)
        self._is_running = True

    def run(self):
        """QThread가 `start()` 될 때 자동으로 실행되는 메인 흐름입니다.

        하위 로직(`do_work`)에서 발생하는 모든 에러를 안전하게 잡아내어 프로그램이 죽지 않게 
        방어하며, 그 결과를 UI(컨트롤러)로 올려보내기 위해 스레드 시작 시 호출됩니다.

        Args:
            None
        
        Returns:
            None
        """
        # ===========================
        # [스레드 실행 준비 및 작업 수행]
        # ===========================
        self._is_running = True
        try:
            # 자식 클래스에서 구현한 실제 작업 로직 실행
            result = self.do_work()
            
            # ===========================
            # [작업 결과 시그널 발송]
            # ===========================
            # 작업 도중 사용자가 강제로 취소(stop)하지 않았다면 성공 시그널 발사
            if self._is_running:
                self.finished_signal.emit(result)
                
        except Exception as e:
            # ===========================
            # [예외 처리 및 에러 시그널 발송]
            # ===========================
            # 작업 중 에러가 터지면 프로그램이 죽는 대신 에러 시그널을 밖으로 쏨
            if self._is_running:
                self.error_signal.emit(str(e))

    def do_work(self):
        """실제 비즈니스 로직을 작성하는 공간입니다. 하위 클래스에서 반드시 오버라이딩해야 합니다.

        실제로 스레드가 어떤 작업을 수행할지 정의하기 위해 하위 클래스에서 구현해야 합니다.
        
        [설계 가이드]
        이 안에서 `BaseService` 객체를 생성할 때, 
        `service = MyService(logger_callback=self.log_signal.emit)` 처럼
        워커의 시그널 발사 메서드 자체를 콜백으로 전달하면 로깅이 완벽하게 연결됩니다.

        Args:
            None

        Returns:
            Any: 작업 완료 후 UI로 반환할 결과물.

        Raises:
            NotImplementedError: 하위 클래스에서 오버라이딩하지 않았을 때 발생.
        """
        raise NotImplementedError("Subclasses must implement do_work()")

    def stop(self):
        """작업 중지(취소) 플래그를 설정합니다.

        BaseController나 TaskManager에서 현재 실행 중인 스레드를 안전하게 멈추고자 할 때 호출합니다.

        Args:
            None
        
        Returns:
            None
        """
        self._is_running = False

    def is_cancelled(self) -> bool:
        """현재 작업이 취소 요청을 받았는지 확인합니다.

        자식 클래스의 `do_work()` 내부에서 시간이 오래 걸리는 반복문을 돌 때, 
        `if self.is_cancelled(): break` 형태로 수시로 체크하여 스레드를 신속히 빠져나가게 할 때 호출됩니다.

        Args:
            None

        Returns:
            bool: 취소 요청이 들어왔다면 True, 그렇지 않다면 False.
        """
        return not self._is_running