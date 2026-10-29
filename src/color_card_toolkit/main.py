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
    if mode == "main-marker":
        import io
        import json
        from PIL import Image
        from color_card_toolkit import __version__
        from color_card_toolkit.core.main_image_marker import marker_exif

        for image_format in ("JPEG", "PNG"):
            output = io.BytesIO()
            Image.new("RGB", (20, 20)).save(output, image_format, exif=marker_exif(5, 10, 2, 3))
            output.seek(0)
            with Image.open(output) as image:
                marker = json.loads(image.getexif().get_ifd(34665)[37510][8:])
            if marker["tool_version"] != __version__:
                raise RuntimeError("图片标记版本与软件版本不一致")
        return 0
    raise ValueError(
        f"Unknown smoke check mode: {mode}. "
        "The old local recognize smoke check was removed with the YOLO runtime."
    )


if __name__ == "__main__":
    raise SystemExit(main())
