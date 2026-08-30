from base.base_worker import BaseWorker

class TranscriptDriveSearchWorker(BaseWorker):
    def __init__(self, controller, start_date, end_date):
        super().__init__()
        self.controller = controller
        self.start_date = start_date
        self.end_date = end_date

    def do_work(self):
        return self.controller.get_drive_text_files(self.start_date, self.end_date)

class TranscriptReadWorker(BaseWorker):
    def __init__(self, controller, filenames, folder_path, is_drive):
        super().__init__()
        self.controller = controller
        self.filenames = filenames
        self.folder_path = folder_path
        self.is_drive = is_drive

    def do_work(self):
        contents = []
        for fname in self.filenames:
            if self.is_cancelled(): break
            c = self.controller.read_drive_file(fname) if self.is_drive else self.controller.read_local_file(self.folder_path, fname)
            contents.append(c)
        return {"filenames": self.filenames, "contents": contents}

class TranscriptSplitSaveWorker(BaseWorker):
    def __init__(self, controller, folder_path, filename, text_content, name1, name2, is_drive):
        super().__init__()
        self.controller = controller
        self.folder_path = folder_path
        self.filename = filename
        self.text_content = text_content
        self.name1 = name1
        self.name2 = name2
        self.is_drive = is_drive

    def do_work(self):
        saved_files = self.controller.split_text_file(
            self.folder_path, self.filename, self.text_content, self.name1, self.name2
        )
        msg = f"총 {len(saved_files)}개의 파일로 분할되어 로컬에 저장되었습니다."
        if self.is_drive:
            self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
            for path in saved_files:
                if self.is_cancelled(): break
                self.controller.upload_to_drive(path)
            msg += "\n(드라이브 업로드도 완료되었습니다!)"
        return msg

class TranscriptMergeSaveWorker(BaseWorker):
    def __init__(self, controller, folder_path, files_to_merge, merged_content, custom_name, is_drive):
        super().__init__()
        self.controller = controller
        self.folder_path = folder_path
        self.files_to_merge = files_to_merge
        self.merged_content = merged_content
        self.custom_name = custom_name
        self.is_drive = is_drive

    def do_work(self):
        import os
        saved_file = self.controller.merge_text_files(
            self.folder_path, self.files_to_merge, self.merged_content, self.custom_name
        )
        new_filename = os.path.basename(saved_file)
        msg = f"파일이 성공적으로 병합되어 로컬에 저장되었습니다:\n{new_filename}"
        if self.is_drive:
            self.log_signal.emit("☁️ 드라이브 자동 업로드를 진행합니다...")
            self.controller.upload_to_drive(saved_file)
            msg += "\n\n(드라이브 업로드도 완료되었습니다!)"
        return msg, new_filename
