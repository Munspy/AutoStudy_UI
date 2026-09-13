import re

with open("ui/drive_sync_ui.py", "r") as f:
    content = f.read()

# Remove the reset_search_btn method
content = re.sub(r'    def reset_search_btn\(self\):\n        self\.search_btn\.stop_loading\(\)\n\n', '', content)

# Remove the handle_worker_error method
content = re.sub(r'    def handle_worker_error\(self, err\):\n        GlobalLogger\.info\(f"\[오류 발생\] \{err\}"\)\n\n', '', content)

with open("ui/drive_sync_ui.py", "w") as f:
    f.write(content)
