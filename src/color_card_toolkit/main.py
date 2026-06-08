from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from color_card_toolkit.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("线下色卡采集工具集")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

