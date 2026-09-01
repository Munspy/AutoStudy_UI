"""기본 서비스(Base Service) 모듈입니다.

이 모듈은 서비스 계층의 최상위 부모 클래스인 `BaseService`를 정의합니다.
서비스 로직에서 발생하는 로그 메시지를 UI나 콘솔 등 원하는 곳으로 
전달하기 위한 공통 로깅 구조를 제공합니다.

주요 클래스:
    BaseService: 콜백 기반의 유연한 로깅을 지원하는 서비스 기반 클래스.
"""

class BaseService:
    """콜백 기반의 커스텀 로깅을 지원하는 서비스 기반 클래스입니다.
    
    비즈니스 로직(Service)에서 발생하는 로그를 직접 `print` 하지 않고,
    생성 시 주입받은 콜백 함수를 통해 외부(예: UI, 컨트롤러)로 전달할 수 있게 합니다.

    Attributes:
        logger_callback (callable, optional): 로그 메시지(str)를 인자로 받아 처리하는 함수.
    """

    def __init__(self, logger_callback: callable = None):
        """BaseService 인스턴스를 초기화합니다.

        Args:
            logger_callback (callable, optional): 로그를 출력할 때 호출할 콜백 함수. Defaults to None.
        
        Returns:
            None
        """
        # ===========================
        # [초기화 및 속성 설정]
        # ===========================
        # 👈 객체를 만들 때 미리 콜백을 장착해 둡니다.
        # 외부로 로그를 전달할 콜백 함수 저장
        self.logger_callback = logger_callback

    def _log(self, msg: str):
        """내부 서비스 로직 중 발생하는 메시지를 로깅합니다.

        콜백이 등록되어 있다면 콜백을 호출하고, 그렇지 않다면 콘솔에 출력합니다.
        서비스 수행 과정이나 상태를 외부 UI로 알리기 위해 내부적으로 호출됩니다.

        Args:
            msg (str): 출력할 로그 메시지.

        Returns:
            None
        """
        # ===========================
        # [로그 출력 처리]
        # ===========================
        # 👈 매번 인자로 안 받고, 내부에 저장된 콜백을 알아서 씁니다.
        # 콜백이 존재하면 콜백 함수를 통해 로그 메시지 전달
        if self.logger_callback:
            self.logger_callback(msg)
        # 콜백이 없으면 기본 콘솔에 출력
        else:
            print(msg)