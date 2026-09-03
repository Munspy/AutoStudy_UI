from typing import Optional, Callable
from base.base_service import BaseService
from utils.drive_api import get_all_drive_files, move_drive_file
from utils.auth_util import get_drive_service
from utils.config import Config

class FolderManagementService(BaseService):
    """구글 드라이브 내 교시별 전용 폴더 트리 탐색, 생성 및 파일 자동 이동을 전담하는 도메인 서비스."""

    def __init__(self, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(logger_callback=logger_callback)
        self.drive_service = get_drive_service()
        self.root_folder_id = Config.TARGET_DRIVE_DIR

    def _get_file_depth(self, file_id, parents_cache):
        """특정 파일의 깊이를 계산합니다."""
        depth = 0
        current_id = file_id
        
        while current_id:
            if current_id == self.root_folder_id:
                break
                
            # 부모 정보 가져오기
            if current_id not in parents_cache:
                try:
                    file_info = self.drive_service.files().get(
                        fileId=current_id, fields='parents'
                    ).execute()
                    parents = file_info.get('parents', [])
                    parents_cache[current_id] = parents[0] if parents else None
                except Exception:
                    parents_cache[current_id] = None
                    
            parent_id = parents_cache[current_id]
            if not parent_id:
                break
                
            current_id = parent_id
            depth += 1
            
            # 무한 루프 방지
            if depth > 20:
                break
                
        return depth

    def ensure_and_organize_lesson_folder(self, lesson_id: str) -> str:
        """
        lesson_id(예: 0814_34)와 관련된 파일들을 찾아, 
        가장 깊은 위치에 lesson_id 폴더를 생성하고 관련된 모든 파일을 해당 폴더로 이동시킵니다.
        """
        self._log(f"📁 [{lesson_id}] 관련 파일 수집 및 전용 폴더 구성 시작...")
        
        # 1. 관련된 모든 파일 찾기
        all_files = get_all_drive_files(self.root_folder_id, drive_service=self.drive_service)
        
        related_files = []
        existing_target_folder_id = None
        
        for f in all_files:
            fname = f.get('name', '')
            fid = f.get('id')
            mimetype = f.get('mimeType')
            
            if lesson_id in fname:
                if mimetype == 'application/vnd.google-apps.folder' and fname == lesson_id:
                    existing_target_folder_id = fid
                else:
                    # 파일 또는 다른 폴더
                    related_files.append(f)
                    
        if not related_files:
            if existing_target_folder_id:
                return existing_target_folder_id
            self._log(f"⚠️ [{lesson_id}] 관련된 파일을 찾을 수 없습니다.")
            return None

        # 2. 깊이 계산 및 최적 부모 찾기
        parents_cache = {}
        max_depth = -1
        deepest_parent_id = self.root_folder_id
        
        for f in related_files:
            file_parents = f.get('parents', [])
            if not file_parents:
                continue
            parent_id = file_parents[0]
            
            depth = self._get_file_depth(f['id'], parents_cache)
            if depth > max_depth:
                max_depth = depth
                deepest_parent_id = parent_id
            elif depth == max_depth and max_depth != -1:
                if deepest_parent_id != parent_id:
                    # 판단 불가 -> 가장 바깥(루트)에 생성
                    deepest_parent_id = self.root_folder_id

        # [검증 로직 추가] deepest_parent_id 폴더 자체가 이미 lesson_id를 포함하는지 확인 (중첩 생성 방지)
        if not existing_target_folder_id and deepest_parent_id != self.root_folder_id:
            try:
                parent_info = self.drive_service.files().get(fileId=deepest_parent_id, fields='name, mimeType').execute()
                if parent_info.get('mimeType') == 'application/vnd.google-apps.folder':
                    parent_name = parent_info.get('name', '')
                    # 부모 폴더 이름에 lesson_id가 포함되어 있다면 하위에 또 만들지 않음
                    if lesson_id.strip() in parent_name:
                        self._log(f"✅ 부모 폴더('{parent_name}')가 이미 '{lesson_id}'와 연관되어 있어 이를 타겟으로 사용합니다.")
                        existing_target_folder_id = deepest_parent_id
            except Exception as e:
                self._log(f"⚠️ 부모 폴더 검증 중 오류 발생: {e}")

        # 이미 목표 폴더가 대상 부모 안에 올바르게 생성되어 있는지 확인
        if existing_target_folder_id:
            target_folder_id = existing_target_folder_id
            self._log(f"✅ [{lesson_id}] 타겟 폴더가 결정되었습니다.")
        else:
            # 폴더 생성 로직
            self._log(f"📂 [{lesson_id}] 폴더가 없어 깊이가 가장 깊은 위치에 새로 생성합니다.")
            file_metadata = {
                'name': lesson_id.strip(),
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [deepest_parent_id]
            }
            folder = self.drive_service.files().create(
                body=file_metadata, fields='id'
            ).execute()
            target_folder_id = folder.get('id')

        # 3. 파일들 이동
        moved_count = 0
        for f in related_files:
            f_parents = f.get('parents', [])
            if not f_parents or f_parents[0] != target_folder_id:
                try:
                    move_drive_file(f['id'], target_folder_id, drive_service=self.drive_service)
                    moved_count += 1
                except Exception as e:
                    self._log(f"⚠️ 파일 이동 실패 ({f['name']}): {e}")
                    
        if moved_count > 0:
            self._log(f"🚚 총 {moved_count}개의 파일을 [{lesson_id}] 폴더로 이동시켰습니다.")
            
        return target_folder_id
