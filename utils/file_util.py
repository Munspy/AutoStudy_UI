"""
파일 시스템 유틸리티 모듈 (utils/file_util.py)

이 모듈은 파일 생성, 이동, 복사, 삭제 및 디렉토리 탐색과 같은 로컬 파일 시스템 제어를 
위한 유틸리티 함수들을 제공합니다. 데이터 전처리 파이프라인이나 로컬 파일 입출력이 
빈번하게 일어나는 애플리케이션에서 안전한 파일 조작(예: 부모 디렉토리 자동 생성, 
원자적 쓰기(Atomic Write) 지원 등)을 보장하며, 예외 발생 시 에러를 로깅하고 프로그램의 
중단을 방지하는 역할을 수행합니다. 모든 경로는 호환성을 위해 `str`과 `pathlib.Path`를 
모두 지원합니다.
"""

import os
import shutil
from pathlib import Path
from typing import Union, List, Tuple

# 경로 입력 시 str과 pathlib.Path 모두 지원하도록 정의
PathLike = Union[str, Path]


def ensure_parent_dir(file_path: PathLike) -> Path:
    """
    대상 파일 경로의 상위(부모) 디렉토리가 존재하는지 확인하고, 없다면 자동으로 생성합니다.
    
    파일을 저장하거나 복사, 이동하는 작업을 수행할 때 목적지의 디렉토리 트리가 
    존재하지 않아 발생하는 `FileNotFoundError`를 방지하기 위해 필수적으로 사용됩니다. 
    단순히 최종 디렉토리만 생성하는 것이 아니라 `parents=True` 옵션을 통해 
    중간 단계의 모든 누락된 디렉토리를 재귀적으로 생성하여 안전한 파일 쓰기 환경을 구축합니다.

    Args:
        file_path (PathLike): 생성하려는 파일 또는 디렉토리의 전체 경로. (문자열 또는 Path 객체)

    Returns:
        Path: 내부적으로 생성 및 확인 작업을 마친 파일의 전체 경로를 Path 객체로 변환하여 반환합니다.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def list_local_files(
    directory_path: PathLike, 
    extension: Union[str, Tuple[str, ...]] = None, 
    full_path: bool = False
) -> List[str]:
    """
    지정된 디렉토리 내에 존재하는 파일들의 목록을 탐색 및 필터링하여 반환합니다.
    
    데이터 파이프라인에서 특정 확장자(예: .json, .csv, .txt 등)를 가진 파일들만 
    일괄적으로 불러와 처리해야 할 때 유용하게 쓰입니다. 내부적으로 입력받은 확장자 문자열이나 
    튜플을 일관된 형태(소문자 튜플)로 정제하여 대소문자 구분 없이 안전하게 확장자 
    매칭을 수행하도록 설계되었습니다. 디렉토리가 존재하지 않거나 권한 부족 등의 OS 레벨 예외가 
    발생하더라도 시스템 크래시 없이 빈 리스트를 반환하고 에러를 출력하여 견고함을 유지합니다.

    Args:
        directory_path (PathLike): 탐색할 대상 디렉토리의 경로.
        extension (Union[str, Tuple[str, ...]], optional): 필터링할 파일 확장자. 
            단일 문자열(예: '.txt') 또는 문자열 튜플(예: ('.jpg', '.png')) 형태로 입력 가능합니다. 기본값은 None입니다.
        full_path (bool, optional): 반환되는 파일 목록의 형태를 결정하는 플래그. 
            True일 경우 절대 경로를 반환하며, False일 경우 파일명만 반환합니다. 기본값은 False입니다.

    Returns:
        List[str]: 탐색 및 필터링 조건에 부합하는 파일 경로 또는 파일명들의 리스트.
            오류가 발생하거나 조건에 맞는 파일이 없다면 빈 리스트를 반환합니다.
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
    """
    원본 파일을 대상 경로로 이동하거나 이름을 변경합니다.
    
    파일 이동 시 대상 경로가 위치할 상위 폴더 구조가 존재하지 않을 수 있으므로, 
    내부적으로 `ensure_parent_dir` 함수를 호출하여 폴더 트리를 먼저 안전하게 구성합니다. 
    그 후 `shutil.move`를 사용하여 파일을 전송하며, 이 과정에서 발생할 수 있는 
    원본 파일 유실, 접근 권한 거부, 디스크 I/O 오류 등의 다양한 OS 예외를 포착하고 
    안전하게 콘솔에 경고를 출력한 뒤 실패 처리를 합니다. 파이프라인의 파일 정리나 
    처리 완료된 데이터의 아카이빙 단계에서 필수적으로 사용됩니다.

    Args:
        src_path (PathLike): 이동시킬 원본 파일의 경로.
        dest_path (PathLike): 파일이 이동될 목적지 경로 (새로운 파일명 포함 가능).

    Returns:
        bool: 파일 이동이 성공적으로 완료되었을 경우 True, 오류로 인해 실패했을 경우 False를 반환합니다.
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
    """
    원본 파일을 목적지 경로로 복사합니다 (메타데이터 포함).
    
    단순히 파일의 데이터 내용만 복사하는 것이 아니라 `shutil.copy2`를 사용하여 생성일, 
    수정일 등의 주요 파일 시스템 메타데이터까지 최대한 함께 보존하며 복사를 수행합니다. 
    대상 디렉토리 트리가 없을 경우 자동으로 생성하여 예외를 방지하며, 
    데이터 백업이나 원본 훼손 없이 파일을 복제하여 가공해야 하는 안전한 데이터 처리 파이프라인 
    단계에서 유용하게 사용됩니다.

    Args:
        src_path (PathLike): 복사할 원본 파일의 경로.
        dest_path (PathLike): 복사본이 생성될 대상 경로.

    Returns:
        bool: 복사 작업이 성공적으로 완료되었으면 True, 권한 문제나 원본 파일 누락 등으로 실패하면 False를 반환합니다.
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
    """
    지정된 경로의 파일이 존재할 경우 안전하게 삭제(Unlink)합니다.
    
    단기 임시 파일(temp files)을 정리하거나 더 이상 필요 없는 캐시 데이터를 
    제거할 때 호출됩니다. 파일 존재 여부와 파일 타입(디렉토리가 아닌지)을 먼저 
    검증한 후 삭제를 시도하여 불필요한 예외를 줄입니다. 만약 다른 프로세스에서 
    파일을 점유하고 있거나 권한이 부족한 경우를 대비해 예외 처리 블록이 구성되어 있어, 
    삭제 작업 실패가 전체 애플리케이션의 크래시로 이어지지 않게 방어합니다.

    Args:
        file_path (PathLike): 삭제하고자 하는 대상 파일의 경로.

    Returns:
        bool: 정상적으로 파일이 삭제되었으면 True, 파일이 존재하지 않거나 예외가 발생해 삭제에 실패하면 False를 반환합니다.
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
    """
    텍스트나 JSON 형태의 문자열 데이터를 로컬 파일 시스템에 저장합니다.
    
    이 함수의 핵심은 덮어쓰기('w') 모드에서 제공하는 원자적 쓰기(Atomic Write) 로직입니다. 
    대용량 데이터를 쓰는 도중에 시스템 크래시나 전원 차단이 발생하면 파일이 불완전하게 
    손상된 상태로 남을 수 있습니다. 이를 방지하기 위해 임시 파일(.tmp)에 먼저 데이터를 
    온전히 기록한 후, 성공적으로 작성이 끝났을 때만 원본 파일과 원자적으로 교체(replace)하여 
    데이터의 무결성을 보장합니다. 저장하려는 경로의 상위 디렉토리가 없으면 자동으로 생성하며, 
    I/O 예외 발생 시 에러를 로깅하고 상위 호출자로 다시 던져(raise) 확실한 후처리를 유도합니다.

    Args:
        content (str): 파일에 기록할 텍스트 또는 JSON 포맷의 문자열 데이터.
        save_path (PathLike): 파일이 최종적으로 저장될 경로.
        mode (str, optional): 파일 쓰기 모드. 기본값은 덮어쓰기 모드인 'w'이며, 이어쓰기인 'a' 등을 지정할 수 있습니다.
        encoding (str, optional): 텍스트 인코딩 방식. 기본값은 'utf-8'입니다.

    Returns:
        str: 저장이 성공적으로 완료된 최종 파일의 경로를 문자열로 반환합니다.

    Raises:
        PermissionError: 임시 파일 작성이나 파일 교체 중 접근 권한이 없을 때 발생합니다.
        OSError: 디스크 용량 부족, 잘못된 파일 시스템, 또는 기타 I/O 오류가 발생할 때 발생합니다.
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
    """
    지정된 경로의 텍스트 또는 JSON 파일을 읽어 문자열 형태로 반환합니다.
    
    파일 시스템에서 데이터를 불러와 메모리에 로드하는 기본적인 데이터 수집 역할을 수행합니다. 
    존재하지 않는 경로나 디렉토리를 읽으려 시도하는 논리적 오류를 사전에 방어하며, 
    인코딩 불일치(`UnicodeDecodeError`), 권한 부족(`PermissionError`) 등 파일을 읽는 동안 
    흔히 직면하는 에러들을 개별적으로 포착하여 상황에 맞는 디버깅용 경고 메시지를 출력합니다. 
    오류 시 예외를 던지는 대신 None을 반환하므로 호출부에서 유연하게 실패를 처리(Fallback)할 수 있습니다.

    Args:
        file_path (PathLike): 읽고자 하는 대상 파일의 경로.
        encoding (str, optional): 텍스트 디코딩 시 사용할 인코딩 방식. 기본값은 'utf-8'입니다.

    Returns:
        str | None: 파일 읽기에 성공한 경우 파일의 전체 내용(문자열), 
            파일이 존재하지 않거나 읽는 도중 오류가 발생한 경우 None을 반환합니다.
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