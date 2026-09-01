"""파일 시스템 유틸리티 모듈 (utils/file_util.py)

이 모듈은 `AutoStudy_UI` 프로젝트의 **Utils(유틸리티) 계층**에 속하며, 로컬 파일 시스템 제어를 
위한 핵심 유틸리티 함수들을 제공합니다. 

전체 파이프라인(PDF 파싱 -> Whisper 음성 변환 -> Gemini 분석 -> Notion/Anki 동기화)에서 
`Service` 및 `Worker` 계층이 파일 시스템과 상호작용할 때 발생하는 복잡성(예: 디렉토리 누락, 
동시성 충돌, 권한 문제)을 추상화하여 방어합니다. 

특히 Watchdog 기반의 자동화 모니터링이나 백그라운드 비동기 처리 중 디스크 I/O 오류가 
발생하더라도 전체 애플리케이션(UI 스레드)이 크래시되지 않고 유연하게 복구되거나 
에러를 로깅할 수 있도록 견고한 예외 처리 및 원자적 쓰기(Atomic Write)를 지원합니다.
"""

import shutil
from pathlib import Path
from typing import Union, List, Tuple

# 경로 입력 시 str과 pathlib.Path 모두 지원하도록 정의
PathLike = Union[str, Path]


def ensure_parent_dir(file_path: PathLike) -> Path:
    """대상 파일 경로의 상위(부모) 디렉토리가 존재하는지 확인하고, 없다면 자동으로 생성합니다.
    
    비동기 Worker가 백그라운드에서 백업 파일, 임시 오디오 추출본, 혹은 Gemini 분석 결과(JSON)를 
    저장할 때, 대상 디렉토리 트리가 존재하지 않으면 `FileNotFoundError`로 인해 파이프라인이 즉각 
    중단될 수 있습니다. 이를 방지하기 위해 파일 쓰기(Write) 작업 이전에 선행 호출되는 
    필수 방어 로직입니다. 단순히 최종 디렉토리만 생성하는 것이 아니라 `parents=True` 옵션을 통해 
    중간 단계의 모든 누락된 디렉토리를 재귀적으로 생성하여 안전한 I/O 환경을 보장합니다.

    Args:
        file_path (PathLike): 생성하려는 파일 또는 디렉토리의 전체 경로입니다. (문자열 또는 Path 객체)

    Returns:
        Path: 내부적으로 부모 디렉토리 생성 및 확인 작업을 마친 파일의 전체 경로를 `Path` 객체로 반환합니다.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def list_local_files(
    directory_path: PathLike, 
    extension: Union[str, Tuple[str, ...]] = None, 
    full_path: bool = False
) -> List[str]:
    """지정된 디렉토리 내에 존재하는 파일들의 목록을 탐색 및 필터링하여 반환합니다.
    
    데이터 파이프라인(예: Watchdog Worker)이 특정 폴더를 주기적으로 폴링(Polling)하여 
    처리되지 않은 PDF 파일이나 변환 완료된 JSON 결과물만 일괄적으로 수집해야 할 때 사용됩니다. 
    내부적으로 입력받은 확장자를 소문자 튜플로 정제하여, 대소문자(e.g., .PDF vs .pdf)로 인한 
    매칭 누락을 방지합니다. 
    
    자동화 루프 특성상 디렉토리가 외부 요인에 의해 삭제되거나 권한이 변경될 수 있으므로, 
    OS 레벨 예외 발생 시 시스템 크래시 대신 빈 리스트를 반환함으로써 백그라운드 파이프라인의 
    연속성을 훼손하지 않고 견고함을 유지합니다.

    Args:
        directory_path (PathLike): 탐색할 대상 디렉토리의 로컬 경로입니다.
        extension (Union[str, Tuple[str, ...]], optional): 필터링할 파일 확장자. 
            단일 문자열(예: '.txt') 또는 문자열 튜플(예: ('.jpg', '.png')) 형태로 입력 가능합니다.
        full_path (bool, optional): 반환되는 파일 목록의 형태를 결정하는 플래그. 
            **True**일 경우 절대 경로를, **False**일 경우 파일명만 반환합니다.

    Returns:
        List[str]: 탐색 및 필터링 조건에 부합하는 파일 경로 또는 파일명들의 리스트.
            오류가 발생하거나 조건에 맞는 파일이 없다면 빈 리스트(`[]`)를 반환합니다.
    """
    dir_path = Path(directory_path)
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    
    # 확장자 튜플화 정제
    if extension:
        if isinstance(extension, str):
            extension = (extension.lower(),)
        else:
            extension = tuple(ext.lower() for ext in extension)

    files = []
    try:
        for entry in dir_path.iterdir():
            if entry.is_file():
                if extension and not entry.name.lower().endswith(extension):
                    continue
                files.append(str(entry.resolve()) if full_path else entry.name)
    except PermissionError:
        print(f"⚠️ 권한 부족으로 디렉토리 접근 실패: {dir_path}")
    except OSError as e:
        print(f"⚠️ 디렉토리 읽기 오류 ({dir_path}): {e}")
            
    return files


def move_file(src_path: PathLike, dest_path: PathLike) -> bool:
    """원본 파일을 대상 경로로 이동하거나 이름을 변경합니다.
    
    학습 자료 처리 파이프라인에서 '처리 대기' 상태의 파일이 Whisper나 Gemini 파이프라인을 거쳐 
    '처리 완료' 또는 '아카이브' 폴더로 이동되는 상태 전이(State Transition) 단계에서 필수적으로 사용됩니다.
    
    대상 경로의 상위 폴더 구조가 존재하지 않을 수 있으므로 내부적으로 `ensure_parent_dir`을 호출하여 
    안전하게 공간을 확보한 뒤 `shutil.move`를 실행합니다. 다중 워커 스레드가 동작하는 환경에서 
    파일 점유율(Lock) 충돌이나 권한 거부 등 OS 예외가 발생할 수 있는데, 이를 안전하게 포착하고 
    실패(False)로 반환하여 Controller가 재시도(Retry) 로직을 태울 수 있도록 설계되었습니다.

    Args:
        src_path (PathLike): 이동시킬 원본 파일의 현재 로컬 경로.
        dest_path (PathLike): 파일이 이동될 목적지 경로 (새로운 파일명 포함).

    Returns:
        bool: 파일 이동이 성공적으로 완료되었을 경우 **True**, 예외(권한, 파일 없음 등)로 인해 실패했을 경우 **False**를 반환합니다.
    """
    src = Path(src_path)
    dest = Path(dest_path)
    
    if src.exists() and src.is_file():
        try:
            ensure_parent_dir(dest)
            shutil.move(str(src), str(dest))
            return True
        except FileNotFoundError:
            print(f"⚠️ 이동 실패: 원본 파일을 찾을 수 없습니다. ({src.name})")
        except PermissionError:
            print(f"⚠️ 이동 실패: 파일 접근 권한이 없습니다. ({src.name} -> {dest})")
        except OSError as e:
            print(f"⚠️ 파일 이동 중 OS 오류 발생 ({src.name} -> {dest}): {e}")
    return False


def copy_file(src_path: PathLike, dest_path: PathLike) -> bool:
    """원본 파일을 목적지 경로로 복사합니다 (메타데이터 포함).
    
    PDF 병합, 분할 또는 워터마크 주입 전 원본 훼손을 방지하기 위한 백업(Backup) 파이프라인에서 주로 호출됩니다. 
    단순 데이터 복사를 넘어 `shutil.copy2`를 사용하여 파일의 생성일, 수정일 등 주요 메타데이터를 
    최대한 보존하므로, 추후 '최근 수정일'을 기준으로 동작하는 동기화 로직이나 Watchdog 이벤트 추적 시 
    무결성을 유지할 수 있습니다. 대상 디렉토리가 없을 경우 자동으로 생성합니다.

    Args:
        src_path (PathLike): 복사할 원본 파일의 경로.
        dest_path (PathLike): 복사본이 생성될 대상 경로.

    Returns:
        bool: 복사 작업이 성공적으로 완료되었으면 **True**, 권한 문제나 원본 파일 누락 등으로 실패하면 **False**를 반환합니다.
    """
    src = Path(src_path)
    dest = Path(dest_path)
    
    if src.exists() and src.is_file():
        try:
            ensure_parent_dir(dest)
            shutil.copy2(str(src), str(dest))
            return True
        except FileNotFoundError:
            print(f"⚠️ 복사 실패: 원본 파일을 찾을 수 없습니다. ({src.name})")
        except PermissionError:
            print(f"⚠️ 복사 실패: 파일 접근 권한이 없습니다. ({src.name} -> {dest})")
        except OSError as e:
            print(f"⚠️ 파일 복사 중 OS 오류 발생 ({src.name} -> {dest}): {e}")
    return False


def delete_file(file_path: PathLike) -> bool:
    """지정된 경로의 파일이 존재할 경우 안전하게 삭제(Unlink)합니다.
    
    PDF에서 추출된 단기 오디오 파일(Whisper 처리용 임시 파일)이나 다운로드된 임시 캐시 데이터를 
    사용 직후 즉각적으로 제거(Clean-up)할 때 호출됩니다.
    
    자동화 서버 환경에서 스토리지 낭비 및 용량 초과로 인한 시스템 다운을 방지하는 중요한 역할을 합니다. 
    삭제를 시도하기 전 파일의 존재 및 타입(디렉토리 여부)을 선행 검증하며, Worker 스레드 간 
    동시성 이슈나 타 프로세스의 파일 점유로 인해 삭제 권한이 거부되더라도 예외를 내부에서 소화하여 
    메인 파이프라인의 진행을 가로막지 않도록 설계되었습니다.

    Args:
        file_path (PathLike): 삭제하고자 하는 대상 파일의 로컬 경로.

    Returns:
        bool: 정상적으로 파일이 삭제되었으면 **True**, 파일이 존재하지 않거나 예외가 발생해 삭제에 실패하면 **False**를 반환합니다.
    """
    path = Path(file_path)
    if path.exists() and path.is_file():
        try:
            path.unlink()
            return True
        except PermissionError:
            print(f"⚠️ 삭제 실패: 파일이 사용 중이거나 권한이 없습니다. ({path.name})")
        except OSError as e:
            print(f"⚠️ 파일 삭제 중 OS 오류 발생 ({path.name}): {e}")
    return False


def save_text_file(
    content: str, 
    save_path: PathLike, 
    mode: str = 'w', 
    encoding: str = 'utf-8'
) -> str:
    """텍스트나 JSON 형태의 문자열 데이터를 로컬 파일 시스템에 저장합니다.
    
    LLM 분석 결과, 트랜스크립트 텍스트, 애플리케이션 상태 정보 등을 로컬에 직렬화하는 핵심 I/O 함수입니다. 
    비동기 처리 관점에서 이 함수의 가장 중요한 역할은 **원자적 쓰기(Atomic Write)**의 지원입니다. 
    
    대용량 문자열을 디스크에 쓰는 도중 시스템 크래시나 사용자 강제 종료가 발생하면 파일이 
    불완전하게(0 bytes 등) 손상된 채로 남게 됩니다. 이를 방지하고자 덮어쓰기('w') 모드에서는 
    임시 파일(`.tmp`)에 전체 데이터를 온전히 기록한 후 성공했을 때만 `replace()`를 호출하여 원본과 
    스왑(Swap)합니다. 이로써 어떠한 중단 상황에서도 데이터 무결성이 보장됩니다. 
    오류 발생 시 상위 Service 계층으로 예외를 전파하여 적절한 UI 알림 또는 재시도가 가능하게 합니다.

    Args:
        content (str): 파일에 기록할 텍스트 또는 JSON 포맷의 문자열 데이터.
        save_path (PathLike): 파일이 최종적으로 저장될 목표 경로.
        mode (str, optional): 파일 쓰기 모드. 기본값은 덮어쓰기 모드인 'w'이며, 로그 생성 등을 위해 이어쓰기인 'a' 등을 지정할 수 있습니다.
        encoding (str, optional): 텍스트 인코딩 방식. 기본값은 'utf-8'.

    Returns:
        str: 저장이 성공적으로 완료된 최종 파일의 경로 문자열.

    Raises:
        PermissionError: 임시 파일 작성이나 파일 교체 중 시스템 접근 권한이 없을 때 발생합니다.
        OSError: 디스크 용량 부족, 잘못된 파일 시스템, 또는 기타 하위 레벨의 I/O 오류 시 발생합니다.
    """
    save_p = ensure_parent_dir(save_path)
    
    # 'w' (덮어쓰기) 모드일 때만 원자적 쓰기(Atomic Write) 적용
    if mode == 'w':
        temp_p = save_p.with_name(save_p.name + '.tmp')
        try:
            with open(temp_p, mode=mode, encoding=encoding) as f:
                f.write(content)
            temp_p.replace(save_p)
        except PermissionError as e:
            if temp_p.exists():
                temp_p.unlink(missing_ok=True)
            print(f"⚠️ 저장 실패: 쓰기 권한이 없습니다. ({save_p.name})")
            raise e
        except OSError as e:
            if temp_p.exists():
                temp_p.unlink(missing_ok=True)
            print(f"⚠️ 저장 실패: 디스크 I/O 오류 발생. ({save_p.name})")
            raise e
    else:
        # 'a' (이어쓰기) 등 다른 모드는 일반 방식으로 처리
        try:
            with open(save_p, mode=mode, encoding=encoding) as f:
                f.write(content)
        except OSError as e:
            print(f"⚠️ 이어쓰기 실패: 디스크 I/O 오류 발생. ({save_p.name})")
            raise e
            
    return str(save_p)


def read_text_file(file_path: PathLike, encoding: str = 'utf-8') -> str | None:
    """지정된 경로의 텍스트 또는 JSON 파일을 읽어 문자열 형태로 반환합니다.
    
    Controller 또는 Service가 과거에 캐싱해둔 LLM 응답, 추출 완료된 텍스트 대본(Transcript), 
    또는 설정 파일을 메모리로 적재할 때 사용되는 기본 데이터 수집 엔드포인트입니다. 
    
    파이프라인이 자동화되어 백그라운드에서 끊임없이 도는 상황에서는 존재하지 않는 경로 참조, 
    `UnicodeDecodeError`(인코딩 불일치), 타 프로세스의 파일 락 등으로 인해 읽기 실패가 빈번히 일어날 수 있습니다. 
    이 함수는 이러한 런타임 I/O 에러들을 포착하여 콘솔에 징후를 로깅하고, 예외를 발생(Raise)시키는 대신 
    `None`을 반환하는 Fallback 구조를 취합니다. 이를 통해 호출부(Service)가 조건 분기를 통해 
    기본값 적용 등 유연한 복구 절차를 밟을 수 있습니다.

    Args:
        file_path (PathLike): 읽고자 하는 대상 파일의 로컬 경로.
        encoding (str, optional): 텍스트 디코딩 시 사용할 인코딩 방식. 기본값은 'utf-8'.

    Returns:
        str | None: 파일 읽기에 성공한 경우 파일의 전체 내용(문자열), 
            파일이 존재하지 않거나 디코딩/권한/I/O 오류가 발생한 경우 **None**을 반환합니다.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
        
    try:
        with open(path, mode='r', encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        print(f"⚠️ 읽기 실패: 인코딩({encoding})이 일치하지 않습니다. ({path.name})")
        return None
    except PermissionError:
        print(f"⚠️ 읽기 실패: 접근 권한이 없습니다. ({path.name})")
        return None
    except OSError as e:
        print(f"⚠️ 파일 읽기 오류 ({path.name}): {e}")
        return None