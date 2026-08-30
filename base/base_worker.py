# base/base_worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class BaseWorker(QThread):
    """
    모든 백그라운드 스레드의 뼈대가 되는 기본 워커 클래스입니다.
    BaseController 및 BaseTaskManager와 통신하기 위한 4개의 '표준 안테나(시그널)'를 제공합니다.
    """
    finished_signal = pyqtSignal(object)   # 작업 성공 시 최종 결과물 전달
    error_signal = pyqtSignal(str)         # 에러 발생 시 예외 메시지 텍스트 전달
    progress_signal = pyqtSignal(int, str) # 진행률(0~100) 및 현재 상태 메시지
    log_signal = pyqtSignal(str)           # 실시간 작업 로그 텍스트

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = True

    def run(self):
        """
        QThread가 start() 될 때 자동으로 실행되는 메인 흐름입니다.
        하위 로직에서 발생하는 모든 에러를 튕겨내지 않고 안전하게 잡아내어 UI로 올려보냅니다.
        """
        self._is_running = True
        try:
            # 자식 클래스에서 구현한 실제 작업 로직 실행
            result = self.do_work()
            
            # 작업 도중 사용자가 강제로 취소(stop)하지 않았다면 성공 시그널 발사
            if self._is_running:
                self.finished_signal.emit(result)
                
        except Exception as e:
            # 작업 중 에러가 터지면 프로그램이 죽는 대신 에러 시그널을 밖으로 쏨
            if self._is_running:
                self.error_signal.emit(str(e))

    def do_work(self):
        """
        실제 비즈니스 로직을 작성하는 공간입니다. 하위 클래스에서 무조건 오버라이딩해야 합니다.
        
        [설계 가이드]
        이 안에서 BaseService 객체를 생성할 때, 
        service = MyService(logger_callback=self.log_signal.emit) 처럼
        워커의 시그널 발사 버튼 자체를 콜백으로 쥐여주면 완벽하게 연결됩니다.
        """
        raise NotImplementedError("Subclasses must implement do_work()")

    def stop(self):
        """
        작업 중지(취소) 플래그를 설정합니다.
        BaseController나 TaskManager에서 스레드를 멈출 때 호출합니다.
        """
        self._is_running = False

    def is_cancelled(self) -> bool:
        """
        현재 작업이 취소 요청을 받았는지 확인합니다.
        자식 클래스의 do_work() 내부에서 시간이 오래 걸리는 반복문을 돌 때, 
        if self.is_cancelled(): break 형태로 수시로 체크해 주어야 스레드가 안전하게 종료됩니다.
        """
        return not self._is_running