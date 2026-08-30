from PyQt6.QtWidgets import QTableWidget, QListWidget, QListWidgetItem, QCheckBox, QDateEdit, QComboBox, QHeaderView
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableWidget, QTableWidgetItem, QLabel, 
                             QHeaderView, QCheckBox, QComboBox, QInputDialog, 
                             QFrame, QMessageBox, QDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
import controller.json_editer_controller as backend

class JsonEditerUi(QDialog):
    def __init__(self, task_manager=None, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.setWindowTitle("Json 직접 수정")
        self.resize(340, 150)