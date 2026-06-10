from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import OcrEngine

DEFAULT_DPI = 300
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ImageProcessResult:
    source_path: Path
    output_path: Path
    recognized_name: str
    warnings: list[str] = field(default_factory=list)


def extract_top_left_name(image_path: str | Path, blocks: list[OcrBlock]) -> str:
    path = Path(image_path)
    width, height = _image_size(path, blocks)
    candidates = [
        block
        for block in blocks
        if block.center_x <= width * 0.45
        and block.center_y <= height * 0.25
        and block.text.strip()
        and len(block.text.strip()) <= 48
    ]
    if not candidates:
        return ""

    top_center_y = min(block.center_y for block in candidates)
    if top_center_y > height * 0.18:
        return ""

    min_text_height = min(max(block.height, 1.0) for block in candidates)
    row_tolerance = max(8.0, height * 0.01, min_text_height * 1.2)
    top_line_blocks = [
        block
        for block in candidates
        if block.center_y <= top_center_y + row_tolerance
    ]
    ordered = sorted(top_line_blocks, key=lambda block: (block.center_y, block.center_x))
    return _safe_filename(" ".join(block.text.strip() for block in ordered if block.text.strip()))


def unique_output_path(output_dir: str | Path, base_name: str, suffix: str) -> Path:
    folder = Path(output_dir)
    clean_base = _safe_filename(base_name) or "未识别"
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    candidate = folder / f"{clean_base}{extension}"
    index = 2
    while candidate.exists():
        candidate = folder / f"{clean_base}-{index}{extension}"
        index += 1
    return candidate


def rename_scan_images(
    image_paths: list[str | Path],
    output_dir: str | Path,
    ocr_engine: OcrEngine,
) -> list[ImageProcessResult]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    results: list[ImageProcessResult] = []

    for image_path in image_paths:
        source = Path(image_path)
        warnings: list[str] = []
        blocks = ocr_engine.recognize(source)
        recognized_name = extract_top_left_name(source, blocks)
        if not recognized_name:
            recognized_name = _safe_filename(source.stem) or "未识别"
            warnings.append("左上角名称识别为空，已使用原文件名")

        output_path = unique_output_path(folder, recognized_name, source.suffix)
        shutil.copy2(source, output_path)
        results.append(ImageProcessResult(source, output_path, recognized_name, warnings))

    return results


def crop_main_images(
    image_paths: list[str | Path],
    output_dir: str | Path,
    ocr_engine: OcrEngine,
    *,
    crop_size_cm: int,
) -> list[ImageProcessResult]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    results: list[ImageProcessResult] = []

    for image_path in image_paths:
        source = Path(image_path)
        warnings: list[str] = []
        blocks = ocr_engine.recognize(source)
        name_block = _top_left_name_block(source, blocks)
        recognized_name = extract_top_left_name(source, blocks)
        if not recognized_name:
            recognized_name = _safe_filename(source.stem) or "未识别"
            warnings.append("左上角名称识别为空，已使用原文件名")

        output_path = unique_output_path(folder, recognized_name, source.suffix)
        _crop_image(source, output_path, name_block, crop_size_cm)
        results.append(ImageProcessResult(source, output_path, recognized_name, warnings))

    return results


def _crop_image(source: Path, output_path: Path, anchor: OcrBlock | None, crop_size_cm: int) -> None:
    with Image.open(source) as image:
        dpi_x, dpi_y = _image_dpi(image)
        crop_width = min(_cm_to_pixels(crop_size_cm, dpi_x), image.width)
        crop_height = min(_cm_to_pixels(crop_size_cm, dpi_y), image.height)
        left = int(anchor.min_x) if anchor else 0
        top = int(anchor.min_y) if anchor else 0
        left = max(0, min(left, image.width - crop_width))
        top = max(0, min(top, image.height - crop_height))
        cropped = image.crop((left, top, left + crop_width, top + crop_height))

        save_kwargs = {}
        if (image.format or "").upper() in {"JPEG", "JPG"}:
            save_kwargs = {"quality": 100, "subsampling": 0}
        cropped.save(output_path, format=image.format, **save_kwargs)


def _top_left_name_block(image_path: Path, blocks: list[OcrBlock]) -> OcrBlock | None:
    width, height = _image_size(image_path, blocks)
    candidates = [
        block
        for block in blocks
        if block.center_x <= width * 0.45
        and block.center_y <= height * 0.25
        and block.text.strip()
        and len(block.text.strip()) <= 48
    ]
    if not candidates:
        return None
    top_center_y = min(block.center_y for block in candidates)
    if top_center_y > height * 0.18:
        return None
    return min(candidates, key=lambda block: (block.center_y, block.center_x))


def _image_size(image_path: Path, blocks: list[OcrBlock]) -> tuple[float, float]:
    try:
        with Image.open(image_path) as image:
            return float(image.width), float(image.height)
    except Exception:
        if not blocks:
            return 1.0, 1.0
        return (
            max(block.max_x for block in blocks) or 1.0,
            max(block.max_y for block in blocks) or 1.0,
        )


def _image_dpi(image: Image.Image) -> tuple[int, int]:
    raw_dpi = image.info.get("dpi")
    if isinstance(raw_dpi, tuple) and len(raw_dpi) >= 2:
        try:
            dpi_x = int(round(float(raw_dpi[0])))
            dpi_y = int(round(float(raw_dpi[1])))
            if dpi_x > 0 and dpi_y > 0:
                return dpi_x, dpi_y
        except (TypeError, ValueError):
            pass
    return DEFAULT_DPI, DEFAULT_DPI


def _cm_to_pixels(centimeters: int, dpi: int) -> int:
    return max(1, int(round(centimeters / 2.54 * dpi)))


def _safe_filename(name: str) -> str:
    clean = _INVALID_FILENAME_CHARS.sub("", name.strip())
    clean = re.sub(r"\s+", " ", clean).strip().rstrip(".")
    return clean
