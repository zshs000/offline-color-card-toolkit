from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from color_card_toolkit.ui.main_image_preview import MainImagePreviewServer


def test_main_image_preview_renders_size_and_original_comparison() -> None:
    app = QApplication.instance() or QApplication([])
    source = Path("/tmp/original.jpg")
    crop = Path("/tmp/crop.jpg")
    server = MainImagePreviewServer(
        [
            {
                "id": "1",
                "source_name": "原图-标签完整名称.jpg",
                "source_path": str(source),
                "preview_path": str(crop),
                "recognized_name": "识别名称",
            }
        ],
        crop_size_cm=15,
    )
    try:
        page = server._render_html()
    finally:
        server.close()
        app.processEvents()

    assert "裁剪尺寸：15 × 15 cm" in page
    assert "完整原图 · 核对名称标签" in page
    assert "/original/1" in page
    assert "点击查看原图与裁剪图" in page
    assert "上一张" in page and "下一张" in page
    assert "识别名称" in page
