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
        predictions = model.predict(
            source=np.array(image_rgb),
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            verbose=False,
            device="cpu",
        )
    except Exception as exc:
        return LayoutDetectionResult(None, [], [], [f"{orientation} layout detection failed: {exc}"])

    detections = _parse_predictions(predictions)
    name_detection = _pick_best_name_detection(detections)
    if orientation == "vertical":
        code_detections = _prepare_vertical_code_detections(detections)
    else:
        code_detections = _prepare_horizontal_code_detections(detections)

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
            expanded_detection = _expand_horizontal_code_detection(detection, image_rgb.width)
            code_blocks = _recognize_crop(
                image_rgb,
                expanded_detection,
                ocr_engine,
                pad_x=0.0,
                pad_y=0.01,
                input_mode="rgb_array",
            )
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
