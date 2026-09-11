"""기본 서비스(Base Service) 모듈입니다.

이 모듈은 서비스 계층의 최상위 부모 클래스인 `BaseService`를 정의합니다.
서비스 로직에서 발생하는 로그 메시지를 UI나 콘솔 등 원하는 곳으로 
전달하기 위한 공통 로깅 구조를 제공합니다.

주요 클래스:
    BaseService: 콜백 기반의 유연한 로깅을 지원하는 서비스 기반 클래스.
"""

from core.logger import GlobalLogger

class BaseService:
    """콜백 기반의 커스텀 로깅을 대체한 중앙 이벤트 버스(GlobalLogger) 기반 서비스 부모 클래스.
    
    비즈니스 로직(Service)에서 발생하는 로그를 직접 `print` 하지 않고,
    `GlobalLogger`를 통해 외부(예: UI, 메인 윈도우)로 방송(Publish)합니다.

    Attributes:
        logger_callback (callable, optional): 과거 버전 호환성을 위해 남겨둔 인자. 더 이상 사용되지 않습니다.
    """

    def __init__(self, logger_callback=None, **kwargs):
        """BaseService 인스턴스를 초기화합니다.

        Args:
            logger_callback (callable, optional): 과거 호환용 (무시됨).
        
        Returns:
            None
        """
        # ===========================
        # [초기화 및 속성 설정]
        # ===========================
        # 👈 DI 도입 전 레거시 코드와의 호환성을 위해 파라미터는 받지만 사용하지 않음
        pass


    @property
    def app(self):
        """자식 서비스들이 DI 컨테이너(AppContainer)의 다른 서비스에 접근하기 위한 글로벌 단축키입니다.
        예: self.app.naming_service
        """
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
        # ===========================
        # [로그 출력 처리]
        # ===========================
        GlobalLogger.info(msg)