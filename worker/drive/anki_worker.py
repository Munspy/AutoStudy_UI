import json
import os
import random
import shutil
import sqlite3
import tempfile
import zipfile

import genanki

from core.logger import GlobalLogger
from base.base_worker import BaseWorker
from core.container import AppContainer
from utils.auth_util import get_drive_service
from utils.config import Config
from utils.drive_api import in_memory_download_from_drive


class AnkiDeckMergeWorker(BaseWorker):
    """체크된 수업들의 _통합본.apkg를 다운로드하고, 폴더 구조에 맞춰 덱 이름을 상속 변경한 뒤 하나로 병합하여 로컬에 저장합니다."""
    def __init__(self, checked_lessons: list[str], output_path: str):
        super().__init__()
        self.checked_lessons = checked_lessons
        self.output_path = output_path
        self._folder_cache: dict = {}

    def _get_folder_path(self, file_parents: list[str], drive_service, root_id: str) -> list[str]:
        path = []
        current_parent_id = file_parents[0] if file_parents else None
        # 메모이제이션(캐시) 역할을 위해 간단한 딕셔너리를 워커 스코프에 둬도 좋지만 여기선 직접 호출
        while current_parent_id and current_parent_id != root_id:
            if current_parent_id in self._folder_cache:
                res = self._folder_cache[current_parent_id]
            else:
                res = drive_service.files().get(fileId=current_parent_id, fields="id, name, parents").execute()
                self._folder_cache[current_parent_id] = res
                
            path.append(res.get('name', 'Unknown'))
            parents = res.get('parents')
            current_parent_id = parents[0] if parents else None
        return list(reversed(path))

    def do_work(self):
        if not self.checked_lessons:
            self.error_signal.emit("선택된 수업이 없습니다.")
            return None

        GlobalLogger.info(f"🚀 총 {len(self.checked_lessons)}개 선택된 수업의 Anki 덱 병합 작업을 시작합니다...")
        

        sync_service = AppContainer.get_instance().drive_sync
        drive_service = get_drive_service()
        root_id = Config.TARGET_DRIVE_DIR

        GlobalLogger.info("☁️ 구글 드라이브 파일 목록을 조회하는 중...")
        drive_files, _, _ = sync_service.fetch_all_files("")
        
        if self.is_cancelled():
            return None

        sorted_lessons = sorted(self.checked_lessons)
        
        master_models = {}
        master_decks = {}
        master_notes = []
        
        # 미디어 파일을 모아둘 임시 디렉토리
        media_temp_dir = tempfile.mkdtemp(prefix="anki_media_")
        media_files_list = []
        
        # 유니크 ID 생성을 위한 편의 함수
        def gen_id(): return random.randrange(1 << 30, 1 << 31)

        try:
            for lesson in sorted_lessons:
                if self.is_cancelled():
                    GlobalLogger.info("Anki 병합 작업이 취소되었습니다.")
                    break
                    
                GlobalLogger.info(f"[{lesson}] 데이터 탐색 중...")
                
                apkg_file = next((f for f in drive_files if f['name'].startswith(lesson) and f['name'].endswith('_통합본.apkg')), None)
                if not apkg_file:
                    GlobalLogger.info(f"   ⚠️ [{lesson}] '_통합본.apkg' 파일을 찾을 수 없습니다. 건너뜁니다.")
                    continue

                # 폴더 계층 구조 추출
                parents = apkg_file.get('parents', [])
                folder_path_parts = self._get_folder_path(parents, drive_service, root_id)
                # 마지막 최하위 폴더명은 기존 덱 이름과 중복되므로 제외합니다
                if folder_path_parts:
                    folder_path_parts = folder_path_parts[:-1]
                
                folder_prefix = "::".join(folder_path_parts) if folder_path_parts else "기본"

                GlobalLogger.info(f"   ➔ [{lesson}] 다운로드 및 데이터베이스 파싱 중 (경로: {folder_prefix})...")
                
                # 메모리에 다운로드 후 임시 파일로 저장 (sqlite3 및 zipfile 처리를 위해)
                with in_memory_download_from_drive(apkg_file['id'], drive_service=drive_service) as io_stream:
                    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as temp_apkg:
                        temp_apkg.write(io_stream.getvalue())
                        temp_apkg_path = temp_apkg.name

                if self.is_cancelled():
                    break

                extract_dir = None
                try:
                    # 압축 풀기
                    extract_dir = tempfile.mkdtemp(prefix="anki_extract_")
                    with zipfile.ZipFile(temp_apkg_path, 'r') as zf:
                        zf.extractall(extract_dir)

                    db_path = os.path.join(extract_dir, 'collection.anki2')
                    if not os.path.exists(db_path):
                        GlobalLogger.info(f"   ❌ [{lesson}] 올바른 apkg 형식이 아닙니다 (DB 없음).")
                        continue

                    # 미디어 매핑 (파일 이름 '0', '1' -> 실제 파일명)
                    media_map_path = os.path.join(extract_dir, 'media')
                    media_map = {}
                    if os.path.exists(media_map_path):
                        with open(media_map_path, 'r', encoding='utf-8') as mf:
                            media_map = json.load(mf)
                    
                    # 미디어 파일 복사 및 수집
                    for key_str, real_name in media_map.items():
                        src_media_file = os.path.join(extract_dir, key_str)
                        if os.path.exists(src_media_file):
                            dst_media_file = os.path.join(media_temp_dir, real_name)
                            shutil.copy(src_media_file, dst_media_file)
                            media_files_list.append(dst_media_file)

                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()

                    # col 테이블에서 모델과 덱 가져오기
                    cursor.execute("SELECT models, decks FROM col LIMIT 1")
                    col_row = cursor.fetchone()
                    if not col_row:
                        continue
                    
                    models_dict = json.loads(col_row[0])
                    decks_dict = json.loads(col_row[1])

                    # 모델 파싱
                    mid_mapping = {} # 기존 mid -> genanki.Model
                    for mid_str, m_data in models_dict.items():
                        m_name = m_data.get('name', 'Model')
                        # 중복 모델 이름 처리 방지 (모델 ID 자체를 유지하거나 해싱)
                        m_id = m_data.get('id', gen_id())
                        if m_name not in master_models:
                            fields = [{'name': f.get('name')} for f in m_data.get('flds', [])]
                            templates = [{'name': t.get('name'), 'qfmt': t.get('qfmt'), 'afmt': t.get('afmt')} for t in m_data.get('tmpls', [])]
                            css = m_data.get('css', '')
                            
                            model = genanki.Model(
                                m_id,
                                m_name,
                                fields=fields,
                                templates=templates,
                                css=css
                            )
                            master_models[m_name] = model
                        mid_mapping[mid_str] = master_models[m_name]

                    # 덱 파싱 (이름 변환)
                    did_to_deck = {}
                    for did_str, d_data in decks_dict.items():
                        old_name = d_data.get('name', 'Default')
                        # 'Default' 같은 기본 덱은 필터링하거나 변환
                        if old_name.lower() == 'default':
                            new_name = folder_prefix
                        else:
                            new_name = f"{folder_prefix}::{old_name}"
                        
                        if new_name not in master_decks:
                            d_id = gen_id()
                            deck = genanki.Deck(d_id, new_name)
                            master_decks[new_name] = deck
                        
                        did_to_deck[did_str] = master_decks[new_name]

                    # 노트 및 카드 추출
                    # 노트 하나가 어느 덱에 속하는지는 첫번째 카드의 did로 결정
                    cursor.execute("SELECT id, mid, flds, tags FROM notes")
                    notes = cursor.fetchall()
                    
                    for n in notes:
                        n_id, mid, flds, tags_str = n
                        mid_str = str(mid)
                        if mid_str not in mid_mapping:
                            continue
                            
                        # 이 노트의 카드들이 속한 덱 찾기 (첫번째 카드 기준)
                        cursor.execute("SELECT did FROM cards WHERE nid = ? LIMIT 1", (n_id,))
                        c_row = cursor.fetchone()
                        if not c_row:
                            continue
                            
                        did_str = str(c_row[0])
                        target_deck = did_to_deck.get(did_str)
                        if not target_deck:
                            continue

                        flds_list = flds.split('\x1f')
                        # 태그 파싱
                        tags = [t for t in tags_str.split(' ') if t] if tags_str else []
                        
                        note = genanki.Note(
                            model=mid_mapping[mid_str],
                            fields=flds_list,
                            tags=tags,
                            guid=n_id # genanki가 guid를 유니크하게 다룰 수 있도록
                        )
                        target_deck.add_note(note)
                        
                    conn.close()

                except Exception as e:
                    GlobalLogger.info(f"   ❌ [{lesson}] 파싱 실패: {e}")
                finally:
                    if os.path.exists(temp_apkg_path):
                        os.unlink(temp_apkg_path)
                    if extract_dir:
                        shutil.rmtree(extract_dir, ignore_errors=True)

            if self.is_cancelled():
                return None

            if master_decks:
                GlobalLogger.info(f"💾 패키징 중... (총 {len(master_decks)}개의 덱 병합)")
                package = genanki.Package(list(master_decks.values()))
                
                # 중복 미디어 파일 제거
                unique_media = list(set(media_files_list))
                package.media_files = unique_media
                
                package.write_to_file(self.output_path)
                return "Anki 덱 병합 및 저장이 완료되었습니다."
            else:
                self.error_signal.emit("병합할 Anki 덱 데이터가 없습니다.")
                return None
        finally:
            shutil.rmtree(media_temp_dir, ignore_errors=True)
