from PyQt6.QtCore import QObject, pyqtSignal

class _GlobalLogger(QObject):
    """
    앱 전역에서 발생하는 로그를 중앙에서 수집하여 메인 스레드(UI)로 안전하게 전달하는 이벤트 버스.
    """
    # PyQt 스레드 안전성을 보장하기 위해 QObject와 pyqtSignal 상속 사용
    log_signal = pyqtSignal(str)
    
    def info(self, msg: str):
        """
        비즈니스 로직(Service) 등에서 로그를 기록할 때 호출하는 메서드.
        """
        self.log_signal.emit(msg)

# 앱 구동 시 가장 먼저 생성되는 싱글톤 전역 로거 객체
GlobalLogger = _GlobalLogger()
