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


def spu_label_template_path() -> Path:
    return resource_path("resources/templates/8144-不干胶贴模板.docx")


def vertical_layout_model_path() -> Path | None:
    path = resource_path("resources/models/vertical_code_area_yolov8n_best.pt")
    return path if path.exists() else None


def horizontal_layout_model_path() -> Path | None:
    path = resource_path("resources/models/horizontal_code_area_yolov8n_best.pt")
    return path if path.exists() else None
