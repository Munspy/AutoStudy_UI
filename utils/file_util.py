# utils/file_util.py
import os
import shutil
from pathlib import Path
from typing import Union, List, Tuple

# 경로 입력 시 str과 pathlib.Path 모두 지원하도록 정의
PathLike = Union[str, Path]


def ensure_parent_dir(file_path: PathLike) -> Path:
    """
    파일 경로의 상위 디렉토리가 존재하지 않는 경우 자동으로 생성합니다.
    (파일 생성/복사/이동 시 FileNotFoundError 예방)
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
    지정된 디렉토리의 파일 리스트를 반환합니다.
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
    파일을 이동하거나 이름을 변경합니다.
    대상 경로의 상위 폴더가 없으면 자동으로 생성합니다.
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
    파일을 복사합니다. (메타데이터 포함)
    대상 경로의 상위 폴더가 없으면 자동으로 생성합니다.
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
    """파일이 존재할 경우 안전하게 삭제합니다."""
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
    텍스트/JSON 데이터를 로컬 파일로 저장합니다.
    저장 경로의 디렉토리가 존재하지 않는 경우 자동으로 생성합니다.
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
    """텍스트/JSON 파일의 내용을 읽어 반환합니다. (파일이 없으면 None)"""
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
