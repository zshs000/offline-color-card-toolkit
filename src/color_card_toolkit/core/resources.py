from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    direct = base_path / relative_path
    if direct.exists():
        return direct
    packaged = base_path / "color_card_toolkit" / relative_path
    if packaged.exists():
        return packaged
    return direct


def flat_template_path() -> Path:
    return resource_path("resources/templates/转平贴底纸模板.docx")
