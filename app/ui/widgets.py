from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox, QLineEdit,
    QDoubleSpinBox, QMessageBox, QFileDialog, QProgressBar, QFrame, QDialog,
    QDialogButtonBox, QTextEdit, QCheckBox, QListWidget, QListWidgetItem,
    QTabWidget, QSizePolicy, QGridLayout, QSpinBox, QDateEdit
)
from PySide6.QtCore import Qt, Signal, QMimeData, QSize, QTimer, QDate
from PySide6.QtGui import (
    QColor, QBrush, QFont, QIcon, QDragEnterEvent, QDropEvent, QPainter,
    QAction, QKeySequence, QPixmap, QLinearGradient, QPen
)
from PySide6.QtSvgWidgets import QSvgWidget


def get_app_style():
    return """
    * {
        font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
        font-size: 10pt;
    }
    QMainWindow, QDialog {
        background-color: #f8fafc;
    }
    QWidget#Sidebar {
        background-color: #1e293b;
    }
    QLabel#SidebarTitle {
        color: #f1f5f9;
        font-size: 14pt;
        font-weight: bold;
        padding: 15px 20px;
        border-bottom: 1px solid #334155;
    }
    QPushButton#NavButton {
        color: #cbd5e1;
        background-color: transparent;
        border: none;
        padding: 12px 20px;
        text-align: left;
        font-size: 11pt;
    }
    QPushButton#NavButton:hover {
        background-color: #334155;
        color: #ffffff;
    }
    QPushButton#NavButton:checked {
        background-color: #3b82f6;
        color: #ffffff;
        border-left: 3px solid #60a5fa;
    }
    QLabel#PageTitle {
        color: #1e293b;
        font-size: 16pt;
        font-weight: bold;
        padding: 5px 0px;
    }
    QLabel#PageSubtitle {
        color: #64748b;
        font-size: 10pt;
        padding-bottom: 15px;
    }
    QFrame#Card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QPushButton {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 7px 16px;
        color: #334155;
    }
    QPushButton:hover {
        background-color: #f1f5f9;
        border-color: #94a3b8;
    }
    QPushButton:pressed {
        background-color: #e2e8f0;
    }
    QPushButton#PrimaryButton {
        background-color: #3b82f6;
        color: #ffffff;
        border-color: #3b82f6;
    }
    QPushButton#PrimaryButton:hover {
        background-color: #2563eb;
        border-color: #2563eb;
    }
    QPushButton#PrimaryButton:pressed {
        background-color: #1d4ed8;
    }
    QPushButton#DangerButton {
        background-color: #ef4444;
        color: #ffffff;
        border-color: #ef4444;
    }
    QPushButton#DangerButton:hover {
        background-color: #dc2626;
        border-color: #dc2626;
    }
    QPushButton#SuccessButton {
        background-color: #10b981;
        color: #ffffff;
        border-color: #10b981;
    }
    QPushButton#SuccessButton:hover {
        background-color: #059669;
        border-color: #059669;
    }
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit, QDateEdit {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px 10px;
        selection-background-color: #3b82f6;
    }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
        border-color: #3b82f6;
    }
    QTableWidget {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        gridline-color: #e2e8f0;
    }
    QTableWidget::item {
        padding: 6px 8px;
    }
    QTableWidget::item:selected {
        background-color: #dbeafe;
        color: #1e40af;
    }
    QHeaderView::section {
        background-color: #f1f5f9;
        color: #475569;
        padding: 10px 8px;
        border: none;
        border-right: 1px solid #e2e8f0;
        border-bottom: 2px solid #e2e8f0;
        font-weight: bold;
    }
    QFrame#DropZone {
        border: 2px dashed #94a3b8;
        border-radius: 12px;
        background-color: #f8fafc;
    }
    QFrame#DropZone:hover {
        border-color: #3b82f6;
        background-color: #eff6ff;
    }
    QLabel#DropText {
        color: #64748b;
        font-size: 12pt;
    }
    QLabel#StatValue {
        font-size: 22pt;
        font-weight: bold;
        color: #1e293b;
    }
    QLabel#StatLabel {
        color: #64748b;
        font-size: 9pt;
    }
    QListWidget {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-bottom: 1px solid #f1f5f9;
    }
    QListWidget::item:selected {
        background-color: #dbeafe;
        color: #1e40af;
    }
    QProgressBar {
        background-color: #e2e8f0;
        border-radius: 4px;
        text-align: center;
        height: 8px;
    }
    QProgressBar::chunk {
        background-color: #3b82f6;
        border-radius: 4px;
    }
    QTabWidget::pane {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        top: -1px;
        background-color: #ffffff;
    }
    QTabBar::tab {
        background-color: #f1f5f9;
        color: #64748b;
        padding: 8px 20px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #1e293b;
        border: 1px solid #e2e8f0;
        border-bottom-color: #ffffff;
    }
    QCheckBox {
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 3px;
        border: 1px solid #cbd5e1;
        background-color: #ffffff;
    }
    QCheckBox::indicator:checked {
        background-color: #3b82f6;
        border-color: #3b82f6;
    }
    QStatusBar {
        background-color: #ffffff;
        border-top: 1px solid #e2e8f0;
        color: #64748b;
    }
    QToolTip {
        background-color: #1e293b;
        color: #ffffff;
        border: none;
        padding: 6px 10px;
        border-radius: 4px;
    }
    """


class DropZone(QFrame):
    fileDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("📁")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48pt; padding-bottom: 10px;")
        layout.addWidget(icon_label)

        self.text_label = QLabel("将 Excel 或 CSV 文件拖放到此处")
        self.text_label.setObjectName("DropText")
        self.text_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.text_label)

        sub_label = QLabel("支持 .xlsx .xls .csv 格式")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet("color: #94a3b8; font-size: 9pt; padding-top: 5px;")
        layout.addWidget(sub_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.browse_btn = QPushButton("或 点击选择文件")
        self.browse_btn.setObjectName("PrimaryButton")
        btn_row.addWidget(self.browse_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.browse_btn.clicked.connect(self._browse_file)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path:
                self.fileDropped.emit(file_path)
                break

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择价目表文件", "",
            "Excel 文件 (*.xlsx *.xls);;CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if file_path:
            self.fileDropped.emit(file_path)


class StatCard(QFrame):
    def __init__(self, title: str, value: str, color: str = "#3b82f6", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(self.value_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("StatLabel")
        layout.addWidget(self.title_label)

    def update_value(self, value: str):
        self.value_label.setText(value)
