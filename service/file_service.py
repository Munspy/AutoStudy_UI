import os

class FileService:
    @staticmethod
    def delete_files(file_paths_or_ids: list, is_drive: bool, log_callback=None):
        """전달받은 파일 리스트를 로컬 또는 드라이브에서 실제 삭제합니다."""
        for f_id_or_path in file_paths_or_ids:
            if is_drive:
                from core.container import AppContainer
                drive_client = AppContainer.get_instance().drive_client
                drive_client.delete_drive_file(f_id_or_path)
                if log_callback: log_callback(f"드라이브 파일 삭제: {f_id_or_path}")
            else:
                if os.path.exists(f_id_or_path):
                    os.remove(f_id_or_path)
                    if log_callback: log_callback(f"로컬 파일 삭제: {f_id_or_path}")