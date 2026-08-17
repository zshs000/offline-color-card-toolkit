from __future__ import annotations

import math
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageOps, JpegImagePlugin

from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import OcrEngine
from color_card_toolkit.core.ruler_detection import detect_ruler

DEFAULT_DPI = 300
RULER_DETECTION_MAX_SIZE = 1500
RULER_PROFILE_MIN_CONTRAST = 6.0
RULER_LINE_MIN_CONTRAST = 5.0
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_OUTPUT_PATH_LOCK = threading.Lock()


@dataclass(frozen=True)
class ImageProcessResult:
    source_path: Path
    output_path: Path
    recognized_name: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _RulerCropResult:
    detected: bool
    healthy: bool
    centered: bool


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
        blocks = _recognize_display_image(source, ocr_engine)
        recognized_name = extract_top_left_name(source, blocks)
        if not recognized_name:
            recognized_name = _safe_filename(source.stem) or "未识别"
            warnings.append("左上角名称识别为空，已使用原文件名")

        with _OUTPUT_PATH_LOCK:
            output_path = unique_output_path(folder, recognized_name, source.suffix)
            shutil.copy2(source, output_path)
        results.append(ImageProcessResult(source, output_path, recognized_name, warnings))

    return results


def crop_main_images(
    image_paths: list[str | Path],
    output_dir: str | Path,
    ocr_engine: OcrEngine | None,
    *,
    crop_size_cm: int,
    name_recognizer: Callable[[Path], str] | None = None,
) -> list[ImageProcessResult]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    results: list[ImageProcessResult] = []

    for image_path in image_paths:
        source = Path(image_path)
        warnings: list[str] = []
        if name_recognizer is not None:
            try:
                recognized_name = _safe_filename(name_recognizer(source))
            except Exception as exc:
                recognized_name = ""
                warnings.append(f"云端名称识别失败：{exc}")
        elif ocr_engine is not None:
            blocks = _recognize_display_image(source, ocr_engine)
            recognized_name = extract_top_left_name(source, blocks)
        else:
            recognized_name = ""
        if not recognized_name:
            recognized_name = _safe_filename(source.stem) or "未识别"
            warnings.append("名称识别为空，已使用原文件名")

        with _OUTPUT_PATH_LOCK:
            output_path = unique_output_path(folder, recognized_name, source.suffix)
            crop_result = _crop_image(source, output_path, crop_size_cm)
        if crop_result.detected and not crop_result.healthy:
            warnings.append("标尺刻度检测可靠性偏低，已按检测结果裁剪，请人工核对")
        elif not crop_result.detected and crop_result.centered:
            warnings.append("未检测到上方和左侧标尺，已按原有方式从图片中心裁剪")
        results.append(ImageProcessResult(source, output_path, recognized_name, warnings))

    return results


def rename_processed_image(result: ImageProcessResult, recognized_name: str) -> ImageProcessResult:
    clean_name = _safe_filename(recognized_name)
    if not clean_name:
        raise ValueError("识别名称为空")

    current_path = result.output_path
    desired_path = current_path.with_name(f"{clean_name}{current_path.suffix}")
    with _OUTPUT_PATH_LOCK:
        if desired_path == current_path:
            output_path = current_path
        else:
            output_path = unique_output_path(current_path.parent, clean_name, current_path.suffix)
            current_path.replace(output_path)

    warnings = [
        warning
        for warning in result.warnings
        if not warning.startswith("云端名称识别失败")
        and warning != "名称识别为空，已使用原文件名"
    ]
    return ImageProcessResult(result.source_path, output_path, clean_name, warnings)


def _crop_image(source: Path, output_path: Path, crop_size_cm: int) -> _RulerCropResult:
    with Image.open(source) as image:
        source_format = image.format
        jpeg_save_kwargs = {}
        if (source_format or "").upper() in {"JPEG", "JPG"}:
            quantization = getattr(image, "quantization", None)
            if quantization:
                jpeg_save_kwargs = {
                    "qtables": quantization,
                    "subsampling": JpegImagePlugin.get_sampling(image),
                }
        image = ImageOps.exif_transpose(image)
        dpi_x, dpi_y = _image_dpi(image)
        crop_width = min(_cm_to_pixels(crop_size_cm, dpi_x), image.width)
        crop_height = min(_cm_to_pixels(crop_size_cm, dpi_y), image.height)

        geometry = detect_ruler(
            image,
            (dpi_x, dpi_y),
            span_mm=crop_size_cm * 10,
        )
        if geometry is not None:
            rotated = image.rotate(
                geometry.rotation_degrees,
                resample=Image.Resampling.BICUBIC,
                expand=True,
                fillcolor=(255, 255, 255),
            )
            origin_x, origin_y = _transform_point(
                np.asarray(geometry.origin, dtype=np.float64),
                source_size=image.size,
                target_size=rotated.size,
                angle_degrees=geometry.rotation_degrees,
            )
            crop_box = (
                0,
                0,
                min(rotated.width, round(origin_x + crop_width)),
                min(rotated.height, round(origin_y + crop_height)),
            )
            rotated.crop(crop_box).save(output_path, format=source_format, **jpeg_save_kwargs)
            return _RulerCropResult(
                detected=True,
                healthy=geometry.healthy,
                centered=False,
            )

        ruler_origin = _find_ruler_origin(image)
        if ruler_origin is None:
            left = max(0, (image.width - crop_width) // 2)
            top = max(0, (image.height - crop_height) // 2)
            crop_box = (left, top, left + crop_width, top + crop_height)
            centered = True
        else:
            origin_x, origin_y = ruler_origin
            crop_box = (
                0,
                0,
                min(image.width, origin_x + crop_width),
                min(image.height, origin_y + crop_height),
            )
            centered = False
        image.crop(crop_box).save(output_path, format=source_format, **jpeg_save_kwargs)
        return _RulerCropResult(detected=False, healthy=False, centered=centered)


def _transform_point(
    point: np.ndarray,
    *,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
    angle_degrees: float,
) -> tuple[float, float]:
    """把原图坐标映射到 rotate(angle, expand=True) 之后的坐标系。"""
    angle = math.radians(angle_degrees)
    delta_x = point[0] - source_size[0] / 2
    delta_y = point[1] - source_size[1] / 2
    transformed_x = (
        math.cos(angle) * delta_x + math.sin(angle) * delta_y + target_size[0] / 2
    )
    transformed_y = (
        -math.sin(angle) * delta_x + math.cos(angle) * delta_y + target_size[1] / 2
    )
    return transformed_x, transformed_y



def _find_ruler_origin(image: Image.Image) -> tuple[int, int] | None:
    scale = min(1.0, RULER_DETECTION_MAX_SIZE / max(image.width, image.height))
    analysis_width = max(1, round(image.width * scale))
    analysis_height = max(1, round(image.height * scale))
    analysis = image.convert("L").resize(
        (analysis_width, analysis_height),
        Image.Resampling.BILINEAR,
    )
    gray = np.asarray(analysis, dtype=np.float32)

    x_profile = np.median(
        gray[int(analysis_height * 0.2) : int(analysis_height * 0.75), :],
        axis=0,
    )
    y_profile = np.median(
        gray[:, int(analysis_width * 0.2) : int(analysis_width * 0.85)],
        axis=1,
    )
    x_start, x_end = int(analysis_width * 0.03), int(analysis_width * 0.12)
    y_start, y_end = int(analysis_height * 0.03), int(analysis_height * 0.12)
    if x_end - x_start < 2 or y_end - y_start < 2:
        return None

    x_edges = np.abs(np.diff(x_profile[x_start:x_end]))
    y_edges = np.abs(np.diff(y_profile[y_start:y_end]))
    if x_edges.max(initial=0) < RULER_PROFILE_MIN_CONTRAST:
        return None
    if y_edges.max(initial=0) < RULER_PROFILE_MIN_CONTRAST:
        return None

    horizontal_gradient = np.abs(np.diff(gray, axis=1))
    vertical_gradient = np.abs(np.diff(gray, axis=0))
    origin_x = x_start + int(np.argmax(x_edges)) + 1
    origin_y = y_start + int(np.argmax(y_edges)) + 1
    x_line_strength = horizontal_gradient[
        int(analysis_height * 0.12) : int(analysis_height * 0.90),
        max(0, origin_x - 2) : origin_x + 2,
    ].mean()
    y_line_strength = vertical_gradient[
        max(0, origin_y - 2) : origin_y + 2,
        int(analysis_width * 0.12) : int(analysis_width * 0.90),
    ].mean()
    if x_line_strength < RULER_LINE_MIN_CONTRAST:
        return None
    if y_line_strength < RULER_LINE_MIN_CONTRAST:
        return None

    return (
        round(origin_x / scale),
        round(origin_y / scale),
    )


def _image_size(image_path: Path, blocks: list[OcrBlock]) -> tuple[float, float]:
    try:
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
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


def _recognize_display_image(image_path: Path, ocr_engine: OcrEngine) -> list[OcrBlock]:
    recognize_image_object = getattr(ocr_engine, "recognize_image_object", None)
    if callable(recognize_image_object):
        with Image.open(image_path) as image:
            display_image = ImageOps.exif_transpose(image).convert("RGB")
            return list(recognize_image_object(np.array(display_image)))
    return ocr_engine.recognize(image_path)


def _cm_to_pixels(centimeters: int, dpi: int) -> int:
    return max(1, int(round(centimeters / 2.54 * dpi)))


def _safe_filename(name: str) -> str:
    clean = _INVALID_FILENAME_CHARS.sub("", name.strip())
    clean = re.sub(r"\s+", " ", clean).strip().rstrip(".")
    return clean
