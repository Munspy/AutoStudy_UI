import pathlib
import threading
from typing import Any, Dict, Generator, Optional, Union
from pathlib import Path
from infrastructure.auth_client import GoogleAuthClient
from core.config import Config

import io
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Union
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from core.config import Config

PathLike = Union[str, Path]

class GoogleDriveClient:
    """구글 드라이브 API 통신을 전담하는 클라이언트."""
    def __init__(self, auth_client: GoogleAuthClient):
        self.auth_client = auth_client
        self._local = threading.local()

    def _get_service(self):
        """스레드별로 서비스 객체를 캐싱하여 같은 스레드 내에서는 TCP 연결을 재활용합니다."""
        if not hasattr(self._local, 'service'):
            self._local.service = self.auth_client.get_drive_service()
        return self._local.service


    def upload_to_drive(self, 
        local_file_path: PathLike, 
        target_folder_id: str, 
        mime_type: Optional[str] = None, 
        new_file_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """지정된 로컬 파일을 구글 드라이브의 특정 폴더로 업로드합니다.

        이 함수는 로컬 파일 시스템에 존재하는 파일을 읽어들여 구글 드라이브로 전송합니다.
        자동화된 학습 자료 처리 파이프라인(예: Whisper 음성 변환 결과, Gemini 분석 노트 등)에서 
        생성된 결과물을 백그라운드 Worker 스레드가 드라이브에 동기화할 때 주로 호출됩니다.
        
        `MediaFileUpload`를 사용하여 resumable(이어올리기) 업로드를 지원하므로, 대용량 파일 전송 중 
        네트워크가 불안정하더라도 비동기 작업이 완전히 실패하지 않도록 안정성을 보장합니다. 
        또한 `Config.extract_drive_id`를 통해 URL 형태의 폴더 ID 입력도 안전하게 파싱하여 
        사용자(UI)가 입력한 다양한 형태의 경로를 유연하게 수용합니다.

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
        # 업로드할 파일의 메타데이터 구성
        file_metadata = {
            'name': new_file_name if new_file_name else file_path.name,
            'parents': [target_folder_id] if target_folder_id else []
        }
        
        # 1차 시도: 이어올리기(resumable=True)
        try:
            media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
            uploaded_file = self._get_service().files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, name'
            ).execute()
            return uploaded_file
        except Exception as e:
            # 2차 시도: 리다이렉트/Location 헤더 오류 대비 직접 단순 업로드(resumable=False) 폴백
            try:
                media_direct = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=False)
                uploaded_file = self._get_service().files().create(
                    body=file_metadata, 
                    media_body=media_direct, 
                    fields='id, name'
                ).execute()
                return uploaded_file
            except Exception as retry_e:
                raise Exception(f"업로드 실패 ({file_path.name}): {str(retry_e)}")



    def download_from_drive(self, 
        file_id: str, 
        save_path: str, 
    ) -> str:
        """구글 드라이브 파일 하나를 지정된 로컬 경로로 다운로드합니다.

        대용량 PDF 문서나 강의 미디어 파일을 Service 계층에서 분석하기 위해 로컬로 가져올 때 
        호출되는 기능입니다. 메인 UI가 멈추는 프리징 현상을 막기 위해 Worker 스레드 내부에서 
        실행되는 경우가 많습니다. 
        
        이 함수는 파일의 바이너리 데이터를 `MediaIoBaseDownload`를 이용해 청크 단위(chunk-by-chunk)로 
        스트리밍하여 디스크에 기록합니다. 한 번에 모든 데이터를 메모리에 적재하지 않으므로, 
        대량의 배치 작업이나 무거운 비동기 파이프라인 실행 중에도 메모리 부족(OOM, Out Of Memory) 
        크래시를 방지할 수 있는 핵심적인 방어 로직입니다.

        Args:
            file_id (str): 다운로드할 구글 드라이브 파일의 고유 ID 또는 URL입니다.
            save_path (str): 파일이 저장될 로컬 시스템의 전체 경로(파일명 포함)입니다.
            drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체입니다.

        Returns:
            str: 다운로드가 완료된 파일의 로컬 저장 경로(save_path)를 반환합니다.
            
        Raises:
            Exception: 파일 아이디가 유효하지 않거나 API 호출 권한/할당량 오류가 있을 경우 예외가 발생할 수 있습니다.
        """
        file_id = Config.extract_drive_id(file_id)
        # 바이너리 다운로드 요청 객체 생성
        request = self._get_service().files().get_media(fileId=file_id)
        
        # 로컬 파일을 쓰기 모드로 오픈
        with io.FileIO(save_path, 'wb') as fh:
            # 청크 단위 다운로더 초기화
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            # 완료될 때까지 청크 스트리밍 다운로드 진행
            while not done:
                _, done = downloader.next_chunk()
                
        return save_path


    @contextmanager
    def temp_download_from_drive(self, 
        file_id: str, 
        extension: Optional[str] = None, 
    ) -> Generator[Path, None, None]:
        """대용량 또는 임시 처리를 위한 파일 다운로드 컨텍스트 매니저입니다.

        백그라운드 Worker나 Service가 특정 문서를 일회성으로 분석(예: OCR 수행, 텍스트 추출)하고 
        폐기하는 자동화 파이프라인에서 주로 사용됩니다. 특정 파일을 영구적으로 보관할 필요가 없을 때, 
        파이썬 내장 `tempfile.TemporaryDirectory`를 활용해 안전하게 격리된 공간에 파일을 내려받습니다.
        
        `yield` 블록(비즈니스 로직) 실행이 종료되면 시스템이 스스로 임시 디렉토리와 파일을 삭제(Clean-up)합니다. 
        이를 통해 지속적으로 동작하는 백그라운드 Watchdog 시스템이 임시 찌꺼기 파일들로 인해 
        디스크 스토리지를 고갈시키는 문제를 원천적으로 차단합니다.

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

        # 확장자가 지정되지 않은 경우 API를 통해 원본 파일명 조회
        if not extension:
            try:
                file_info = self._get_service().files().get(fileId=file_id, fields='name').execute()
                extension = Path(file_info.get('name', '')).suffix or ".pdf"
            except Exception:
                extension = ".pdf"

        # 임시 디렉토리 생성 (컨텍스트 종료 시 자동 삭제됨)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / f"downloaded_temp_file{extension}"
            # 임시 경로로 다운로드 수행
            self.download_from_drive(file_id, str(temp_path), drive_service=self.auth_client.get_drive_service())
            # 로직 실행을 위해 yield
            yield temp_path



    @contextmanager
    def in_memory_download_from_drive(self, 
        file_id: str, 
        mime_type: str | None = None, 
    ):
        """디스크 I/O 없이 메모리(RAM) 상에서 직접 데이터를 다운로드하는 컨텍스트 매니저입니다.

        물리적인 디스크 저장 공간을 거치지 않고 `io.BytesIO()`를 통해 바이너리 버퍼 공간을 
        만들어 데이터를 즉시 적재합니다. 수많은 문서를 빠르게 파싱하여 Gemini LLM으로 넘겨야 하는 
        Service 계층이나, 파일 I/O로 인한 병목을 허용할 수 없는 고속 스트리밍 환경에서 
        비동기 처리량과 자원 효율성을 극대화하기 위해 설계되었습니다.
        
        구글 문서(Docs, Sheets 등)의 경우 `mime_type`을 전달하여 Export API를 호출함으로써 
        다운로드 가능한 포맷으로 서버단에서 자동 변환 후 읽어올 수 있습니다.

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
        
        # 구글 문서 포맷은 변환 내보내기, 일반 파일은 단순 미디어 다운로드 요청
        if mime_type:
            request = self._get_service().files().export_media(fileId=file_id, mimeType=mime_type)
        else:
            request = self._get_service().files().get_media(fileId=file_id)
            
        # 메모리 버퍼 생성
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        try:
            done = False
            # 청크 스트리밍 다운로드
            while not done:
                _, done = downloader.next_chunk()
            # 버퍼 읽기 위치를 처음으로 초기화
            fh.seek(0)
            yield fh
        finally:
            # 사용이 끝난 메모리 버퍼 안전 해제
            fh.close()


    def get_drive_file_info(self, file_id: str) -> dict:
        """특정 파일의 메타데이터(id, name, parents 등)를 조회합니다."""
        service = self._get_service()
        res = service.files().get(fileId=file_id, fields="id, name, parents").execute()
        return res

    def get_all_drive_files(self, 
        root_folder_id: str, 
        name_filter: str | None = None, 
    ) -> list:
        """루트 폴더 하위의 모든 폴더 및 파일 목록을 재귀적으로 탐색하여 수집합니다.

        DriveSyncController나 연관 Worker가 주기적으로 구글 드라이브의 상태를 모니터링하고 
        새로운 학습 자료를 로컬과 동기화하는 자동화 과정에서 사용됩니다. 
        구글 드라이브 API는 한 번에 가져올 수 있는 개수 제한이 있고 URL 쿼리 길이에도 상한이 존재합니다. 
        
        따라서 이 함수는 BFS(너비 우선 탐색) 기반의 큐(queue) 알고리즘과 Pagination(pageToken) 로직, 
        그리고 한 번에 20개씩 폴더를 묶어 쿼리를 날리는(chunking) 최적화 기법을 적용했습니다. 
        이를 통해 대량의 깊은 디렉토리 구조라도 API 호출 횟수 제한(Rate Limit)을 우회하며 
        누락이나 오류 없이 전체 트리를 안정적으로 긁어올 수 있습니다.

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

        # 1단계: 하위 폴더 트리 탐색 (BFS) — 결과가 다음 쿼리의 입력이므로 순차 실행
        while queue:
            # 한 번에 20개씩 묶어서 API 할당량 초과 방지
            current_batch = queue[:20]
            queue = queue[20:]

            parents_query = " or ".join([f"'{fid}' in parents" for fid in current_batch])
            folder_q = f"({parents_query}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

            page_token = None
            while True:
                res = self._get_service().files().list(
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

        # SQL 인젝션 및 쿼리 파싱 에러 방지를 위한 필터링 값 정제
        safe_filter = name_filter.replace("'", "\\'") if name_filter else None

        # 청크 목록 사전 구성
        chunks = [all_folder_ids[i:i + 20] for i in range(0, len(all_folder_ids), 20)]

        def _fetch_chunk(chunk: list) -> list:
            """단일 청크에 대한 파일 목록을 조회합니다. ThreadPoolExecutor의 각 스레드에서 실행됩니다.
            threading.local() 덕분에 스레드마다 독립된 HTTP 연결을 사용하므로 스레드 안전합니다.
            """
            parents_query = " or ".join([f"'{fid}' in parents" for fid in chunk])
            file_q = f"({parents_query}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            if safe_filter:
                file_q += f" and name contains '{safe_filter}'"

            result = []
            page_token = None
            while True:
                res = self._get_service().files().list(
                    q=file_q,
                    pageSize=1000,
                    fields="nextPageToken, files(id, name, parents)",
                    pageToken=page_token
                ).execute()
                result.extend(res.get('files', []))
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            return result

        # 2단계: 각 청크를 병렬로 동시 조회 — 순차 대비 최대 청크수 배 빠름
        from concurrent.futures import ThreadPoolExecutor, as_completed
        all_files = []
        max_workers = min(8, len(chunks))  # 과도한 병렬화 방지
        if max_workers > 0:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_fetch_chunk, chunk): chunk for chunk in chunks}
                for future in as_completed(futures):
                    all_files.extend(future.result())

        return all_files



    def create_folder(self, name: str, parent_id: str) -> str:
        """구글 드라이브에 폴더를 생성하고 생성된 폴더의 ID를 반환합니다."""
        service = self._get_service()
        file_metadata = {
            'name': name.strip(),
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id', '')

    def find_drive_file_id(self, 
        folder_id: str, 
        file_name: str, 
    ) -> str | None:
        """특정 폴더 내에서 정확히 일치하는 이름을 가진 단일 파일의 고유 ID를 조회합니다.

        자동화 파이프라인이 여러 번 재시도되거나 Watchdog에 의해 중복 실행되더라도, 
        이미 처리된 파일(동일한 이름의 파일)을 식별하여 무의미한 덮어쓰기를 피하거나 
        업데이트 분기를 태우는 멱등성(Idempotency)을 보장하기 위한 사전 검증 로직으로 활용됩니다.
        
        휴지통(trashed=false)에 있지 않은 대상만 검색하며, 쿼리 구문 오류나 크래시를 막기 위해
        파일 이름 내에 포함될 수 있는 특수문자(')에 대한 이스케이프 처리를 선행합니다.

        Args:
            folder_id (str): 파일을 검색할 대상 부모 폴더의 고유 ID 또는 URL입니다.
            file_name (str): 검색하려는 파일의 정확한 이름입니다.
            drive_service (Any): 구글 API 클라이언트 인증이 완료된 드라이브 서비스 리소스 객체 객체입니다.

        Returns:
            str | None: 조건에 일치하는 파일이 존재할 경우 최상위(인덱스 0) 파일의 고유 ID 문자열을 반환하고, 존재하지 않거나 검색 중 에러가 발생하면 None을 반환합니다.
        """
        folder_id = Config.extract_drive_id(folder_id)
        
        # 이스케이프 처리하여 쿼리 안전성 확보
        safe_file_name = file_name.replace("'", "\\'")
        query = f"'{folder_id}' in parents and name = '{safe_file_name}' and trashed = false"
        
        try:
            # 단일 매칭 파일 검색 수행
            results = self._get_service().files().list(
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



    def copy_drive_file(self, 
        file_id: str, 
        target_folder_id: str, 
        new_name: str | None = None, 
    ) -> dict:
        """드라이브 내 파일을 로컬로 다운로드하지 않고 서버 사이드에서 직접 복사합니다.

        학습 자료가 파이프라인의 특정 단계(예: 원본 폴더 -> 분석 완료 폴더)를 거칠 때, 
        Service나 Worker가 로컬 머신으로 데이터를 다운로드했다가 다시 업로드하는 비효율적인 왕복 과정 없이 
        구글 서버 내부에서 즉각적으로 복제본을 생성하도록 요청합니다. 
        
        이는 네트워크 트래픽 대역폭과 시스템 메모리 낭비를 방지하고 비동기 작업의 소요 시간을 
        획기적으로 단축시키는 효율적인 방식입니다. 복제본이 생성될 대상 폴더와 새로운 파일명을 함께 설정할 수 있습니다.

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

        # 복사본이 위치할 폴더 지정
        body = {'parents': [target_folder_id]}
        # 새 파일명이 제공되었으면 적용
        if new_name:
            body['name'] = new_name

        try:
            # 서버 사이드 파일 복제 요청
            copied_file = self._get_service().files().copy(
                fileId=file_id, 
                body=body, 
                fields='id, name, parents'
            ).execute()
            return copied_file
        except Exception as e:
            raise Exception(f"드라이브 파일 복사 실패 (File ID: {file_id}): {str(e)}")



    def delete_drive_file(self, file_id: str,) -> bool:
        """구글 드라이브 파일을 휴지통으로 이동(소프트 삭제)합니다.

        영구 삭제 대신 휴지통으로 이동하여 실수로 인한 데이터 손실을 방지합니다.
        Google Drive 콘솔의 휴지통에서 30일 이내에 복구 가능합니다.

        Args:
            file_id (str): 삭제할 파일의 드라이브 고유 ID 또는 URL.
            drive_service (Any): 인증된 드라이브 서비스 객체.

        Returns:
            bool: 삭제 성공 시 True, 실패 시 False.
        """
        file_id = Config.extract_drive_id(file_id)
        try:
            self._get_service().files().update(
                fileId=file_id,
                body={'trashed': True}
            ).execute()
            return True
        except Exception as e:
            print(f"⚠️ 드라이브 파일 삭제 실패 (File ID: {file_id}): {e}")
            return False



    def move_drive_file(self, 
        file_id: str, 
        target_folder_id: str, 
    ) -> dict:
        """구글 드라이브 파일의 위치(부모 폴더)를 서버 사이드에서 다른 폴더로 이동시킵니다.

        자동화 파이프라인에서 파일의 비즈니스 처리가 끝난 뒤 상태 관리를 수행할 때(예: '처리 대기' 폴더에서 
        '처리 완료' 폴더로 이동), 실제 파일을 다운로드 및 재업로드하는 것이 아니라 메타데이터만 수정합니다.
        
        구글 드라이브의 파일 모델은 단일 파일이 여러 부모를 가질 수 있는 구조(`parents` 배열)를 취하므로, 
        이 함수는 파일 속성에서 기존 부모 폴더 목록(removeParents)을 떼어내고 새로운 대상 폴더(addParents)를 
        붙이는 논리적인 갱신 방식으로 동작합니다. 이를 통해 오버헤드 없이 빠르고 가벼운 파이프라인 단계 전환을 지원합니다.

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
            # 파일의 현재 부모(Parents) 상태 조회
            file_info = self._get_service().files().get(
                fileId=file_id, 
                fields='parents'
            ).execute()
            previous_parents = ",".join(file_info.get('parents', []))

            # 메타데이터 업데이트: 이전 부모 삭제 및 새로운 부모 추가
            moved_file = self._get_service().files().update(
                fileId=file_id,
                addParents=target_folder_id,
                removeParents=previous_parents,
                fields='id, name, parents'
            ).execute()
            
            return moved_file
        except Exception as e:
            raise Exception(f"드라이브 파일 이동 실패 (File ID: {file_id}): {str(e)}")

    # =========================================================================
    # [Changes API 기반 증분 캐시]
    # =========================================================================

    def get_all_drive_files_cached(self, root_folder_id: str, name_filter: str | None = None) -> list:
        """Changes API를 활용한 증분 업데이트 버전의 파일 목록 조회.

        - 첫 실행: 전체 BFS 스캔 후 결과와 pageToken을 디스크에 저장.
        - 이후 실행: 저장된 pageToken으로 변경분만 받아 캐시에 적용 (대폭 빠름).
        - 앱 재시작 후에도 캐시를 그대로 재사용.
        - 토큰 만료 또는 오류 시 전체 재스캔으로 자동 fallback.
        """
        import json
        from core.config import BASE_DIR

        clean_root_id = Config.extract_drive_id(root_folder_id)
        cache_filename = "drive_cache.json" if clean_root_id == Config.TARGET_DRIVE_DIR else f"drive_cache_{clean_root_id}.json"
        cache_path = BASE_DIR / cache_filename

        # 1. 캐시 로드 시도
        cache = None
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if cache.get('root_folder_id') != clean_root_id:
                    cache = None  # 루트 폴더가 바뀌었으면 무효화
            except Exception:
                cache = None

        # 2. 캐시가 있으면 Changes API로 증분 업데이트
        if cache and cache.get('page_token'):
            try:
                cache = self._apply_drive_changes(cache)
                self._save_drive_cache(cache_path, cache)
                files = cache['files']
                if name_filter:
                    files = [f for f in files if name_filter in f.get('name', '')]
                return files
            except Exception:
                pass  # 토큰 만료 등 오류 → 전체 재스캔으로 fallback

        # 3. 전체 BFS 스캔 (첫 실행 또는 fallback)
        # 스캔 시작 전에 변경점 토큰을 미리 획득하여 스캔 도중의 변경사항도 다음 증분 때 유실되지 않도록 보장
        try:
            start_token = self._get_service().changes().getStartPageToken(
                supportsAllDrives=True
            ).execute().get('startPageToken')
        except Exception:
            start_token = None

        all_files = self.get_all_drive_files(clean_root_id, name_filter=None)

        # 폴더 ID 목록은 BFS 내부에서도 구축하지만, 캐시용으로 별도 수집
        all_folder_ids = self._collect_all_folder_ids(clean_root_id)

        new_cache = {
            'root_folder_id': clean_root_id,
            'page_token': start_token,
            'folder_ids': all_folder_ids,
            'files': all_files,
        }
        self._save_drive_cache(cache_path, new_cache)

        if name_filter:
            all_files = [f for f in all_files if name_filter in f.get('name', '')]
        return all_files

    def _collect_all_folder_ids(self, root_folder_id: str) -> list:
        """BFS로 루트 하위 모든 폴더 ID를 수집합니다 (캐시 구축용)."""
        all_folder_ids = [root_folder_id]
        queue = [root_folder_id]
        while queue:
            batch = queue[:20]
            queue = queue[20:]
            pq = " or ".join([f"'{fid}' in parents" for fid in batch])
            fq = f"({pq}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            page_token = None
            while True:
                res = self._get_service().files().list(
                    q=fq, pageSize=1000, fields="nextPageToken, files(id)", pageToken=page_token
                ).execute()
                for sf in res.get('files', []):
                    all_folder_ids.append(sf['id'])
                    queue.append(sf['id'])
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
        return all_folder_ids

    def _apply_drive_changes(self, cache: dict) -> dict:
        """저장된 pageToken 이후 Drive 변경사항을 캐시에 반영합니다."""
        service = self._get_service()
        page_token = cache['page_token']
        folder_ids_set = set(cache.get('folder_ids', []))
        files_dict = {f['id']: f for f in cache.get('files', [])}
        new_folder_ids = []

        while page_token:
            res = service.changes().list(
                pageToken=page_token,
                spaces='drive',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields='nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, parents, mimeType, trashed))',
                pageSize=1000
            ).execute()

            for change in res.get('changes', []):
                file_id = change.get('fileId')
                file_info = change.get('file') or {}
                removed = change.get('removed', False) or file_info.get('trashed', False)

                if removed:
                    files_dict.pop(file_id, None)
                    folder_ids_set.discard(file_id)
                    continue

                parents = file_info.get('parents', [])
                mime = file_info.get('mimeType', '')
                in_our_tree = any(p in folder_ids_set for p in parents)

                if not in_our_tree:
                    continue  # 우리 루트 하위가 아닌 변경은 무시

                if mime == 'application/vnd.google-apps.folder':
                    if file_id not in folder_ids_set:
                        folder_ids_set.add(file_id)
                        new_folder_ids.append(file_id)
                else:
                    files_dict[file_id] = {
                        'id': file_id,
                        'name': file_info.get('name', ''),
                        'parents': parents,
                    }

            # nextPageToken이 있으면 계속, newStartPageToken이 있으면 끝
            next_token = res.get('nextPageToken')
            new_start = res.get('newStartPageToken')
            if new_start:
                cache['page_token'] = new_start
                break
            page_token = next_token

        # 새로 추가된 폴더가 있으면 그 하위 파일도 수집
        if new_folder_ids:
            # 새 폴더의 하위 폴더까지 BFS
            q = list(new_folder_ids)
            while q:
                batch = q[:20]
                q = q[20:]
                pq = " or ".join([f"'{fid}' in parents" for fid in batch])
                fq = f"({pq}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                res = service.files().list(q=fq, pageSize=1000, fields="files(id)").execute()
                for sf in res.get('files', []):
                    if sf['id'] not in folder_ids_set:
                        folder_ids_set.add(sf['id'])
                        new_folder_ids.append(sf['id'])
                        q.append(sf['id'])

            # 새 폴더들의 파일 수집 (병렬)
            from concurrent.futures import ThreadPoolExecutor
            chunks = [new_folder_ids[i:i+20] for i in range(0, len(new_folder_ids), 20)]

            def _fetch_new_folder_files(chunk):
                pq = " or ".join([f"'{fid}' in parents" for fid in chunk])
                fq = f"({pq}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
                res = self._get_service().files().list(
                    q=fq, pageSize=1000, fields="files(id, name, parents)"
                ).execute()
                return res.get('files', [])

            with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as executor:
                futures = [executor.submit(_fetch_new_folder_files, c) for c in chunks]
                for future in futures:
                    for f in future.result():
                        files_dict[f['id']] = f

        cache['folder_ids'] = list(folder_ids_set)
        cache['files'] = list(files_dict.values())
        return cache

    def _save_drive_cache(self, path, cache: dict) -> None:
        """캐시를 디스크에 저장합니다."""
        import json
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass

    def invalidate_drive_cache(self, root_folder_id: Optional[str] = None) -> None:
        """캐시를 강제로 무효화합니다. 파일 업로드/삭제 후 또는 강제 새로고침 시 호출하세요."""
        from core.config import BASE_DIR
        try:
            if root_folder_id:
                clean_root_id = Config.extract_drive_id(root_folder_id)
                cache_filename = "drive_cache.json" if clean_root_id == Config.TARGET_DRIVE_DIR else f"drive_cache_{clean_root_id}.json"
                cache_path = BASE_DIR / cache_filename
                if cache_path.exists():
                    cache_path.unlink()
            else:
                for p in BASE_DIR.glob('drive_cache*.json'):
                    p.unlink(missing_ok=True)
        except Exception:
            pass


