from __future__ import annotations

from pathlib import Path

from PIL import Image

from color_card_toolkit.core.color_code_parser import parse_color_codes
from color_card_toolkit.core.grouping import parse_group_name
from color_card_toolkit.core.models import ImageRecognitionResult, OcrBlock
from color_card_toolkit.core.ocr_engine import OcrEngine


def recognize_image(image_path: str | Path, ocr_engine: OcrEngine) -> ImageRecognitionResult:
    path = Path(image_path)
    blocks = ocr_engine.recognize(path)
    raw_name = extract_group_name(path, blocks)
    group = parse_group_name(raw_name)
    parsed_codes = parse_color_codes(blocks)
    warnings = list(parsed_codes.warnings)
    if not raw_name:
        warnings.append("左上角组名识别为空，请手动填写")
    confidence = min((block.confidence for block in blocks), default=0.0)
    return ImageRecognitionResult(
        image_path=path,
        raw_name=raw_name,
        base_name=group.base_name,
        sequence=group.sequence,
        color_codes=parsed_codes.codes,
        explicit_sequence=group.explicit_sequence,
        missing_codes=parsed_codes.missing_codes,
        warnings=warnings,
        confidence=confidence,
    )


def extract_group_name(image_path: Path, blocks: list[OcrBlock]) -> str:
    width, height = _image_size(image_path, blocks)
    left_top_blocks = [
        block
        for block in blocks
        if block.center_x <= width * 0.35 and block.center_y <= height * 0.22
    ]
    left_top_blocks = [
        block
        for block in left_top_blocks
        if len(block.text.strip()) <= 24 and not block.text.strip().isdigit()
    ]
    if not left_top_blocks:
        return ""
    ordered = sorted(left_top_blocks, key=lambda block: (block.center_y, block.center_x))
    return " ".join(block.text.strip() for block in ordered if block.text.strip()).strip()


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

