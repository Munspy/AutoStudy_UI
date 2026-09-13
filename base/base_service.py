"""기본 서비스(Base Service) 모듈입니다.

이 모듈은 서비스 계층의 최상위 부모 클래스인 `BaseService`를 정의합니다.
1. 서비스 로직에서 발생하는 로그 메시지를 GlobalLogger로 전달하기 위한 공통 로깅 구조를 제공합니다.
2. app 을 통해서 AppContainer 쉽게 부를 수 있게 만듭니다.
주요 클래스:
    BaseService: 콜백 기반의 유연한 로깅을 지원하는 서비스 기반 클래스.
"""

from core.logger import GlobalLogger

class BaseService:
    """중앙 이벤트 버스(GlobalLogger) 기반 서비스 부모 클래스.
    
    비즈니스 로직(Service)에서 발생하는 로그를 직접 `print` 하지 않고,
    `GlobalLogger`를 통해 외부(예: UI, 메인 윈도우)로 방송(Publish)합니다.
    """

    def __init__(self):
        """BaseService 인스턴스를 초기화합니다."""
        pass


    @property
    def app(self):
        """자식 서비스들이 DI 컨테이너(AppContainer)의 다른 서비스에 접근하기 위한 글로벌 단축키입니다.
        예: self.app.naming_service
        """
        # lazy loading 구현
        from core.container import AppContainer
        return AppContainer.get_instance()

    def _log(self, msg: str):
        """내부 서비스 로직 중 발생하는 메시지를 로깅합니다.

        GlobalLogger를 통해 중앙 UI로 즉시 메시지를 방송합니다.

        Args:
            msg (str): 출력할 로그 메시지.

        Returns:
            None
        """

        GlobalLogger.info(msg)