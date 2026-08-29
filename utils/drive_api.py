"""구글 드라이브 API 연동 및 파일 제어 유틸리티 모듈.

이 모듈은 구글 드라이브(Google Drive)와의 상호작용을 캡슐화하여, 
로컬 시스템과 드라이브 간의 파일 업로드, 다운로드, 검색, 복사 및 이동과 같은 
파일 시스템 수준의 오퍼레이션을 제공합니다. 전체 파이프라인에서 데이터의 
저장 및 조회를 담당하는 핵심 I/O 인터페이스 역할을 수행하며, 대용량 파일이나 
임시 파일 처리를 위한 컨텍스트 매니저 기반의 메모리/임시 파일 제어 기능도 포함하여 
시스템 자원을 효율적으로 관리할 수 있도록 설계되었습니다.
"""

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
    """지정된 로컬 파일을 구글 드라이브의 특정 폴더로 업로드합니다.

    이 함수는 로컬 파일 시스템에 존재하는 파일을 읽어들여 구글 드라이브로 전송합니다.
    `MediaFileUpload`를 사용하여 resumable(이어올리기) 업로드를 지원하므로,
    대용량 파일 전송 시 네트워크 끊김 등에 비교적 안정적으로 동작합니다. 
    `Config.extract_drive_id`를 통해 URL 형태의 폴더 ID 입력도 안전하게 파싱하여 
    대상 폴더를 지정할 수 있도록 구성되었습니다.

    Args:
        local_file_path (PathLike): 업로드할 로컬 파일의 절대 또는 상대 경로입니다.
        target_folder_id (str): 업로드될 구글 드라이브 대상 폴더의 고유 ID 또는 URL입니다.
        mime_type (Optional[str], optional): 파일의 MIME 타입입니다. 지정하지 않을 경우 확장자를 통해 자동 추론됩니다. Defaults to None.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        Dict[str, Any]: 업로드 성공 시 반환되는 파일의 메타데이터(예: {'id': '...', 'name': '...'})를 담은 딕셔너리입니다.

    Raises:
        Exception: 파일 읽기 실패, 네트워크 오류, 인증 실패 등 구글 API 통신 중 예외가 발생할 경우 업로드 실패 메시지와 함께 발생합니다.
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
    """구글 드라이브 파일 하나를 지정된 로컬 경로로 다운로드합니다.

    이 함수는 구글 드라이브에 저장된 파일의 바이너리 데이터를 `MediaIoBaseDownload`를 
    이용해 청크 단위(chunk-by-chunk)로 스트리밍하여 로컬 파일 시스템에 기록합니다.
    한 번에 모든 데이터를 메모리에 올리지 않고 분할해서 다운로드하므로, 메모리 부족(OOM) 
    현상을 방지하고 대용량 파일을 안전하게 처리할 수 있는 핵심 로직입니다.

    Args:
        file_id (str): 다운로드할 구글 드라이브 파일의 고유 ID 또는 URL입니다.
        save_path (str): 파일이 저장될 로컬 시스템의 전체 경로(파일명 포함)입니다.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        str: 다운로드가 완료된 파일의 로컬 저장 경로(save_path)를 그대로 반환합니다.
        
    Raises:
        Exception: 파일 아이디가 유효하지 않거나 API 호출 권한/할당량 오류가 있을 경우 예외가 발생할 수 있습니다.
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
    """대용량 또는 임시 처리를 위한 파일 다운로드 컨텍스트 매니저입니다.

    이 제너레이터는 특정 파일을 영구적으로 저장할 필요 없이 데이터를 임시로 파싱하거나 
    단기적으로 분석해야 할 때 유용합니다. 파이썬 내장 `tempfile.TemporaryDirectory`를 
    활용하여 안전한 임시 디렉토리를 생성하고 파일 다운로드를 수행하며, `yield` 블록 
    실행이 종료되면 시스템이 자동으로 임시 디렉토리와 파일을 정리(삭제)합니다. 
    이를 통해 디스크 스토리지 낭비를 막고 찌꺼기 파일이 남지 않도록 관리 부담을 덜어줍니다.

    Args:
        file_id (str): 다운로드할 구글 드라이브 파일의 고유 ID 또는 URL입니다.
        extension (Optional[str], optional): 임시 파일에 부여할 확장자입니다. 지정하지 않을 경우 드라이브 API를 통해 원본 파일명을 조회하여 추출하며, 조회 실패 시 기본값(".pdf")을 적용합니다. Defaults to None.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Yields:
        Generator[Path, None, None]: 다운로드된 임시 파일의 로컬 `Path` 객체를 반환합니다.

    Raises:
        Exception: 구글 드라이브 API 통신 오류나 파일 다운로드 실패 시 발생할 수 있습니다.
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
    """디스크 I/O 없이 메모리(RAM) 상에서 직접 데이터를 다운로드하는 컨텍스트 매니저입니다.

    물리적인 디스크 저장 공간을 거치지 않고 `io.BytesIO()`를 통해 바이너리 버퍼 공간을 
    만들어 데이터를 적재합니다. 잦은 I/O를 발생시키지 않아야 하거나 응답 속도가 중요한 
    환경(예: 클라우드 서버리스 환경, 스트림 파이프라인)에서 자원 효율성을 극대화하기 위해 
    설계되었습니다. 구글 문서(Docs, Sheets 등)의 경우 `mime_type`을 전달하여 Export API를 
    호출함으로써 다운로드 가능한 포맷으로 자동 변환해 읽어올 수 있습니다.

    Args:
        file_id (str): 드라이브에서 읽어올 대상 파일의 고유 ID 또는 URL입니다.
        mime_type (str, optional): 구글 워크스페이스 문서(Google Docs 등)를 내보낼 때 지정할 변환 목적 MIME 타입(예: 'application/pdf'). 일반 파일의 경우 생략합니다. Defaults to None.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Yields:
        Generator[io.BytesIO, None, None]: 다운로드된 파일 데이터가 담긴 바이트 스트림 객체를 반환합니다. 이 객체의 읽기 위치(pointer)는 0으로 초기화되어 즉시 사용할 수 있습니다.

    Raises:
        Exception: 파일 스트리밍 실패 시, 혹은 내보낼 수 없는 파일에 대해 잘못된 `mime_type`을 요청할 경우 예외가 발생할 수 있습니다.
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
    """루트 폴더 하위의 모든 폴더 및 파일 목록을 재귀적으로 탐색하여 수집합니다.

    이 함수는 지정된 최상위 폴더(root) 아래 존재하는 복잡한 폴더 트리 구조를 모두 순회합니다. 
    구글 드라이브 API는 한 번에 가져올 수 있는 개수 제한이 있고 URL 쿼리 길이에도 제한이 있으므로, 
    BFS(너비 우선 탐색) 기반의 큐(queue) 알고리즘과 Pagination(pageToken) 로직, 그리고 
    한 번에 20개씩 폴더를 묶어 검색하는(chunk/batch) 최적화 로직을 적용하여 대량의 구조를 
    누락과 오류 없이 빠르고 안전하게 가져옵니다.

    Args:
        root_folder_id (str): 탐색을 시작할 최상위 구글 드라이브 폴더의 고유 ID 또는 URL입니다.
        name_filter (str, optional): 결과 중 파일명이 특정 문자열을 포함(contains)하는 파일만 반환하고 싶을 때 사용하는 검색 필터입니다. SQL 인젝션 및 구문 오류 방지를 위해 내부적으로 이스케이프 처리됩니다. Defaults to None.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        list: 수집된 개별 파일의 메타데이터(딕셔너리 형태: 'id', 'name', 'parents' 등)를 포함하는 전체 리스트입니다.

    Raises:
        Exception: 구글 드라이브 폴더 접근 권한이 없거나, 할당량 초과 등으로 인한 API 호출 실패 시 발생할 수 있습니다.
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
    """특정 폴더 내에서 정확히 일치하는 이름을 가진 단일 파일의 고유 ID를 조회합니다.

    특정 디렉토리에 동일한 이름의 파일이 이미 존재하는지 확인하여 중복 생성을 방지하고, 
    기존 파일에 덮어쓰기(업데이트)를 수행할지 분기하기 위한 검증 로직으로 활용됩니다.
    휴지통(trashed=false)에 있지 않은 대상만 검색하며, 쿼리 구문 오류를 막기 위해
    파일 내 특수문자(') 이스케이프 처리를 수행합니다.

    Args:
        folder_id (str): 파일을 검색할 대상 부모 폴더의 고유 ID 또는 URL입니다.
        file_name (str): 검색하려는 파일의 정확한 이름입니다.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        str | None: 조건에 일치하는 파일이 존재할 경우 최상위(인덱스 0) 파일의 고유 ID 문자열을 반환하고, 존재하지 않거나 검색 중 에러가 발생하면 None을 반환합니다.
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
    """드라이브 내 파일을 로컬로 다운로드하지 않고 서버 사이드에서 직접 복사합니다.

    이 함수는 클라이언트(로컬 서버)가 직접 파일을 다운로드 후 업로드하는 과정 없이, 
    구글 드라이브 API 서버 내에서 곧바로 복제되도록 요청합니다. 이는 네트워크 트래픽 및 
    메모리 낭비를 방지하고 복사 소요 시간을 획기적으로 줄여주는 효율적인 방식입니다. 
    복제본이 생성될 대상 폴더와 원할 경우 새로운 파일명을 함께 설정할 수 있습니다.

    Args:
        file_id (str): 복사할 원본 파일의 구글 드라이브 고유 ID 또는 URL입니다.
        target_folder_id (str): 복사본이 저장될 대상 폴더의 고유 ID 또는 URL입니다.
        new_name (str, optional): 복사본에 새롭게 부여할 파일명입니다. 제공하지 않을 경우 원본의 파일명이 그대로 사용됩니다. Defaults to None.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        dict: 정상적으로 복사 생성된 새 파일의 메타데이터('id', 'name', 'parents') 정보를 담은 딕셔너리입니다.

    Raises:
        Exception: 원본 파일을 찾을 수 없거나 대상 폴더에 쓰기 권한이 부족하여 복사에 실패할 경우 예외가 발생합니다.
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
    """구글 드라이브 파일의 위치(부모 폴더)를 서버 사이드에서 다른 폴더로 이동시킵니다.

    구글 드라이브의 파일 모델은 전통적인 트리 구조와 달리 단일 파일이 여러 부모를 
    가질 수 있는 구조(`parents` 배열)로 관리됩니다. 따라서 이 함수는 파일 자체를 
    이동시키는 것이 아니라, 파일 속성에서 기존 부모 폴더 목록(removeParents)을 
    제거하고 새로운 대상 폴더(addParents)를 등록하는 논리적인 메타데이터 업데이트 
    방식으로 동작합니다. 이를 통해 다운로드/업로드 오버헤드 없는 즉각적인 이동 처리가 가능합니다.

    Args:
        file_id (str): 위치를 이동할 대상 파일의 구글 드라이브 ID 또는 URL입니다.
        target_folder_id (str): 파일이 새롭게 위치할 대상 폴더의 고유 ID 또는 URL입니다.
        drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

    Returns:
        dict: 부모 폴더 변경이 성공적으로 반영된 파일의 최신 메타데이터('id', 'name', 'parents') 딕셔너리입니다.

    Raises:
        Exception: 원본 파일 조회에 실패하거나 이동시키려는 대상 폴더 권한 부족, 또는 API 호출 중 에러 발생 시 실패 메시지와 함께 예외가 발생합니다.
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