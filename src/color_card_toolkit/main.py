from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from color_card_toolkit.core.ocr_engine import RapidOcrEngine
from color_card_toolkit.core.resources import flat_template_path
from color_card_toolkit.ui.main_window import MainWindow


def main() -> int:
    smoke_result = _run_smoke_check()
    if smoke_result is not None:
        return smoke_result

    app = QApplication(sys.argv)
    app.setApplicationName("线下色卡采集工具集")
    window = MainWindow()
    window.show()
    return app.exec()


def _run_smoke_check() -> int | None:
    mode = os.environ.get("COLOR_CARD_TOOLKIT_SMOKE", "").strip().lower()
    if not mode:
        return None
    if mode == "ocr":
        RapidOcrEngine()
        return 0
    if mode == "template":
        if not flat_template_path().exists():
            raise FileNotFoundError(flat_template_path())
        return 0
    raise ValueError(f"Unknown smoke check mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
