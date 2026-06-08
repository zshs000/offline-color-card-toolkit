from __future__ import annotations

from pathlib import Path
from typing import Protocol

from color_card_toolkit.core.models import Box, OcrBlock


class OcrEngine(Protocol):
    def recognize(self, image_path: str | Path) -> list[OcrBlock]:
        ...


class RapidOcrEngine:
    def __init__(self) -> None:
        self._engine = self._create_engine()

    def recognize(self, image_path: str | Path) -> list[OcrBlock]:
        raw_result = self._engine(str(image_path))
        records = self._extract_records(raw_result)
        blocks: list[OcrBlock] = []
        for record in records:
            parsed = self._parse_record(record)
            if parsed:
                blocks.append(parsed)
        return blocks

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

