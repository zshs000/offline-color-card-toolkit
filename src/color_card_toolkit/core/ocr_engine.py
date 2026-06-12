from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from color_card_toolkit.core.models import Box, OcrBlock


class OcrEngine(Protocol):
    def recognize(self, image_path: str | Path) -> list[OcrBlock]:
        ...


class RapidOcrEngine:
    def __init__(self) -> None:
        self._engine = self._create_engine()

    def recognize(self, image_path: str | Path) -> list[OcrBlock]:
        raw_result = self._call_engine(str(image_path), return_word_box=False)
        records = self._extract_records(raw_result)
        blocks: list[OcrBlock] = []
        for record in records:
            parsed = self._parse_record(record)
            if parsed:
                blocks.append(parsed)
        return blocks

    def recognize_color_code_strips(self, image_path: str | Path) -> list[OcrBlock]:
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            return []

        width, height = image.size
        y2_ratio = 0.985
        strip_sets = (
            ((0.02, 0.22, 0.12, 1.8), (0.07, 0.14, 0.16, 2.0)),
            ((0.84, 0.98, 0.12, 1.8), (0.84, 0.98, 0.16, 2.0)),
        )

        blocks: list[OcrBlock] = []
        for strip_configs in strip_sets:
            side_blocks: list[OcrBlock] = []
            for x1_ratio, x2_ratio, y1_ratio, contrast in strip_configs:
                x1 = int(width * x1_ratio)
                x2 = int(width * x2_ratio)
                y1 = int(height * y1_ratio)
                y2 = int(height * y2_ratio)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = image.crop((x1, y1, x2, y2))
                scale = 3.0
                prepared = _prepare_color_code_crop(crop, int(scale), contrast)
                raw_result = self._call_engine(prepared, return_word_box=True)
                for record in self._extract_records(raw_result):
                    row_blocks = _blocks_from_word_boxes(record, offset=(x1, y1), scale=scale)
                    if row_blocks:
                        side_blocks.extend(row_blocks)
                        continue
                    parsed = self._parse_record(record)
                    if parsed:
                        side_blocks.append(_map_block(parsed, offset=(x1, y1), scale=scale))
            blocks.extend(_merge_strip_variant_blocks(side_blocks))

        horizontal_variants: list[list[OcrBlock]] = []
        horizontal_configs = (
            (0.01, 0.99, 0.34, 0.47, 3.0, 1.8),
            (0.01, 0.99, 0.35, 0.45, 4.0, 2.0),
            (0.01, 0.99, 0.32, 0.50, 3.0, 2.0),
        )
        for x1_ratio, x2_ratio, y1_ratio, y2_ratio, scale, contrast in horizontal_configs:
            x1 = int(width * x1_ratio)
            x2 = int(width * x2_ratio)
            y1 = int(height * y1_ratio)
            y2 = int(height * y2_ratio)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = image.crop((x1, y1, x2, y2))
            prepared = _prepare_color_code_crop(crop, int(scale), contrast)
            crop_blocks: list[OcrBlock] = []
            raw_result = self._call_engine(prepared, return_word_box=True)
            for record in self._extract_records(raw_result):
                row_blocks = _blocks_from_word_boxes(record, offset=(x1, y1), scale=scale)
                if row_blocks:
                    crop_blocks.extend(row_blocks)
                    continue
                parsed = self._parse_record(record)
                if parsed:
                    crop_blocks.append(_map_block(parsed, offset=(x1, y1), scale=scale))
            horizontal_blocks = _merge_horizontal_variant_blocks(crop_blocks)
            if horizontal_blocks:
                horizontal_variants.append(horizontal_blocks)

        return _select_supplemental_blocks(blocks, horizontal_variants)

    def _call_engine(self, image, return_word_box: bool):
        if return_word_box:
            try:
                return self._engine(image, return_word_box=True)
            except TypeError:
                return self._engine(image)
        return self._engine(image)

    @staticmethod
    def _create_engine():
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    "未安装 RapidOCR。请先执行：python -m pip install rapidocr-onnxruntime"
                ) from exc
        return RapidOCR()

    @staticmethod
    def _extract_records(raw_result):
        if raw_result is None:
            return []
        if isinstance(raw_result, tuple):
            return raw_result[0] or []
        if hasattr(raw_result, "boxes") and hasattr(raw_result, "txts") and hasattr(raw_result, "scores"):
            return zip(raw_result.boxes, raw_result.txts, raw_result.scores)
        return raw_result or []

    @staticmethod
    def _parse_record(record) -> OcrBlock | None:
        if record is None:
            return None
        try:
            if len(record) >= 3 and isinstance(record[1], str):
                box, text, confidence = record[0], record[1], float(record[2])
            elif len(record) >= 3:
                box, text, confidence = record[0], str(record[1]), float(record[2])
            else:
                return None
            return OcrBlock(text=text, confidence=confidence, box=_normalize_box(box))
        except (TypeError, ValueError, IndexError):
            return None


class FakeOcrEngine:
    def __init__(self, blocks_by_path: dict[str, list[OcrBlock]]) -> None:
        self._blocks_by_path = blocks_by_path

    def recognize(self, image_path: str | Path) -> list[OcrBlock]:
        return list(self._blocks_by_path.get(str(image_path), []))


def _normalize_box(raw_box) -> Box:
    points = []
    for point in raw_box:
        points.append((float(point[0]), float(point[1])))
    if len(points) != 4:
        raise ValueError("OCR box must contain four points")
    return (points[0], points[1], points[2], points[3])


def _prepare_color_code_crop(crop: Image.Image, scale: int, contrast: float) -> np.ndarray:
    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    resized = gray.resize((max(1, gray.width * scale), max(1, gray.height * scale)), resampling)
    return np.array(resized)


def _blocks_from_word_boxes(record, offset: tuple[float, float], scale: float) -> list[OcrBlock]:
    try:
        if len(record) < 6:
            return []
        char_boxes = record[3] or []
        chars = record[4] or []
        scores = record[5] or []
        confidence = float(record[2])
    except (TypeError, ValueError, IndexError):
        return []
    if not char_boxes or not chars or len(char_boxes) != len(chars):
        return []

    items = []
    for index, (char, box) in enumerate(zip(chars, char_boxes)):
        text = str(char).strip()
        if not text:
            continue
        mapped_box = _map_box(_normalize_box(box), offset=offset, scale=scale)
        score = confidence
        if index < len(scores):
            try:
                score = float(scores[index])
            except (TypeError, ValueError):
                score = confidence
        items.append((index, text, score, mapped_box))
    if not items:
        return []

    heights = [max(_box_height(item[3]), 1.0) for item in items]
    tolerance = max(8.0, float(np.median(heights)) * 1.4)
    items.sort(key=lambda item: _box_center_y(item[3]))

    rows: list[list[tuple[int, str, float, Box]]] = []
    for item in items:
        if not rows:
            rows.append([item])
            continue
        current_y = sum(_box_center_y(row_item[3]) for row_item in rows[-1]) / len(rows[-1])
        if abs(_box_center_y(item[3]) - current_y) <= tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])

    blocks: list[OcrBlock] = []
    for row in rows:
        row = sorted(row, key=lambda item: item[0])
        text = "".join(item[1] for item in row).strip()
        if not text:
            continue
        row_confidence = sum(item[2] for item in row) / len(row)
        blocks.append(OcrBlock(text=text, confidence=row_confidence, box=_union_boxes([item[3] for item in row])))
    return blocks


def _map_block(block: OcrBlock, offset: tuple[float, float], scale: float) -> OcrBlock:
    return OcrBlock(text=block.text, confidence=block.confidence, box=_map_box(block.box, offset, scale))


def _map_box(box: Box, offset: tuple[float, float], scale: float) -> Box:
    offset_x, offset_y = offset
    return tuple((offset_x + point[0] / scale, offset_y + point[1] / scale) for point in box)  # type: ignore[return-value]


def _union_boxes(boxes: list[Box]) -> Box:
    min_x = min(point[0] for box in boxes for point in box)
    max_x = max(point[0] for box in boxes for point in box)
    min_y = min(point[1] for box in boxes for point in box)
    max_y = max(point[1] for box in boxes for point in box)
    return ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))


def _box_center_y(box: Box) -> float:
    return (min(point[1] for point in box) + max(point[1] for point in box)) / 2


def _box_height(box: Box) -> float:
    return max(point[1] for point in box) - min(point[1] for point in box)


def _merge_strip_variant_blocks(blocks: list[OcrBlock]) -> list[OcrBlock]:
    candidates = [_clean_strip_block(block) for block in blocks if _looks_like_strip_code(block.text)]
    if not candidates:
        return []

    normal_heights = [block.height for block in candidates if 6 <= block.height <= 50]
    median_height = float(np.median(normal_heights)) if normal_heights else 20.0
    candidates = [
        block
        for block in candidates
        if not (_looks_like_merged_noise(block, median_height) and _has_normal_overlap(block, candidates, median_height))
    ]

    tolerance = max(10.0, median_height * 0.8)
    rows: list[list[OcrBlock]] = []
    for block in sorted(candidates, key=lambda item: item.center_y):
        matching_row = None
        for row in rows:
            row_center = sum(item.center_y for item in row) / len(row)
            if abs(block.center_y - row_center) <= tolerance:
                matching_row = row
                break
        if matching_row is None:
            rows.append([block])
        else:
            matching_row.append(block)

    return [_best_strip_row_block(row, median_height) for row in rows]


def _clean_strip_block(block: OcrBlock) -> OcrBlock:
    text = _normalize_strip_text(block.text)
    return OcrBlock(text=text, confidence=block.confidence, box=block.box)


def _normalize_strip_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text).strip().upper())
    if re.search(r"\d", normalized):
        normalized = normalized.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"}))
    return re.sub(r"[^0-9A-Z]", "", normalized)


def _looks_like_strip_code(text: str) -> bool:
    normalized = _normalize_strip_text(text)
    if not normalized:
        return False
    return bool(re.fullmatch(r"[A-Z]{0,2}\d{1,3}[A-Z]{0,2}|\d{1,3}", normalized))


def _looks_like_merged_noise(block: OcrBlock, median_height: float) -> bool:
    text = _normalize_strip_text(block.text)
    if not text.isdigit():
        return False
    return block.height > median_height * 1.9 and len(text) >= 2


def _has_normal_overlap(block: OcrBlock, blocks: list[OcrBlock], median_height: float) -> bool:
    for other in blocks:
        if other is block:
            continue
        if other.height > median_height * 1.5:
            continue
        if _vertical_overlap(block, other) >= min(other.height, median_height) * 0.55:
            return True
    return False


def _vertical_overlap(first: OcrBlock, second: OcrBlock) -> float:
    return max(0.0, min(first.max_y, second.max_y) - max(first.min_y, second.min_y))


def _best_strip_row_block(row: list[OcrBlock], median_height: float) -> OcrBlock:
    return max(row, key=lambda block: _strip_row_score(block, median_height))


def _strip_row_score(block: OcrBlock, median_height: float) -> tuple[float, float, float]:
    text = _normalize_strip_text(block.text)
    score = block.confidence
    if re.search(r"[A-Z]", text):
        score += 0.45
    if block.height > median_height * 1.6:
        score -= 0.35
    if text.isdigit() and len(text) > 2:
        score -= 0.2
    return (score, -abs(block.height - median_height), -len(text))


def _merge_horizontal_variant_blocks(blocks: list[OcrBlock]) -> list[OcrBlock]:
    candidates = [_clean_horizontal_block(block) for block in blocks if _looks_like_horizontal_code(block.text)]
    if not candidates:
        return []

    heights = [max(block.height, 1.0) for block in candidates]
    tolerance = max(12.0, float(np.median(heights)) * 1.2)
    rows: list[list[OcrBlock]] = []
    for block in sorted(candidates, key=lambda item: item.center_y):
        matching_row = None
        for row in rows:
            row_center = sum(item.center_y for item in row) / len(row)
            if abs(block.center_y - row_center) <= tolerance:
                matching_row = row
                break
        if matching_row is None:
            rows.append([block])
        else:
            matching_row.append(block)

    best_row = max(rows, key=_horizontal_variant_score)
    if _horizontal_variant_unit_count(best_row) < 6:
        return []
    return sorted(best_row, key=lambda block: block.center_x)


def _select_supplemental_blocks(
    side_blocks: list[OcrBlock], horizontal_variants: list[list[OcrBlock]]
) -> list[OcrBlock]:
    if not horizontal_variants:
        return side_blocks
    best_horizontal = max(horizontal_variants, key=_horizontal_variant_score)
    if _horizontal_variant_unit_count(best_horizontal) >= 8:
        return best_horizontal
    return side_blocks + best_horizontal


def _clean_horizontal_block(block: OcrBlock) -> OcrBlock:
    return OcrBlock(text=_normalize_horizontal_text(block.text), confidence=block.confidence, box=block.box)


def _looks_like_horizontal_code(text: str) -> bool:
    normalized = _normalize_horizontal_text(text)
    return bool(normalized and normalized.isdigit() and len(normalized) <= 80)


def _normalize_horizontal_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", str(text).strip().upper())
    if re.search(r"\d", normalized):
        normalized = normalized.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"}))
    if re.search(r"[A-Z\u4e00-\u9fff]", normalized):
        return ""
    return re.sub(r"\D", "", normalized)


def _horizontal_variant_score(blocks: list[OcrBlock]) -> tuple[int, int, float, float]:
    if not blocks:
        return (0, 0, 0.0, 0.0)
    confidence = sum(block.confidence for block in blocks) / len(blocks)
    span = max(block.max_x for block in blocks) - min(block.min_x for block in blocks)
    return (_horizontal_variant_unit_count(blocks), len(blocks), span, confidence)


def _horizontal_variant_unit_count(blocks: list[OcrBlock]) -> int:
    count = 0
    for block in blocks:
        text = _normalize_horizontal_text(block.text)
        if not text.isdigit():
            continue
        if len(text) <= 3:
            count += 1
        else:
            count += max(1, len(text) // 2)
    return count
