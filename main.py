#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
医美价目表批量维护工具
支持离线、批处理、极简操作
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("医美价目管家")
    app.setOrganizationName("MedicalAestheticTools")

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
