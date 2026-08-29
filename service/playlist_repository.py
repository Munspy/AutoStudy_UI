"""유튜브 재생목록 메타데이터 영속성 관리 저장소 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.[cite: 1]
구체적으로는 데이터 접근 및 영속성(Persistence)을 전담하는 저장소(Repository) 패턴을 구현하고 있습니다.

Whisper AI 기반 음성 변환을 위해 원본 미디어를 유튜브에서 다운로드하거나, 
반대로 가공이 완료된 학습 자료를 유튜브 재생목록으로 동기화하는 비동기 백그라운드 Worker 스레드와 Controller가, 
재생목록 메타데이터(이름, URL, 고유 ID)를 스레드 안전(Thread-safe)하게 저장하고 조회할 수 있도록 
로컬 CSV 기반의 CRUD(Create, Read, Update, Delete) 인터페이스를 제공하는 핵심 데이터베이스 역할을 수행합니다.
"""
import csv
import threading
from pathlib import Path
from typing import List, Dict, Optional, Callable

from base.base_service import BaseService

class PlaylistRepository(BaseService):
    """재생목록 메타데이터(CSV)의 저장, 조회, 수정, 삭제(CRUD) 등 데이터 영속성(Persistence) 관리만을 전담하는 저장소 클래스.

    단일 책임 원칙(SRP)에 따라, 이 클래스는 YouTube Data API와의 네트워크 통신이나 UI 렌더링 로직을 전혀 포함하지 않으며, 
    오직 로컬 파일 시스템의 `.csv` 데이터베이스 파일 상태를 무결하게 관리하는 역할만 수행합니다.

    내부 주요 상태로 물리적 파일 경로(`self.csv_file`)와 다중 스레드 환경에서의 I/O 충돌을 막기 위한 
    재진입 가능 락(`self._lock`, RLock)을 보유하고 있습니다. 주로 유튜브 연동을 처리하는 Controller나 
    비동기 작업을 수행하는 Worker 계층에 의해 호출되어 데이터를 공급하거나 업데이트합니다.
    """
    def __init__(
        self, 
        csv_file_path: str = "playlists.csv",
        logger_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """PlaylistRepository 인스턴스를 초기화하고 스레드 락 및 데이터베이스 파일을 준비합니다.

        Args:
            csv_file_path (str, optional): 재생목록 데이터를 영속화할 로컬 CSV 파일의 경로. 기본값은 "playlists.csv"입니다.
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 처리 중 발생하는 로컬 DB 접근 로그를 
                메인 UI 스레드로 안전하게 전달하기 위한 콜백 함수. Defaults to None.
        """
        # [최적화 2] BaseService 초기화로 로깅 시스템 활성화
        super().__init__(logger_callback=logger_callback)
        
        # [최적화 3] pathlib을 도입하여 객체 지향적이고 안전한 파일 경로 제어
        self.csv_file: Path = Path(csv_file_path)
        
        # [최적화 1] 스레드 안전성(Thread-Safety) 확보. 
        # 같은 스레드 내에서 연달아 Lock을 획득해도 데드락이 발생하지 않는 RLock 사용
        self._lock = threading.RLock()
        
        self._init_csv()

    def _init_csv(self) -> None:
        """CSV 데이터베이스 파일이 존재하지 않을 경우 기본 헤더를 포함하여 초기화(Self-healing)합니다.

        자동화 파이프라인의 백그라운드 Worker는 사용자의 개입 없이 지속적으로 동작해야 합니다. 
        만약 사용자의 실수나 시스템 오류로 로컬 데이터베이스 파일(`.csv`)이 삭제되었을 경우, 
        시스템이 크래시(Crash)되는 대신 스스로 디렉토리 트리와 빈 CSV 파일을 복구하여 
        파이프라인의 연속성을 보장하는 강력한 방어 로직입니다. 내부적으로 `_lock`을 사용하여 
        여러 스레드가 동시에 초기화를 시도하는 Race Condition을 방지합니다.

        Args:
            없음

        Returns:
            None
        """
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
        """로컬 CSV 데이터베이스 파일에서 재생목록 정보를 읽어 메모리 구조(List of Dicts)로 반환합니다.

        메인 UI가 로드되거나 Watchdog Worker가 동기화 대상을 스캔할 때 빈번하게 호출되는 Read 엔트리포인트입니다. 
        파일 I/O 작업 중 다른 스레드가 쓰기(Write) 연산을 수행하여 파일이 손상(Incomplete read)되는 것을 막기 위해 
        전체 읽기 블록이 `_lock`으로 강하게 보호됩니다. 읽기 중 예외가 발생하더라도 빈 리스트를 반환하여 
        호출자(Controller/Service)가 에러 처리 없이 안전하게 Fallback 할 수 있도록 돕습니다.

        Args:
            없음

        Returns:
            List[Dict[str, str]]: 각 딕셔너리가 단일 재생목록 정보('name', 'url', 'playlist_id')를 
                포함하는 리스트. 파일이 없거나 오류 발생 시 빈 리스트(`[]`)를 반환합니다.
        """
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
        """메모리에 로드되어 수정된 재생목록 리스트를 물리적 CSV 파일에 안전하게 덮어씁니다(Overwrite).

        CSV 파일 특성상 특정 행(Row)만 무작위 접근(Random Access)하여 수정하는 것이 까다롭습니다. 
        따라서 이 클래스의 모든 데이터 변경 연산(Add, Delete, Rename)은 메모리에서 전체 리스트를 조작한 후 
        이 내부 메서드를 통해 파일 전체를 새롭게 덮어쓰는(Rewrite) 방식을 취합니다. 
        데이터 누락 방지를 위해 `.get()` 메서드를 활용하여 키 누락 예외를 방어하며, RLock 안에서 실행되므로 
        쓰기 도중 다른 스레드의 간섭을 원천 차단합니다.

        Args:
            playlists (List[Dict[str, str]]): CSV 파일에 기록할 최신 상태의 재생목록 딕셔너리 리스트.

        Returns:
            None
        """
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
        """새로운 재생목록 엔티티를 데이터베이스에 추가합니다(Create).

        비동기 환경에서 여러 사용자의 액션이나 Worker의 백그라운드 스캔으로 인해 동시에 여러 재생목록이 
        등록될 수 있습니다. 이를 안전하게 처리하기 위해 '기존 데이터 로드 -> 메모리 배열에 새 항목 추가 -> CSV 전체 덮어쓰기'의 
        일련의 과정을 하나의 원자적 트랜잭션(Atomic Transaction)으로 간주하고 `with self._lock:` 블록으로 묶어 
        데이터 경합(Race Condition)으로 인한 정보 유실을 방지합니다.

        Args:
            name (str): 사용자에게 보여질 재생목록의 이름.
            url (str): 해당 유튜브 재생목록의 전체 URL 경로.
            playlist_id (str): API 통신 시 활용되는 재생목록의 고유 식별자(ID).

        Returns:
            None
        """
        # 읽기 -> 리스트 조작 -> 쓰기 전체 과정을 원자적 트랜잭션으로 보호
        with self._lock:
            playlists = self.load_playlists()
            playlists.append({"name": name, "url": url, "playlist_id": playlist_id})
            self._rewrite_csv(playlists)
            self._log(f"✅ [Repository] 항목 추가 완료: {name}")

    def delete_playlist(self, playlist_id: str) -> None:
        """특정 재생목록 고유 ID를 기반으로 데이터베이스에서 해당 항목을 완전히 제거합니다(Delete).

        사용자가 UI에서 특정 재생목록의 동기화 연동을 해제(삭제)하고자 할 때 호출됩니다. 
        메모리 상에 로드된 전체 리스트에서 대상 `playlist_id`와 일치하지 않는 항목들만으로 
        새로운 배열을 필터링(List Comprehension)한 뒤, 이를 디스크에 재기록(Rewrite)하여 물리적인 삭제를 달성합니다.

        Args:
            playlist_id (str): 데이터베이스에서 삭제하고자 하는 대상 재생목록의 고유 식별자(ID).

        Returns:
            None
        """
        with self._lock:
            playlists = self.load_playlists()
            # 해당 ID를 가진 항목을 제외하고 리스트 재구성
            new_playlists = [p for p in playlists if p.get('playlist_id') != playlist_id]
            
            if len(playlists) != len(new_playlists):
                self._rewrite_csv(new_playlists)
                self._log(f"🗑️ [Repository] 항목 삭제 완료 (ID: {playlist_id})")

    def rename_playlist(self, playlist_id: str, new_name: str) -> None:
        """기존 데이터베이스에 존재하는 특정 재생목록의 이름을 새로운 이름으로 갱신합니다(Update).

        학습자의 편의에 따라 자동화 파이프라인에서 관리되는 폴더명이나 재생목록의 별칭(Alias)을 
        변경해야 할 때 사용되는 업데이트 로직입니다. 
        메모리 리스트를 순회하며 타겟 ID를 찾아 이름(`name`) 필드만 단일 수정(In-place update)한 후, 
        실제 변경 사항이 발생했을 때만(디스크 I/O 최적화) `_rewrite_csv`를 호출하여 상태를 영속화합니다.

        Args:
            playlist_id (str): 이름을 변경할 대상 재생목록의 고유 식별자(ID).
            new_name (str): 변경하고자 하는 새로운 재생목록의 이름 문자열.

        Returns:
            None
        """
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