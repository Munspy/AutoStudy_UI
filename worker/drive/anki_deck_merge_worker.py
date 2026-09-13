from base.base_worker import BaseWorker

class AnkiDeckMergeWorker(BaseWorker):
    """체크된 수업들의 _통합본.apkg를 다운로드하고, 폴더 구조에 맞춰 덱 이름을 상속 변경한 뒤 하나로 병합하여 로컬에 저장합니다."""
    def __init__(self, checked_lessons: list[str], output_path: str):
        super().__init__()
        self.checked_lessons = checked_lessons
        self.output_path = output_path

    def do_work(self):

        # 로그에다가 시작 표시
        self._log("🚀 Anki 덱 병합 및 빌드 작업 시작")

        # merge 작업 시작 (자세한 로직은 service로 이관)
        result = self.app.anki.merge_apkg_files(
            self.checked_lessons, 
            self.output_path, 
            cancel_checker=self.is_cancelled
        )

        if result and "없습니다" in result:
            self.error_signal.emit(result)
            return None
            
        return result
