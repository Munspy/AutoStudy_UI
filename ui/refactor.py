import re

def process_drive_sync():
    path = "/Users/baek/Desktop/UI/ui/drive_sync_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Add imports
    if "from base.base_ui_components import" not in content:
        content = content.replace("from base.base_ui import BaseUI", "from base.base_ui import BaseUI\nfrom base.base_ui_components import LoadingButton, StyledButton, CardWidget")

    # CardWidget replacement
    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    # Buttons
    content = re.sub(r'self\.btn_set_folder = QPushButton\("📂 로컬 폴더"\)\n\s*self\.btn_set_folder\.setCursor[^)]+\)\n\s*self\.btn_set_folder\.setStyleSheet\([^)]+\)', 'self.btn_set_folder = StyledButton("📂 로컬 폴더", "secondary")', content)
    
    content = re.sub(r'self\.search_btn = QPushButton\("데이터 동기화 및 조회"\)\n\s*self\.search_btn\.setCursor[^)]+\)\n\s*self\.search_btn\.setStyleSheet\([^)]+\)', 'self.search_btn = LoadingButton("데이터 동기화 및 조회", "primary")', content)
    
    content = re.sub(r'btn_run_local = QPushButton\("누락 로컬 작업 모두 실행"\)\n\s*btn_run_local\.setStyleSheet[^)]+\)\n\s*btn_run_local\.setCursor[^)]+\)', 'btn_run_local = StyledButton("누락 로컬 작업 모두 실행", "success")', content)
    
    content = re.sub(r'btn_run_whisper = QPushButton\("🎙️ Whisper AI 전사 실행"\)\n\s*btn_run_whisper\.setStyleSheet[^)]+\)\n\s*btn_run_whisper\.setCursor[^)]+\)', 'btn_run_whisper = StyledButton("🎙️ Whisper AI 전사 실행", "primary")', content)
    
    content = re.sub(r'btn_dl_script = QPushButton\("📄 스크립트 합본 다운로드"\)\n\s*btn_dl_script\.setStyleSheet[^)]+\)\n\s*btn_dl_script\.setCursor[^)]+\)', 'btn_dl_script = StyledButton("📄 스크립트 합본 다운로드", "danger")', content)
    
    # Secondary buttons
    secondary = r'btn_dl_summary = QPushButton\("📝 요약본 다운로드"\)\n\s*btn_dl_anki = QPushButton\("🗂️ Anki 다운로드"\)\n\n\s*for btn in \[btn_dl_summary, btn_dl_anki\]:\n\s*btn\.setStyleSheet\(secondary_style\)\n\s*btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\n\s*actions_layout\.addWidget\(btn\)'
    repl = 'btn_dl_summary = StyledButton("📝 요약본 다운로드", "secondary")\n        btn_dl_anki = StyledButton("🗂️ Anki 다운로드", "secondary")\n        actions_layout.addWidget(btn_dl_summary)\n        actions_layout.addWidget(btn_dl_anki)'
    content = re.sub(r'secondary_style = """[\s\S]*?"""\n\s*' + secondary, repl, content)
    
    # Update search_btn usage
    content = content.replace('self.search_btn.setEnabled(False)\n        self.search_btn.setText("조회 중...")', 'self.search_btn.start_loading("조회 중")')
    content = content.replace('self.search_btn.setEnabled(True)\n        self.search_btn.setText("데이터 동기화 및 조회")', 'self.search_btn.stop_loading()')
    
    # primary_btn_style block remove
    content = re.sub(r'primary_btn_style = """[\s\S]*?"""\n', '', content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_combine_notes():
    path = "/Users/baek/Desktop/UI/ui/combine_notes_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "from base.base_ui_components import LoadingButton, StyledButton, CardWidget," not in content:
        content = content.replace("from base.base_ui_components import create_pdf_thumbnail_frame, bytes_to_pixmap", "from base.base_ui_components import create_pdf_thumbnail_frame, bytes_to_pixmap, LoadingButton, StyledButton, CardWidget")

    # FullScreenEditDialog Buttons
    content = re.sub(r'cancel_btn = QPushButton\("수정 취소 \(Cancel\)"\)\n\s*cancel_btn\.setCursor[^)]+\)\n\s*cancel_btn\.setStyleSheet\([^)]+\)', 'cancel_btn = StyledButton("수정 취소 (Cancel)", "danger")', content)
    content = re.sub(r'save_btn = QPushButton\("수정 완료 \(Save\)"\)\n\s*save_btn\.setCursor[^)]+\)\n\s*save_btn\.setStyleSheet\([^)]+\)', 'save_btn = StyledButton("수정 완료 (Save)", "success")', content)

    # QFrame to CardWidget
    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    # Buttons
    content = re.sub(r'browse_btn = QPushButton\("폴더 변경"\)\n\s*browse_btn\.setCursor[^)]+\)\n\s*browse_btn\.setStyleSheet\([^)]+\)', 'browse_btn = StyledButton("폴더 변경", "secondary")', content)
    
    content = re.sub(r'auto_run_btn = QPushButton\("🚀 선택 파일 알아서 진행하기"\)\n\s*auto_run_btn\.setCursor[^)]+\)\n\s*auto_run_btn\.setStyleSheet\([^)]+\)', 'auto_run_btn = StyledButton("🚀 선택 파일 알아서 진행하기", "success")', content)
    
    content = re.sub(r'manual_run_btn = QPushButton\("👀 선택 파일 검수하기"\)\n\s*manual_run_btn\.setCursor[^)]+\)\n\s*manual_run_btn\.setStyleSheet\([^)]+\)', 'manual_run_btn = StyledButton("👀 선택 파일 검수하기", "primary")', content)
    
    content = re.sub(r'self\.edit_btn = QPushButton\("상세 검수 및 수정 \(전체화면\)"\)\n\s*self\.edit_btn\.setCursor[^)]+\)\n\s*self\.edit_btn\.setStyleSheet\([^)]+\)', 'self.edit_btn = StyledButton("상세 검수 및 수정 (전체화면)", "secondary")', content)
    
    content = re.sub(r'self\.approve_btn = QPushButton\("최종 승인 및 병합 저장"\)\n\s*self\.approve_btn\.setCursor[^)]+\)\n\s*self\.approve_btn\.setStyleSheet\([^)]+\)', 'self.approve_btn = StyledButton("최종 승인 및 병합 저장", "danger")', content)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_pdf_merge():
    path = "/Users/baek/Desktop/UI/ui/pdf_merge_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "from base.base_ui_components import LoadingButton, StyledButton, CardWidget," not in content:
        content = content.replace("from base.base_ui_components import create_pdf_thumbnail_frame", "from base.base_ui_components import create_pdf_thumbnail_frame, LoadingButton, StyledButton, CardWidget")

    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    content = re.sub(r'browse_btn = QPushButton\("폴더 변경"\)\n\s*browse_btn\.setCursor[^)]+\)\n\s*browse_btn\.setStyleSheet\([^)]+\)', 'browse_btn = StyledButton("폴더 변경", "secondary")', content)
    
    content = re.sub(r'search_btn = QPushButton\("파일 조회"\)\n\s*search_btn\.setCursor[^)]+\)\n\s*search_btn\.setStyleSheet\([^)]+\)', 'search_btn = LoadingButton("파일 조회", "primary")', content)
    
    content = re.sub(r'self\.select_scripted_btn = QPushButton\("스크립트본 선택"\)\n\s*self\.select_scripted_btn\.setCursor[^)]+\)\n\s*self\.select_scripted_btn\.setStyleSheet\([^)]+\)', 'self.select_scripted_btn = StyledButton("스크립트본 선택", "secondary")', content)
    
    content = re.sub(r'save_btn = QPushButton\("💾 선택 파일 병합 및 저장"\)\n\s*save_btn\.setCursor[^)]+\)\n\s*save_btn\.setStyleSheet\([^)]+\)', 'save_btn = StyledButton("💾 선택 파일 병합 및 저장", "success")', content)
    
    # QThread removal if unused. Wait, QThread is used in PyQt imports? "from PyQt6.QtCore import Qt, pyqtSignal, QDate, QThread". If it's not used, remove it.
    if "QThread(" not in content:
        content = content.replace(", QThread", "")
        
    # global_loading_signal use on search_btn? It emits global_loading_signal. We can ignore search_btn loading state for now or keep it as LoadingButton and we manually control it. But wait, search_btn is just a local var here? Wait! `search_btn` is local in `init_ui`, so it can't be used across methods unless we change it to `self.search_btn`. Let's just make it `self.search_btn`.
    content = content.replace('search_btn = LoadingButton', 'self.search_btn = LoadingButton')
    content = content.replace('search_btn.clicked', 'self.search_btn.clicked')
    content = content.replace('control_layout.addWidget(search_btn)', 'control_layout.addWidget(self.search_btn)')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_pdf_split():
    path = "/Users/baek/Desktop/UI/ui/pdf_split_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove pymupdf if present and unused. Wait, `pdf_split_ui.py` uses pymupdf for what?
    # Wait, the instructions say "remove unused pymupdf (e.g. dummy import in pdf_split_ui.py)".
    # Tab 3 load_more_pages is in pdf_merge_ui.py so leave pymupdf there.
    content = re.sub(r'^import pymupdf\n', '', content, flags=re.MULTILINE)

    if "from base.base_ui_components import" not in content:
        content = content.replace("from controller.pdf_split_controller import PdfSplitController", "from base.base_ui_components import LoadingButton, StyledButton, CardWidget\nfrom controller.pdf_split_controller import PdfSplitController")

    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    content = re.sub(r'browse_btn = QPushButton\("폴더 변경"\)\n\s*browse_btn\.setCursor[^)]+\)\n\s*browse_btn\.setStyleSheet\([^)]+\)', 'browse_btn = StyledButton("폴더 변경", "secondary")', content)
    
    content = re.sub(r'search_btn = QPushButton\("파일 조회"\)\n\s*search_btn\.setCursor[^)]+\)\n\s*search_btn\.setStyleSheet\([^)]+\)', 'self.search_btn = LoadingButton("파일 조회", "primary")', content)
    content = content.replace('search_btn.clicked', 'self.search_btn.clicked')
    content = content.replace('control_layout.addWidget(search_btn)', 'control_layout.addWidget(self.search_btn)')
    
    content = re.sub(r'save_btn = QPushButton\("💾 선택 파일 분할 및 저장"\)\n\s*save_btn\.setCursor[^)]+\)\n\s*save_btn\.setStyleSheet\([^)]+\)', 'save_btn = StyledButton("💾 선택 파일 분할 및 저장", "danger")', content)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_transcript():
    path = "/Users/baek/Desktop/UI/ui/transcript_merge_split_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "from base.base_ui_components import" not in content:
        content = content.replace("from base.base_ui import BaseUI", "from base.base_ui import BaseUI\nfrom base.base_ui_components import LoadingButton, StyledButton, CardWidget")

    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    content = re.sub(r'browse_btn = QPushButton\("폴더 찾기"\)\n\s*browse_btn\.setCursor[^)]+\)\n\s*browse_btn\.setStyleSheet\([^)]+\)', 'browse_btn = StyledButton("폴더 찾기", "secondary")', content)
    
    content = re.sub(r'self\.search_btn = QPushButton\("파일 조회"\)\n\s*self\.search_btn\.setCursor[^)]+\)\n\s*self\.search_btn\.setStyleSheet\([^)]+\)', 'self.search_btn = LoadingButton("파일 조회", "primary")', content)
    
    content = re.sub(r'find_btn = QPushButton\("검색"\)\n\s*find_btn\.setStyleSheet\([^)]+\)', 'find_btn = StyledButton("검색", "secondary")', content)
    
    content = re.sub(r'save_split_btn = QPushButton\("💾 선택 파일 분할 및 저장"\)\n\s*save_split_btn\.setCursor[^)]+\)\n\s*save_split_btn\.setStyleSheet\([^)]+\)', 'save_split_btn = StyledButton("💾 선택 파일 분할 및 저장", "danger")', content)
    
    content = re.sub(r'save_merge_btn = QPushButton\("💾 선택 파일 병합 및 저장"\)\n\s*save_merge_btn\.setCursor[^)]+\)\n\s*save_merge_btn\.setStyleSheet\([^)]+\)', 'save_merge_btn = StyledButton("💾 선택 파일 병합 및 저장", "success")', content)
    
    # search_btn Loading states
    content = content.replace('self.search_btn.setText("조회 중...")\n            self.search_btn.setEnabled(False)', 'self.search_btn.start_loading("조회 중")')
    content = content.replace('self.search_btn.setText("파일 조회")\n        self.search_btn.setEnabled(True)', 'self.search_btn.stop_loading()')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_youtube():
    path = "/Users/baek/Desktop/UI/ui/youtube_playlist_ui.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "from base.base_ui_components import" not in content:
        content = content.replace("from base.base_ui import BaseUI", "from base.base_ui import BaseUI\nfrom base.base_ui_components import LoadingButton, StyledButton, CardWidget")

    # In PlaylistManagerDialog
    content = re.sub(r'self\.rename_btn = QPushButton\("이름 변경"\)\n\s*self\.delete_btn = QPushButton\("삭제"\)\n\s*for btn in \[self\.rename_btn, self\.delete_btn\]:\n\s*btn\.setCursor[^)]+\)\n\s*btn\.setStyleSheet\([^)]+\)', 'self.rename_btn = StyledButton("이름 변경", "secondary")\n        self.delete_btn = StyledButton("삭제", "danger")', content)
    
    # QFrame to CardWidget
    content = re.sub(r'control_frame = QFrame\(\)\n\s+control_frame\.setObjectName\("ControlBox"\)\n\s+control_frame\.setStyleSheet\([^)]+\)', 'control_frame = CardWidget()', content, flags=re.MULTILINE)
    
    content = re.sub(r'refresh_video_btn = QPushButton\("데이터 새로고침"\)\n\s*refresh_video_btn\.setCursor[^)]+\)\n\s*refresh_video_btn\.setStyleSheet\([^)]+\)', 'refresh_video_btn = StyledButton("데이터 새로고침", "secondary")', content)
    
    secondary = r'manage_pl_btn = QPushButton\("⚙️ 관리"\)\n\s*add_pl_btn = QPushButton\("➕ 추가"\)\n\s*refresh_list_btn = QPushButton\("🔄 목록 갱신"\)\n\s*secondary_btn_style = """[\s\S]*?"""\n\s*for btn in \[manage_pl_btn, add_pl_btn, refresh_list_btn\]:\n\s*btn\.setStyleSheet\(secondary_btn_style\)\n\s*btn\.setCursor\(Qt\.CursorShape\.PointingHandCursor\)\n\s*control_layout\.addWidget\(btn\)'
    repl = 'manage_pl_btn = StyledButton("⚙️ 관리", "secondary")\n        add_pl_btn = StyledButton("➕ 추가", "secondary")\n        refresh_list_btn = StyledButton("🔄 목록 갱신", "secondary")\n        control_layout.addWidget(manage_pl_btn)\n        control_layout.addWidget(add_pl_btn)\n        control_layout.addWidget(refresh_list_btn)'
    content = re.sub(secondary, repl, content)
    
    content = re.sub(r'sel_unex_btn = QPushButton\("🎯 음성 미추출 자동 선택"\)\n\s*sel_unex_btn\.setCursor[^)]+\)\n\s*sel_unex_btn\.setStyleSheet\([^)]+\)', 'sel_unex_btn = StyledButton("🎯 음성 미추출 자동 선택", "secondary")', content)
    
    content = re.sub(r'self\.upload_btn = QPushButton\("☁️ 선택 영상 음성 추출 및 업로드"\)\n\s*self\.upload_btn\.setCursor[^)]+\)\n\s*self\.upload_btn\.setStyleSheet\([^)]+\)', 'self.upload_btn = LoadingButton("☁️ 선택 영상 음성 추출 및 업로드", "primary")', content)
    
    # Using LoadingButton features
    content = content.replace('self.upload_btn.setEnabled(False)', 'self.upload_btn.start_loading("업로드 중")')
    content = content.replace('self.upload_btn.setEnabled(True)', 'self.upload_btn.stop_loading()')

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

process_drive_sync()
process_combine_notes()
process_pdf_merge()
process_pdf_split()
process_transcript()
process_youtube()
print("Success")
