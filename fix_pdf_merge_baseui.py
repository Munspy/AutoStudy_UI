import re

path = "ui/pdf_merge_ui.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add import BaseUI
if "from base.base_ui import BaseUI" not in content:
    content = content.replace("from base.base_ui_components", "from base.base_ui import BaseUI\nfrom base.base_ui_components")

# Replace QWidget with BaseUI
content = content.replace("class PdfMergeUi(QWidget):", "class PdfMergeUi(BaseUI):")

# Remove redundant log_signal and error_signal
content = re.sub(r'    log_signal = pyqtSignal\(str\)\n', '', content)
content = re.sub(r'    error_signal = pyqtSignal\(str, str\)\n', '', content)

# Modify __init__
init_old = """    def __init__(self, task_manager=None):
        super().__init__()
        self.task_manager = task_manager"""
init_new = """    def __init__(self, task_manager=None):
        super().__init__(task_manager=task_manager)"""
content = content.replace(init_old, init_new)

# Remove self.controller.error_signal.connect(self.error_signal.emit) because BaseUI doesn't have error_signal as a pyqtSignal, it uses show_error directly or maybe error_signal wasn't in BaseUI!
# Wait, BaseUI only has log_signal. It does NOT have error_signal as pyqtSignal!
# Look at BaseUI:
# class BaseUI(QWidget):
#     log_signal = pyqtSignal(str)
#     ...
