from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

from color_card_toolkit.core.models import Box, OcrBlock
from color_card_toolkit.core.resources import horizontal_layout_model_path, vertical_layout_model_path

LayoutOrientation = Literal["vertical", "horizontal"]

VERTICAL_ASPECT_RATIO_THRESHOLD = 1.2
HORIZONTAL_CODE_FALLBACK_CONFS = (0.1, 0.05, 0.01)
_CLASS_NAMES = {
    "name_area": "name_area",
    "code_area": "code_area",
    "0": "name_area",
    "1": "code_area",
}


@dataclass(frozen=True)
class LayoutDetection:
    label: str
    confidence: float
    box: Box

    @property
    def min_x(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def max_x(self) -> float:
        return max(point[0] for point in self.box)

    @property
    def min_y(self) -> float:
        return min(point[1] for point in self.box)

    @property
    def max_y(self) -> float:
        return max(point[1] for point in self.box)

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass(frozen=True)
class LayoutDetectionResult:
    name_detection: LayoutDetection | None
    code_detections: list[LayoutDetection]
    ocr_blocks: list[OcrBlock]
    warnings: list[str]


def infer_layout_orientation(image_path: str | Path) -> LayoutOrientation:
    path = Path(image_path)
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            ratio = image.width / max(image.height, 1)
    except Exception:
        return "horizontal"
    return "vertical" if ratio < VERTICAL_ASPECT_RATIO_THRESHOLD else "horizontal"


def detect_vertical_layout(
    image_path: str | Path,
    ocr_engine,
    *,
    imgsz: int = 1280,
    conf: float = 0.2,
    iou: float = 0.45,
) -> LayoutDetectionResult | None:
    return _detect_layout(
        image_path,
        ocr_engine,
        model_path=vertical_layout_model_path(),
        orientation="vertical",
        imgsz=imgsz,
        conf=conf,
        iou=iou,
    )


def detect_horizontal_layout(
    image_path: str | Path,
    ocr_engine,
    *,
    imgsz: int = 1280,
    conf: float = 0.2,
    iou: float = 0.45,
) -> LayoutDetectionResult | None:
    return _detect_layout(
        image_path,
        ocr_engine,
        model_path=horizontal_layout_model_path(),
        orientation="horizontal",
        imgsz=imgsz,
        conf=conf,
        iou=iou,
    )


def _detect_layout(
    image_path: str | Path,
    ocr_engine,
    *,
    model_path: Path | None,
    orientation: LayoutOrientation,
    imgsz: int,
    conf: float,
    iou: float,
) -> LayoutDetectionResult | None:
    if model_path is None:
        return None

    try:
        model = _load_model(str(model_path))
    except Exception as exc:
        return LayoutDetectionResult(None, [], [], [f"{orientation} layout model load failed: {exc}"])

    path = Path(image_path)
    try:
        with Image.open(path) as image:
            image_rgb = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        return LayoutDetectionResult(None, [], [], [f"image load failed: {exc}"])

    try:
        detections = _predict_layout_detections(model, image_rgb, imgsz=imgsz, conf=conf, iou=iou)
    except Exception as exc:
        return LayoutDetectionResult(None, [], [], [f"{orientation} layout detection failed: {exc}"])

    name_detection = _pick_best_name_detection(detections)
    if orientation == "vertical":
        code_detections = _prepare_vertical_code_detections(detections)
    else:
        code_detections = _prepare_horizontal_code_detections(detections)
        if not code_detections:
            code_detections = _find_horizontal_code_detections_at_lower_conf(
                model,
                image_rgb,
                imgsz=imgsz,
                current_conf=conf,
                iou=iou,
            )

    if not name_detection and not code_detections:
        return LayoutDetectionResult(None, [], [], [f"{orientation} layout model found no valid regions"])

    ocr_blocks: list[OcrBlock] = []
    warnings: list[str] = []

    if name_detection is not None:
        ocr_blocks.extend(_recognize_crop(image_rgb, name_detection, ocr_engine, pad_x=0.02, pad_y=0.03))

    kept_code_detections: list[LayoutDetection] = []
    for detection in code_detections:
        if orientation == "vertical":
            code_blocks = _recognize_crop(image_rgb, detection, ocr_engine, pad_x=0.012, pad_y=0.01)
            if not _has_effective_code_blocks(code_blocks):
                continue
            kept_code_detections.append(detection)
            ocr_blocks.extend(_normalize_vertical_column_blocks(code_blocks, detection))
        else:
            expanded_detection, code_blocks = _recognize_horizontal_code_detection(image_rgb, detection, ocr_engine)
            if not _has_effective_code_blocks(code_blocks):
                continue
            kept_code_detections.append(expanded_detection)
            ocr_blocks.extend(code_blocks)

    if not kept_code_detections:
        warnings.append(f"{orientation} layout model found no code region with OCR text")

    return LayoutDetectionResult(name_detection, kept_code_detections, ocr_blocks, warnings)


@lru_cache(maxsize=2)
def _load_model(model_path: str):
    from ultralytics import YOLO

    return YOLO(model_path)


def _parse_predictions(predictions) -> list[LayoutDetection]:
    detections: list[LayoutDetection] = []
    if not predictions:
        return detections

    result = predictions[0]
    names = getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections

    for coords, class_id, score in zip(getattr(boxes, "xyxy", []), getattr(boxes, "cls", []), getattr(boxes, "conf", [])):
        x1, y1, x2, y2 = [float(value) for value in coords.tolist()]
        class_index = int(class_id.item() if hasattr(class_id, "item") else class_id)
        label = _CLASS_NAMES.get(str(class_index))
        if label is None and names:
            raw_name = names.get(class_index) if isinstance(names, dict) else None
            if raw_name is None:
                try:
                    raw_name = names[class_index]
                except Exception:
                    raw_name = None
            label = _CLASS_NAMES.get(str(raw_name), str(raw_name) if raw_name else "")
        if label not in {"name_area", "code_area"}:
            continue
        detections.append(
            LayoutDetection(
                label=label,
                confidence=float(score.item() if hasattr(score, "item") else score),
                box=((x1, y1), (x2, y1), (x2, y2), (x1, y2)),
            )
        )
    return detections


def _predict_layout_detections(
    model,
    image: Image.Image,
    *,
    imgsz: int,
    conf: float,
    iou: float,
) -> list[LayoutDetection]:
    predictions = model.predict(
        source=np.array(image),
        imgsz=imgsz,
        conf=conf,
        iou=iou,
        verbose=False,
        device="cpu",
    )
    return _parse_predictions(predictions)


def _find_horizontal_code_detections_at_lower_conf(
    model,
    image: Image.Image,
    *,
    imgsz: int,
    current_conf: float,
    iou: float,
) -> list[LayoutDetection]:
    for fallback_conf in HORIZONTAL_CODE_FALLBACK_CONFS:
        if fallback_conf >= current_conf:
            continue
        detections = _predict_layout_detections(model, image, imgsz=imgsz, conf=fallback_conf, iou=iou)
        code_detections = _prepare_horizontal_code_detections(detections)
        if code_detections:
            return code_detections
    return []


def _pick_best_name_detection(detections: list[LayoutDetection]) -> LayoutDetection | None:
    names = [item for item in detections if item.label == "name_area"]
    if not names:
        return None
    return max(names, key=lambda item: (item.confidence, -item.center_y))


def _prepare_vertical_code_detections(detections: list[LayoutDetection]) -> list[LayoutDetection]:
    codes = [item for item in detections if item.label == "code_area"]
    if not codes:
        return []
    return sorted(_dedupe_code_detections(codes), key=lambda item: item.center_x)


def _prepare_horizontal_code_detections(detections: list[LayoutDetection]) -> list[LayoutDetection]:
    codes = [item for item in detections if item.label == "code_area"]
    if not codes:
        return []
    return sorted(_dedupe_code_detections(codes), key=lambda item: item.confidence, reverse=True)[:1]


def _expand_horizontal_code_detection(detection: LayoutDetection, image_width: int) -> LayoutDetection:
    return LayoutDetection(
        label=detection.label,
        confidence=detection.confidence,
        box=((0.0, detection.min_y), (float(image_width), detection.min_y), (float(image_width), detection.max_y), (0.0, detection.max_y)),
    )


def _recognize_horizontal_code_detection(
    image: Image.Image,
    detection: LayoutDetection,
    ocr_engine,
) -> tuple[LayoutDetection, list[OcrBlock]]:
    expanded_detection = _expand_horizontal_code_detection(detection, image.width)
    code_blocks = _recognize_horizontal_code_crop(image, expanded_detection, ocr_engine, pad_y=0.01)
    if _has_effective_code_blocks(code_blocks):
        return expanded_detection, code_blocks

    best_detection = expanded_detection
    best_blocks = code_blocks
    best_score = _score_horizontal_code_blocks(code_blocks)
    for candidate in _horizontal_code_ocr_fallback_detections(expanded_detection, image.height):
        candidate_blocks = _recognize_horizontal_code_crop(image, candidate, ocr_engine, pad_y=0.0)
        candidate_score = _score_horizontal_code_blocks(candidate_blocks)
        if candidate_score > best_score:
            best_detection = candidate
            best_blocks = candidate_blocks
            best_score = candidate_score

    return best_detection, best_blocks


def _recognize_horizontal_code_crop(
    image: Image.Image,
    detection: LayoutDetection,
    ocr_engine,
    *,
    pad_y: float,
) -> list[OcrBlock]:
    blocks = _recognize_crop(
        image,
        detection,
        ocr_engine,
        pad_x=0.0,
        pad_y=pad_y,
        input_mode="rgb_array",
    )
    return _split_horizontal_merged_code_blocks(image, detection, blocks)


def _horizontal_code_ocr_fallback_detections(
    detection: LayoutDetection,
    image_height: int,
) -> list[LayoutDetection]:
    return [
        _scale_detection_height(detection, image_height, scale)
        for scale in (1.0, 0.86, 0.78, 0.70, 1.30, 1.60, 2.00)
    ]


def _scale_detection_height(
    detection: LayoutDetection,
    image_height: int,
    scale: float,
) -> LayoutDetection:
    center_y = detection.center_y
    half_height = max(10.0, detection.height * scale / 2)
    y1 = max(0.0, center_y - half_height)
    y2 = min(float(image_height), center_y + half_height)
    return LayoutDetection(
        label=detection.label,
        confidence=detection.confidence,
        box=((detection.min_x, y1), (detection.max_x, y1), (detection.max_x, y2), (detection.min_x, y2)),
    )


def _score_horizontal_code_blocks(blocks: list[OcrBlock]) -> tuple[int, int, int, int, float]:
    numbers: list[int] = []
    long_numeric_blocks = 0
    noise_blocks = 0
    confidence_sum = 0.0
    for block in blocks:
        text = str(block.text).strip()
        digits = "".join(char for char in text if char.isdigit())
        if text.isdigit() and len(text) <= 3:
            numbers.append(int(text))
            confidence_sum += block.confidence
        elif len(digits) > 3:
            long_numeric_blocks += 1
        elif text:
            noise_blocks += 1

    if not numbers:
        return (0, 0, 0, -long_numeric_blocks, 0.0)

    unique_numbers = set(numbers)
    missing_count = max(numbers) - min(numbers) + 1 - len(unique_numbers)
    duplicate_count = len(numbers) - len(unique_numbers)
    average_confidence = confidence_sum / len(numbers)
    return (
        len(numbers),
        _longest_incrementing_run(numbers),
        -missing_count,
        -(duplicate_count + long_numeric_blocks + noise_blocks),
        average_confidence,
    )


def _longest_incrementing_run(numbers: list[int]) -> int:
    longest = 1
    current = 1
    for previous, number in zip(numbers, numbers[1:]):
        if number == previous + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def _dedupe_code_detections(detections: list[LayoutDetection]) -> list[LayoutDetection]:
    kept: list[LayoutDetection] = []
    for detection in sorted(detections, key=lambda item: item.confidence, reverse=True):
        if any(_is_duplicate_code_box(detection, existing) for existing in kept):
            continue
        kept.append(detection)
    return kept


def _is_duplicate_code_box(first: LayoutDetection, second: LayoutDetection) -> bool:
    if _intersection_over_union(first.box, second.box) >= 0.72:
        return True
    width_base = max(min(first.width, second.width), 1.0)
    height_base = max(min(first.height, second.height), 1.0)
    close_x = abs(first.center_x - second.center_x) <= width_base * 0.35
    close_y = abs(first.center_y - second.center_y) <= height_base * 0.06
    similar_w = abs(first.width - second.width) <= width_base * 0.35
    similar_h = abs(first.height - second.height) <= height_base * 0.08
    return close_x and close_y and similar_w and similar_h


def _intersection_over_union(first: Box, second: Box) -> float:
    first_x1, first_y1, first_x2, first_y2 = _box_xyxy(first)
    second_x1, second_y1, second_x2, second_y2 = _box_xyxy(second)
    inter_x1 = max(first_x1, second_x1)
    inter_y1 = max(first_y1, second_y1)
    inter_x2 = min(first_x2, second_x2)
    inter_y2 = min(first_y2, second_y2)
    intersection = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    if intersection <= 0:
        return 0.0
    first_area = max(0.0, first_x2 - first_x1) * max(0.0, first_y2 - first_y1)
    second_area = max(0.0, second_x2 - second_x1) * max(0.0, second_y2 - second_y1)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def _box_xyxy(box: Box) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in box),
        min(point[1] for point in box),
        max(point[0] for point in box),
        max(point[1] for point in box),
    )


def _recognize_crop(
    image: Image.Image,
    detection: LayoutDetection,
    ocr_engine,
    *,
    pad_x: float,
    pad_y: float,
    input_mode: Literal["pil", "rgb_array"] = "pil",
) -> list[OcrBlock]:
    crop_result = _crop_with_padding(image, detection, pad_x=pad_x, pad_y=pad_y)
    if crop_result is None:
        return []
    crop, offset = crop_result

    recognizer = getattr(ocr_engine, "recognize_image_object", None)
    try:
        if callable(recognizer):
            ocr_input = np.array(crop) if input_mode == "rgb_array" else crop
            blocks = list(recognizer(ocr_input))
        else:
            blocks = list(ocr_engine.recognize(crop))
    except Exception:
        return []
    return [_offset_block(block, offset) for block in blocks]


def _split_horizontal_merged_code_blocks(
    image: Image.Image,
    detection: LayoutDetection,
    blocks: list[OcrBlock],
) -> list[OcrBlock]:
    crop_result = _crop_with_padding(image, detection, pad_x=0.0, pad_y=0.01)
    if crop_result is None:
        return blocks

    crop, offset = crop_result
    units = _segment_horizontal_code_units(crop)
    if len(units) < 6:
        return blocks

    refined: list[OcrBlock] = []
    changed = False
    for block in blocks:
        digits = "".join(char for char in str(block.text).strip() if char.isdigit())
        if digits != str(block.text).strip() or len(digits) < 2:
            refined.append(block)
            continue

        relative_x1 = block.min_x - offset[0]
        relative_x2 = block.max_x - offset[0]
        covered_units = _units_covered_by_block(units, relative_x1, relative_x2)
        if len(covered_units) <= 1:
            refined.append(block)
            continue

        parts = _split_numeric_text_by_unit_count(digits, len(covered_units))
        split_units = covered_units
        if not parts:
            for candidate_count in (len(covered_units) + 1, len(covered_units) - 1):
                parts = _split_numeric_text_by_unit_count(digits, candidate_count)
                if parts:
                    split_units = _interpolate_horizontal_units(relative_x1, relative_x2, candidate_count)
                    break
        if not parts:
            refined.append(block)
            continue

        changed = True
        for text, unit in zip(parts, split_units):
            refined.append(
                OcrBlock(
                    text=text,
                    confidence=block.confidence,
                    box=_offset_unit_box(unit, offset, y1=block.min_y, y2=block.max_y),
                )
            )

    if not changed:
        return blocks
    return sorted(refined, key=lambda item: (item.center_y, item.center_x))


def _segment_horizontal_code_units(crop: Image.Image) -> list[tuple[float, float, float, float]]:
    try:
        import cv2
    except ImportError:
        return []

    gray = np.array(crop.convert("L"))
    if gray.size == 0:
        return []

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    height, width = mask.shape
    components: list[tuple[int, int, int, int, int]] = []
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    for index in range(1, count):
        x, y, component_width, component_height, area = [int(value) for value in stats[index]]
        if area < max(12, int(width * height * 0.00005)):
            continue
        if component_height < max(8, int(height * 0.15)):
            continue
        if component_width < 2:
            continue
        if x <= 3 or x + component_width >= width - 3:
            continue
        if component_height > height * 0.95 and component_width > width * 0.8:
            continue
        components.append((x, y, x + component_width, y + component_height, area))

    if len(components) < 6:
        return []

    components.sort(key=lambda item: item[0])
    gaps = [
        components[index + 1][0] - components[index][2]
        for index in range(len(components) - 1)
        if components[index + 1][0] > components[index][2]
    ]
    gap_threshold = _horizontal_unit_gap_threshold(gaps, components)

    groups: list[list[tuple[int, int, int, int, int]]] = []
    current = [components[0]]
    for previous, component in zip(components, components[1:]):
        gap = component[0] - previous[2]
        if gap <= gap_threshold:
            current.append(component)
        else:
            groups.append(current)
            current = [component]
    groups.append(current)

    units: list[tuple[float, float, float, float]] = []
    for group in groups:
        x1 = min(item[0] for item in group)
        y1 = min(item[1] for item in group)
        x2 = max(item[2] for item in group)
        y2 = max(item[3] for item in group)
        if x2 - x1 < 4 or y2 - y1 < max(8, height * 0.12):
            continue
        units.append((float(x1), float(y1), float(x2), float(y2)))

    if len(units) < 6:
        return []
    units = _drop_horizontal_unit_width_outliers(units)
    if len(units) < 6:
        return []
    return units


def _horizontal_unit_gap_threshold(
    gaps: list[int],
    components: list[tuple[int, int, int, int, int]],
) -> float:
    positive_gaps = sorted(gap for gap in gaps if gap > 0)
    if len(positive_gaps) >= 4:
        largest_jump = 0
        threshold = float(np.median(positive_gaps))
        for previous, current in zip(positive_gaps, positive_gaps[1:]):
            jump = current - previous
            if jump > largest_jump:
                largest_jump = jump
                threshold = (previous + current) / 2
        return max(8.0, min(threshold, 45.0))

    widths = [item[2] - item[0] for item in components]
    return max(8.0, float(np.median(widths)) * 0.55)


def _drop_horizontal_unit_width_outliers(
    units: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    widths = [unit[2] - unit[0] for unit in units]
    normal_widths = [width for width in widths if 4 <= width <= 160]
    if not normal_widths:
        return units
    median_width = float(np.median(normal_widths))
    max_width = max(120.0, median_width * 3.2)
    return [unit for unit in units if unit[2] - unit[0] <= max_width]


def _units_covered_by_block(
    units: list[tuple[float, float, float, float]],
    x1: float,
    x2: float,
) -> list[tuple[float, float, float, float]]:
    tolerance = max(6.0, (x2 - x1) * 0.02)
    covered = []
    for unit in units:
        center_x = (unit[0] + unit[2]) / 2
        if x1 - tolerance <= center_x <= x2 + tolerance:
            covered.append(unit)
    return covered


def _split_numeric_text_by_unit_count(text: str, unit_count: int) -> list[str]:
    if unit_count <= 1:
        return []
    if len(text) == unit_count:
        parts = list(text)
        if _looks_like_incrementing_parts(parts):
            return parts

    for width in (2, 3):
        if len(text) % width != 0 or len(text) // width != unit_count:
            continue
        parts = [text[index : index + width] for index in range(0, len(text), width)]
        if _looks_like_incrementing_parts(parts):
            return parts

    return _split_incrementing_digits(text, unit_count)


def _interpolate_horizontal_units(
    x1: float,
    x2: float,
    unit_count: int,
) -> list[tuple[float, float, float, float]]:
    if unit_count <= 0 or x2 <= x1:
        return []
    width = (x2 - x1) / unit_count
    return [
        (x1 + index * width, 0.0, x1 + (index + 1) * width, 1.0)
        for index in range(unit_count)
    ]


def _split_incrementing_digits(text: str, unit_count: int) -> list[str]:
    for start in range(1, 100):
        parts = _consume_incrementing_digits(text, start, unit_count)
        if parts and _looks_like_incrementing_parts(parts):
            return parts
    return []


def _consume_incrementing_digits(text: str, start: int, unit_count: int) -> list[str]:
    remaining = text
    expected = start
    parts: list[str] = []
    while remaining and len(parts) < unit_count:
        matched = False
        for skipped in range(0, 13):
            candidate = str(expected + skipped)
            if remaining.startswith(candidate):
                parts.append(candidate)
                remaining = remaining[len(candidate) :]
                expected = int(candidate) + 1
                matched = True
                break
        if not matched:
            return []

    if remaining or len(parts) != unit_count:
        return []
    return parts


def _looks_like_incrementing_parts(parts: list[str]) -> bool:
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        return False
    numbers = [int(part) for part in parts]
    if any(current <= previous for previous, current in zip(numbers, numbers[1:])):
        return False
    span = numbers[-1] - numbers[0] + 1
    return span <= len(numbers) + max(4, int(len(numbers) * 0.35))


def _offset_unit_box(
    unit: tuple[float, float, float, float],
    offset: tuple[float, float],
    *,
    y1: float,
    y2: float,
) -> Box:
    offset_x, offset_y = offset
    _unit_x1, _unit_y1, _unit_x2, _unit_y2 = unit
    x1 = offset_x + _unit_x1
    x2 = offset_x + _unit_x2
    return (
        (x1, y1),
        (x2, y1),
        (x2, y2),
        (x1, y2),
    )


def _crop_with_padding(
    image: Image.Image,
    detection: LayoutDetection,
    *,
    pad_x: float,
    pad_y: float,
) -> tuple[Image.Image, tuple[float, float]] | None:
    width, height = image.size
    x_pad = int(width * pad_x)
    y_pad = int(height * pad_y)
    x1 = max(0, int(detection.min_x) - x_pad)
    y1 = max(0, int(detection.min_y) - y_pad)
    x2 = min(width, int(detection.max_x) + x_pad)
    y2 = min(height, int(detection.max_y) + y_pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return image.crop((x1, y1, x2, y2)), (float(x1), float(y1))


def _normalize_vertical_column_blocks(blocks: list[OcrBlock], detection: LayoutDetection) -> list[OcrBlock]:
    normalized: list[OcrBlock] = []
    for block in blocks:
        normalized.append(
            OcrBlock(
                text=block.text,
                confidence=block.confidence,
                box=_map_block_to_vertical_column_box(block, detection),
            )
        )
    return normalized


def _map_block_to_vertical_column_box(block: OcrBlock, detection: LayoutDetection) -> Box:
    min_x = detection.min_x
    max_x = detection.max_x
    width = max(max_x - min_x, 1.0)
    center_x = (min_x + max_x) / 2
    block_width = min(max(block.width, 1.0), width * 0.8)
    x1 = max(min_x, center_x - block_width / 2)
    x2 = min(max_x, center_x + block_width / 2)
    return ((x1, block.min_y), (x2, block.min_y), (x2, block.max_y), (x1, block.max_y))


def _has_effective_code_blocks(blocks: list[OcrBlock]) -> bool:
    return any(_looks_like_effective_code_text(block.text) for block in blocks)


def _looks_like_effective_code_text(text: str) -> bool:
    normalized = str(text).strip().upper().replace(" ", "")
    normalized = normalized.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"}))
    normalized = "".join(char for char in normalized if char.isalnum())
    if not normalized:
        return False
    if not any(char.isdigit() for char in normalized):
        return False
    return len(normalized) <= 80


def _offset_block(block: OcrBlock, offset: tuple[float, float]) -> OcrBlock:
    offset_x, offset_y = offset
    return OcrBlock(
        text=block.text,
        confidence=block.confidence,
        box=tuple((offset_x + point[0], offset_y + point[1]) for point in block.box),  # type: ignore[return-value]
    )
