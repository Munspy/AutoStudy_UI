from PyQt6.QtWidgets import QDialog

class JsonEditerUi(QDialog):
    def __init__(self, task_manager=None, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.setWindowTitle("Json 직접 수정")
        self.resize(340, 150)