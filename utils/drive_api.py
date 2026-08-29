# utils/drive_api.py
import io
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any, Generator, Union

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from utils.config import Config

PathLike = Union[str, Path]

def upload_to_drive(
    local_file_path: PathLike, 
    target_folder_id: str, 
    mime_type: Optional[str] = None, 
    *,
    drive_service: Any
) -> Dict[str, Any]:
    """
    지정된 로컬 파일을 구글 드라이브 폴더로 업로드합니다.
    """
    target_folder_id = Config.extract_drive_id(target_folder_id)
    
    file_path = Path(local_file_path)
    file_metadata = {
        'name': file_path.name,
        'parents': [target_folder_id] if target_folder_id else []
    }
    
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    try:
        uploaded_file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, name'
        ).execute()
        return uploaded_file
    except Exception as e:
        raise Exception(f"업로드 실패 ({file_path.name}): {str(e)}")

def download_from_drive(
    file_id: str, 
    save_path: str, 
    *,
    drive_service: Any
) -> str:
    """
    구글 드라이브 파일 하나를 지정된 로컬 경로로 다운로드합니다.
    """
    file_id = Config.extract_drive_id(file_id)
    request = drive_service.files().get_media(fileId=file_id)
    
    with io.FileIO(save_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            
    return save_path

@contextmanager
def temp_download_from_drive(
    file_id: str, 
    extension: Optional[str] = None, 
    *,
    drive_service: Any
) -> Generator[Path, None, None]:
    """
    대용량/임시 처리용 파일 다운로드 컨텍스트 매니저.
    """
    file_id = Config.extract_drive_id(file_id)

    if not extension:
        try:
            file_info = drive_service.files().get(fileId=file_id, fields='name').execute()
            extension = Path(file_info.get('name', '')).suffix or ".pdf"
        except Exception:
            extension = ".pdf"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / f"downloaded_temp_file{extension}"
        download_from_drive(file_id, str(temp_path), drive_service=drive_service)
        yield temp_path

@contextmanager
def in_memory_download_from_drive(
    file_id: str, 
    mime_type: str = None, 
    *,
    drive_service: Any
):
    """
    디스크 I/O 없이 메모리(RAM, BytesIO) 상에서 직접 다운로드하는 컨텍스트 매니저.
    """
    file_id = Config.extract_drive_id(file_id)
    if mime_type:
        request = drive_service.files().export_media(fileId=file_id, mimeType=mime_type)
    else:
        request = drive_service.files().get_media(fileId=file_id)
        
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    try:
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        yield fh
    finally:
        fh.close()

def get_all_drive_files(
    root_folder_id: str, 
    name_filter: str = None, 
    *,
    drive_service: Any
) -> list:
    """
    루트 폴더 내부의 모든 하위 폴더와 파일 목록을 재귀적으로 수집합니다.
    """
    root_folder_id = Config.extract_drive_id(root_folder_id)
    all_folder_ids = [root_folder_id]
    queue = [root_folder_id]

    while queue:
        current_batch = queue[:20]
        queue = queue[20:]
        parents_query = " or ".join([f"'{fid}' in parents" for fid in current_batch])
        folder_q = f"({parents_query}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

        page_token = None
        while True:
            res = drive_service.files().list(
                q=folder_q, 
                pageSize=1000, 
                fields="nextPageToken, files(id, name)", 
                pageToken=page_token
            ).execute()
            
            for sf in res.get('files', []):
                all_folder_ids.append(sf['id'])
                queue.append(sf['id'])
                
            page_token = res.get('nextPageToken')
            if not page_token:
                break

    all_files = []
    safe_filter = name_filter.replace("'", "\\'") if name_filter else None

    for i in range(0, len(all_folder_ids), 20):
        chunk = all_folder_ids[i:i + 20]
        parents_query = " or ".join([f"'{fid}' in parents" for fid in chunk])
        file_q = f"({parents_query}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        
        if safe_filter:
            file_q += f" and name contains '{safe_filter}'"

        page_token = None
        while True:
            res = drive_service.files().list(
                q=file_q, 
                pageSize=1000, 
                fields="nextPageToken, files(id, name, parents)", 
                pageToken=page_token
            ).execute()
            
            all_files.extend(res.get('files', []))
            page_token = res.get('nextPageToken')
            if not page_token:
                break
                
    return all_files

def find_drive_file_id(
    folder_id: str, 
    file_name: str, 
    *,
    drive_service: Any
) -> str | None:
    """
    특정 폴더 내에서 일치하는 이름을 가진 단일 파일의 ID를 조회합니다.
    """
    folder_id = Config.extract_drive_id(folder_id)
    
    safe_file_name = file_name.replace("'", "\\'")
    query = f"'{folder_id}' in parents and name = '{safe_file_name}' and trashed = false"
    
    try:
        results = drive_service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        if items:
            return items[0]['id']
        return None
    except Exception as e:
        print(f"⚠️ 파일 검색 오류 ({file_name}): {e}")
        return None

def copy_drive_file(
    file_id: str, 
    target_folder_id: str, 
    new_name: str = None, 
    *,
    drive_service: Any
) -> dict:
    """
    드라이브 내의 파일을 로컬 다운로드 없이 다른 드라이브 폴더로 서버 사이드 복사합니다.
    """
    file_id = Config.extract_drive_id(file_id)
    target_folder_id = Config.extract_drive_id(target_folder_id)

    body = {'parents': [target_folder_id]}
    if new_name:
        body['name'] = new_name

    try:
        copied_file = drive_service.files().copy(
            fileId=file_id, 
            body=body, 
            fields='id, name, parents'
        ).execute()
        return copied_file
    except Exception as e:
        raise Exception(f"드라이브 파일 복사 실패 (File ID: {file_id}): {str(e)}")

def move_drive_file(
    file_id: str, 
    target_folder_id: str, 
    *,
    drive_service: Any
) -> dict:
    """
    드라이브 내의 파일 위치(부모 폴더)를 서버 사이드에서 변경(이동)합니다.
    """
    file_id = Config.extract_drive_id(file_id)
    target_folder_id = Config.extract_drive_id(target_folder_id)

    try:
        file_info = drive_service.files().get(
            fileId=file_id, 
            fields='parents'
        ).execute()
        previous_parents = ",".join(file_info.get('parents', []))

        moved_file = drive_service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            fields='id, name, parents'
        ).execute()
        
        return moved_file
    except Exception as e:
        raise Exception(f"드라이브 파일 이동 실패 (File ID: {file_id}): {str(e)}")
