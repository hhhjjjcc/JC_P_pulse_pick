#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
P波脉冲拾取系统主入口
"""

import sys
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    """
    主函数，用于启动应用
    """
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 