from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

from color_card_toolkit.core.models import Box, OcrBlock
from color_card_toolkit.core.resources import vertical_layout_model_path

LayoutOrientation = Literal["vertical", "horizontal"]

VERTICAL_ASPECT_RATIO_THRESHOLD = 1.2
_VERTICAL_CLASS_NAMES = {
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
class VerticalLayoutResult:
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
) -> VerticalLayoutResult | None:
    model_path = vertical_layout_model_path()
    if model_path is None:
        return None

    try:
        model = _load_vertical_model(model_path)
    except Exception as exc:
        return VerticalLayoutResult(
            name_detection=None,
            code_detections=[],
            ocr_blocks=[],
            warnings=[f"竖版版式模型加载失败: {exc}"],
        )

    path = Path(image_path)
    try:
        with Image.open(path) as image:
            image_rgb = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        return VerticalLayoutResult(
            name_detection=None,
            code_detections=[],
            ocr_blocks=[],
            warnings=[f"图片加载失败: {exc}"],
        )

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
        return VerticalLayoutResult(
            name_detection=None,
            code_detections=[],
            ocr_blocks=[],
            warnings=[f"竖版版式检测失败: {exc}"],
        )

    detections = _parse_predictions(predictions)
    name_detection = _pick_best_name_detection(detections)
    code_detections = _prepare_code_detections(detections)
    if not name_detection and not code_detections:
        return VerticalLayoutResult(
            name_detection=None,
            code_detections=[],
            ocr_blocks=[],
            warnings=["竖版版式模型未检测到有效区域"],
        )

    ocr_blocks: list[OcrBlock] = []
    warnings: list[str] = []

    if name_detection is not None:
        name_blocks = _recognize_crop(image_rgb, name_detection, ocr_engine, pad_x=0.02, pad_y=0.015)
        ocr_blocks.extend(name_blocks)

    kept_code_detections: list[LayoutDetection] = []
    for detection in code_detections:
        code_blocks = _recognize_crop(image_rgb, detection, ocr_engine, pad_x=0.012, pad_y=0.01)
        if not _has_effective_code_blocks(code_blocks):
            continue
        kept_code_detections.append(detection)
        ocr_blocks.extend(_normalize_column_blocks(code_blocks, detection))

    if not kept_code_detections:
        warnings.append("竖版版式模型未检测到数字区域")

    return VerticalLayoutResult(
        name_detection=name_detection,
        code_detections=kept_code_detections,
        ocr_blocks=ocr_blocks,
        warnings=warnings,
    )


@lru_cache(maxsize=1)
def _load_vertical_model(model_path: Path):
    from ultralytics import YOLO

    return YOLO(str(model_path))


def _parse_predictions(predictions) -> list[LayoutDetection]:
    detections: list[LayoutDetection] = []
    if not predictions:
        return detections

    result = predictions[0]
    names = getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections

    xyxy = getattr(boxes, "xyxy", [])
    cls = getattr(boxes, "cls", [])
    conf = getattr(boxes, "conf", [])

    for coords, class_id, score in zip(xyxy, cls, conf):
        x1, y1, x2, y2 = [float(value) for value in coords.tolist()]
        label_key = str(int(class_id.item() if hasattr(class_id, "item") else class_id))
        label = _VERTICAL_CLASS_NAMES.get(label_key)
        if label is None and names:
            raw_name = names.get(int(label_key)) if isinstance(names, dict) else None
            if raw_name is None:
                try:
                    raw_name = names[int(label_key)]
                except Exception:
                    raw_name = None
            label = _VERTICAL_CLASS_NAMES.get(str(raw_name), str(raw_name) if raw_name else "")
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


def _prepare_code_detections(detections: list[LayoutDetection]) -> list[LayoutDetection]:
    codes = [item for item in detections if item.label == "code_area"]
    if not codes:
        return []
    deduped = _dedupe_code_detections(codes)
    return sorted(deduped, key=lambda item: item.center_x)


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
    first_x1 = min(point[0] for point in first)
    first_y1 = min(point[1] for point in first)
    first_x2 = max(point[0] for point in first)
    first_y2 = max(point[1] for point in first)
    second_x1 = min(point[0] for point in second)
    second_y1 = min(point[1] for point in second)
    second_x2 = max(point[0] for point in second)
    second_y2 = max(point[1] for point in second)

    inter_x1 = max(first_x1, second_x1)
    inter_y1 = max(first_y1, second_y1)
    inter_x2 = min(first_x2, second_x2)
    inter_y2 = min(first_y2, second_y2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h
    if intersection <= 0:
        return 0.0

    first_area = max(0.0, first_x2 - first_x1) * max(0.0, first_y2 - first_y1)
    second_area = max(0.0, second_x2 - second_x1) * max(0.0, second_y2 - second_y1)
    union = first_area + second_area - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _recognize_crop(
    image: Image.Image,
    detection: LayoutDetection,
    ocr_engine,
    *,
    pad_x: float,
    pad_y: float,
) -> list[OcrBlock]:
    crop = _crop_with_padding(image, detection, pad_x=pad_x, pad_y=pad_y)
    if crop is None:
        return []

    recognizer = getattr(ocr_engine, "recognize_image_object", None)
    try:
        if callable(recognizer):
            return list(recognizer(crop))
        return list(ocr_engine.recognize(crop))
    except Exception:
        return []


def _crop_with_padding(
    image: Image.Image,
    detection: LayoutDetection,
    *,
    pad_x: float,
    pad_y: float,
) -> Image.Image | None:
    width, height = image.size
    x_pad = int(width * pad_x)
    y_pad = int(height * pad_y)
    x1 = max(0, int(detection.min_x) - x_pad)
    y1 = max(0, int(detection.min_y) - y_pad)
    x2 = min(width, int(detection.max_x) + x_pad)
    y2 = min(height, int(detection.max_y) + y_pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return image.crop((x1, y1, x2, y2))


def _normalize_column_blocks(blocks: list[OcrBlock], detection: LayoutDetection) -> list[OcrBlock]:
    normalized: list[OcrBlock] = []
    for block in blocks:
        normalized.append(
            OcrBlock(
                text=block.text,
                confidence=block.confidence,
                box=_map_block_to_column_box(block, detection),
            )
        )
    return normalized


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
    return len(normalized) <= 4


def _map_block_to_column_box(block: OcrBlock, detection: LayoutDetection) -> Box:
    min_x = detection.min_x
    max_x = detection.max_x
    width = max(max_x - min_x, 1.0)
    center_x = (min_x + max_x) / 2
    block_min_y = block.min_y + detection.min_y
    block_max_y = block.max_y + detection.min_y
    block_width = min(max(block.width, 1.0), width * 0.8)
    x1 = max(min_x, center_x - block_width / 2)
    x2 = min(max_x, center_x + block_width / 2)
    return ((x1, block_min_y), (x2, block_min_y), (x2, block_max_y), (x1, block_max_y))
