# base/base_controller.py
from PyQt6.QtCore import QObject, pyqtSignal

class BaseController(QObject):
    """
    UI와 Worker 사이에서 신호를 중계하고 스레드의 생명 주기를 관리하는 중앙 통제실입니다.
    UI의 메서드를 직접 호출하지 않으며, 오직 시그널(Signal)만을 사용해 통신합니다.
    """
    # 📡 UI로 쏴줄 4개의 공통 중계 안테나 (BaseWorker의 시그널과 매칭됨)
    log_signal = pyqtSignal(str)              # 실시간 로그 텍스트
    error_signal = pyqtSignal(str, str)       # 에러 팝업용 (제목, 에러 내용)
    progress_signal = pyqtSignal(int, str)    # 진행률(0~100) 및 상태 메시지
    loading_signal = pyqtSignal(bool)         # UI 화면 차단/활성화 및 커서 모래시계 제어용

    def __init__(self, task_manager=None):
        """
        :param task_manager: main에서 생성한 글로벌 BaseTaskManager 객체. 
                             다중 스레드(Batch) 작업 시 큐(Queue) 관리를 위해 주입받습니다.
        """
        super().__init__()
        # 단일 작업용 변수
        self.worker = None 
        
        # 다중/병렬 작업용 글로벌 매니저 장착
        self.task_manager = task_manager
        
        # 글로벌 매니저가 장착되었다면, 전체 대기열 진행 상태를 이 컨트롤러의 진행률 안테나로 연결
        if self.task_manager:
            self.task_manager.queue_progress_signal.connect(self._on_queue_progress)

    # ==========================================
    # [모드 1] 단일 작업 전용 (기존 작업 취소 후 1개만 실행)
    # ==========================================
    def start_worker(self, worker_instance):
        """
        단발성 작업을 실행할 때 사용합니다. (예: 로그인, 단일 파일 처리 등)
        사용자가 버튼을 연타하더라도 이전 작업을 죽이고 최신 작업 1개만 실행합니다.
        """
        self.cleanup_worker() 
        self.worker = worker_instance
        
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
        """단일 작업이 성공적으로 끝났을 때 호출됩니다."""

        # UI에 로딩 상태 끄기 신호 발사 (일 끝났으니)
        self.loading_signal.emit(False)

        # 'Controller' 특이적인 '작업 끝내고 할 일' 시행
        self.handle_result(result)

    def _on_worker_error(self, error_msg: str):
        """단일 작업 중 에러가 발생했을 때 호출됩니다."""

        # UI에 로딩 상태 끄기 신호 발사 (일 망했으니)
        self.loading_signal.emit(False)

        # 왜 고장났는지를 위로 보내기; "작업 오류"
        self.error_signal.emit("작업 오류", error_msg)

    # 문득 고민이 들어서 여기다가 미리 적어놓음
    # 지금까지는 하나의 UI -> 하나의 Controller로 지금까지 개발하였는데
    # 이 handle_result(self, result): 은 '하나의 기능'을 담당할 때 필요한 것
    # 따라서, 하나의 UI에 하나의 Controller를 고집하기 보다는
    # 하나의 위젯, 큰 기능 단위에 하나의 Controller를 매칭시키는 것이 더 알맞다.
    # 어지간 하면 없앨 생각을 합시다
    def handle_result(self, result):
        """
        작업 성공 결과(result)를 받아 처리하는 곳입니다.
        이 클래스를 상속받는 자식 컨트롤러(예: DriveSyncController)에서 오버라이딩하여 구현합니다.
        """
        pass

    # ==========================================
    # [모드 2] 멀티/배치 작업 전용 (매니저의 Queue에 밀어넣기)
    # ==========================================
    def start_batch_workers(self, worker_list: list, channel="general"):
        """
        대량의 작업을 글로벌 큐에 넣고 병렬 실행할 때 사용합니다.
        """
        if not self.task_manager:
            self.error_signal.emit("시스템 오류", "글로벌 TaskManager가 연결되지 않았습니다.")
            return

        if not worker_list:
            return

        self.loading_signal.emit(True)
        
        for w in worker_list:
            # 개별 워커의 로그와 에러는 현재 컨트롤러의 안테나를 타도록 연결
            w.log_signal.connect(self.log_signal.emit)
            w.error_signal.connect(lambda msg: self.error_signal.emit("배치 작업 오류", msg))
            
            # 워커를 글로벌 큐에 던짐 (이후의 스케줄링과 시작은 매니저가 알아서 함)
            self.task_manager.add_task(w, channel=channel)

    def _on_queue_progress(self, completed: int, total: int):
        """큐의 전체 진행률을 UI에 맞게 변환하여 쏴줍니다."""
        if total > 0:
            percent = int((completed / total) * 100)
            self.progress_signal.emit(percent, f"대기열 처리 중 ({completed}/{total})")

    # ==========================================
    # 메모리 및 스레드 정리 로직
    # ==========================================
    def cleanup_worker(self):
        """
        실행 중인 단일 워커를 안전하게 중지하고 폐기합니다.
        프로그램 종료 시나, 새로운 단일 작업이 시작될 때 호출됩니다.
        """
        try:
            if self.worker and self.worker.isRunning():
                if hasattr(self.worker, 'stop'):
                    self.worker.stop() # 자연스러운 종료 유도
                
                if not self.worker.wait(2000): # 2초간 기다림
                    self.worker.terminate()    # 그래도 안 끝나면 강제 종료
                    self.worker.wait()
        except RuntimeError:
            # C++ QThread 객체가 이미 deleteLater()로 인해 소멸된 경우 무시
            pass
        finally:
            self.worker = None