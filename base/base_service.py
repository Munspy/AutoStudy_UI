# service/base_service.py
class BaseService:
    def __init__(self, logger_callback: callable = None):
        # 👈 객체를 만들 때 미리 콜백을 장착해 둡니다.
        self.logger_callback = logger_callback

    def _log(self, msg: str):
        # 👈 매번 인자로 안 받고, 내부에 저장된 콜백을 알아서 씁니다.
        if self.logger_callback:
            self.logger_callback(msg)
        else:
            print(msg)