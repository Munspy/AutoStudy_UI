import csv
import threading
from pathlib import Path
from typing import List, Dict, Optional, Callable

from base.base_service import BaseService

class PlaylistRepository(BaseService):
    """
    재생목록 메타데이터(CSV)의 저장, 조회, 수정, 삭제(CRUD) 등
    데이터 영속성(Persistence) 관리만을 전담하는 저장소 클래스입니다.
    """
    def __init__(
        self, 
        csv_file_path: str = "playlists.csv",
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        # [최적화 2] BaseService 초기화로 로깅 시스템 활성화
        super().__init__(logger_callback=logger_callback)
        
        # [최적화 3] pathlib을 도입하여 객체 지향적이고 안전한 파일 경로 제어
        self.csv_file: Path = Path(csv_file_path)
        
        # [최적화 1] 스레드 안전성(Thread-Safety) 확보. 
        # 같은 스레드 내에서 연달아 Lock을 획득해도 데드락이 발생하지 않는 RLock 사용
        self._lock = threading.RLock()
        
        self._init_csv()

    def _init_csv(self) -> None:
        """CSV 파일이 존재하지 않으면 헤더와 함께 초기화합니다."""
        with self._lock:
            if not self.csv_file.exists():
                try:
                    # 부모 디렉토리가 없을 경우를 대비한 자동 생성 로직 추가
                    self.csv_file.parent.mkdir(parents=True, exist_ok=True)
                    with self.csv_file.open('w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["name", "url", "playlist_id"])
                    self._log(f"📄 [Repository] 새 CSV 데이터베이스 파일 생성 완료: {self.csv_file.name}")
                except Exception as e:
                    self._log(f"❌ [Repository] CSV 초기화 중 오류 발생: {str(e)}")

    def load_playlists(self) -> List[Dict[str, str]]:
        """데이터베이스에서 재생목록 정보를 읽어 반환합니다."""
        playlists: List[Dict[str, str]] = []
        with self._lock:
            if self.csv_file.exists():
                try:
                    with self.csv_file.open('r', newline='', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            playlists.append(row)
                except Exception as e:
                    self._log(f"❌ [Repository] 데이터 로드 중 오류 발생: {str(e)}")
        return playlists

    def _rewrite_csv(self, playlists: List[Dict[str, str]]) -> None:
        """메모리의 리스트 데이터를 CSV 파일에 안전하게 덮어씁니다."""
        with self._lock:
            try:
                with self.csv_file.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["name", "url", "playlist_id"])
                    for p in playlists:
                        # 누락된 키가 있더라도 에러가 발생하지 않도록 .get() 사용 방어
                        writer.writerow([
                            p.get('name', ''), 
                            p.get('url', ''), 
                            p.get('playlist_id', '')
                        ])
            except Exception as e:
                self._log(f"❌ [Repository] 데이터 저장 중 오류 발생: {str(e)}")

    def add_playlist(self, name: str, url: str, playlist_id: str) -> None:
        """새로운 재생목록을 추가합니다."""
        # 읽기 -> 리스트 조작 -> 쓰기 전체 과정을 원자적 트랜잭션으로 보호
        with self._lock:
            playlists = self.load_playlists()
            playlists.append({"name": name, "url": url, "playlist_id": playlist_id})
            self._rewrite_csv(playlists)
            self._log(f"✅ [Repository] 항목 추가 완료: {name}")

    def delete_playlist(self, playlist_id: str) -> None:
        """특정 재생목록을 삭제합니다."""
        with self._lock:
            playlists = self.load_playlists()
            # 해당 ID를 가진 항목을 제외하고 리스트 재구성
            new_playlists = [p for p in playlists if p.get('playlist_id') != playlist_id]
            
            if len(playlists) != len(new_playlists):
                self._rewrite_csv(new_playlists)
                self._log(f"🗑️ [Repository] 항목 삭제 완료 (ID: {playlist_id})")

    def rename_playlist(self, playlist_id: str, new_name: str) -> None:
        """특정 재생목록의 이름을 변경합니다."""
        with self._lock:
            playlists = self.load_playlists()
            modified = False
            for p in playlists:
                if p.get('playlist_id') == playlist_id:
                    p['name'] = new_name
                    modified = True
                    break
                    
            if modified:
                self._rewrite_csv(playlists)
                self._log(f"✏️ [Repository] 항목 이름 변경 완료 (ID: {playlist_id} -> {new_name})")