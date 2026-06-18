from __future__ import annotations

from pathlib import Path

from PIL import Image

from color_card_toolkit.core.color_code_parser import parse_color_codes
from color_card_toolkit.core.grouping import parse_group_name
from color_card_toolkit.core.layout_detection import detect_vertical_layout, infer_layout_orientation
from color_card_toolkit.core.models import ImageRecognitionResult, OcrBlock
from color_card_toolkit.core.ocr_engine import OcrEngine

GROUP_NAME_TOP_BAND_RATIO = 0.14


def recognize_image(image_path: str | Path, ocr_engine: OcrEngine) -> ImageRecognitionResult:
    path = Path(image_path)
    orientation = infer_layout_orientation(path)
    if orientation == "vertical":
        return _recognize_vertical_with_layout_model(path, ocr_engine)
    return _recognize_horizontal_with_ocr(path, ocr_engine)


def _recognize_vertical_with_layout_model(image_path: Path, ocr_engine: OcrEngine) -> ImageRecognitionResult:
    layout_result = detect_vertical_layout(image_path, ocr_engine)
    if layout_result is None:
        return _recognize_horizontal_with_ocr(image_path, ocr_engine)

    if layout_result.ocr_blocks:
        blocks = layout_result.ocr_blocks
        raw_name = extract_group_name(image_path, blocks)
        group = parse_group_name(raw_name)
        parsed_codes = parse_color_codes(blocks)
        warnings = list(parsed_codes.warnings)
        warnings.extend(layout_result.warnings)
        if not raw_name:
            warnings.append("左上角组名识别为空，请手动确认")
        confidence = min((block.confidence for block in blocks), default=0.0)
        return ImageRecognitionResult(
            image_path=image_path,
            raw_name=raw_name,
            base_name=group.base_name,
            sequence=group.sequence,
            color_codes=parsed_codes.codes,
            explicit_sequence=group.explicit_sequence,
            missing_codes=parsed_codes.missing_codes,
            warnings=warnings,
            confidence=confidence,
        )

    horizontal_result = _recognize_horizontal_with_ocr(image_path, ocr_engine)
    warnings = list(horizontal_result.warnings)
    warnings.extend(layout_result.warnings)
    return ImageRecognitionResult(
        image_path=horizontal_result.image_path,
        raw_name=horizontal_result.raw_name,
        base_name=horizontal_result.base_name,
        sequence=horizontal_result.sequence,
        color_codes=horizontal_result.color_codes,
        explicit_sequence=horizontal_result.explicit_sequence,
        participate=horizontal_result.participate,
        missing_codes=horizontal_result.missing_codes,
        warnings=warnings,
        confidence=horizontal_result.confidence,
    )


def _recognize_horizontal_with_ocr(image_path: Path, ocr_engine: OcrEngine) -> ImageRecognitionResult:
    blocks = ocr_engine.recognize(image_path)
    raw_name = extract_group_name(image_path, blocks)
    group = parse_group_name(raw_name)
    parsed_codes = parse_color_codes(blocks)
    strip_blocks = _recognize_color_code_strips(image_path, ocr_engine)
    if strip_blocks:
        strip_codes = parse_color_codes(strip_blocks)
        if _should_prefer_strip_codes(strip_codes, parsed_codes):
            parsed_codes = strip_codes
    warnings = list(parsed_codes.warnings)
    if not raw_name:
        warnings.append("左上角组名识别为空，请手动确认")
    confidence = min((block.confidence for block in blocks), default=0.0)
    return ImageRecognitionResult(
        image_path=image_path,
        raw_name=raw_name,
        base_name=group.base_name,
        sequence=group.sequence,
        color_codes=parsed_codes.codes,
        explicit_sequence=group.explicit_sequence,
        missing_codes=parsed_codes.missing_codes,
        warnings=warnings,
        confidence=confidence,
    )


def _recognize_color_code_strips(image_path: Path, ocr_engine: OcrEngine) -> list[OcrBlock]:
    recognizer = getattr(ocr_engine, "recognize_color_code_strips", None)
    if not callable(recognizer):
        return []
    try:
        return list(recognizer(image_path))
    except Exception:
        return []


def _should_prefer_strip_codes(strip_codes, parsed_codes) -> bool:
    strip_numeric_count = _color_code_numeric_count(strip_codes.codes)
    parsed_numeric_count = _color_code_numeric_count(parsed_codes.codes)
    if strip_numeric_count < 8:
        return False
    if strip_codes.orientation == "vertical":
        if parsed_codes.orientation != "vertical":
            return strip_numeric_count >= parsed_numeric_count
        return strip_numeric_count >= parsed_numeric_count + 3
    if strip_codes.orientation == "horizontal":
        if _parsed_codes_are_mostly_noise(parsed_codes):
            return True
        if _has_significantly_fewer_missing_codes(strip_codes, parsed_codes):
            return strip_numeric_count >= parsed_numeric_count
        if _strip_codes_extend_leading_sequence(strip_codes.codes, parsed_codes.codes):
            return True
        if parsed_codes.orientation != "horizontal":
            return strip_numeric_count >= parsed_numeric_count + 3
        return strip_numeric_count >= parsed_numeric_count + 3
    return False


def _color_code_numeric_count(codes: list[str]) -> int:
    return sum(1 for code in codes if code.isdigit() and len(code) <= 3)


def _parsed_codes_are_mostly_noise(parsed_codes) -> bool:
    if not parsed_codes.codes:
        return True
    numeric_count = _color_code_numeric_count(parsed_codes.codes)
    return numeric_count < 3 and numeric_count * 2 < len(parsed_codes.codes)


def _has_significantly_fewer_missing_codes(strip_codes, parsed_codes) -> bool:
    return len(parsed_codes.missing_codes) >= len(strip_codes.missing_codes) + 3


def _strip_codes_extend_leading_sequence(strip_codes: list[str], parsed_codes: list[str]) -> bool:
    strip_numbers = [int(code) for code in strip_codes if code.isdigit() and len(code) <= 3]
    parsed_numbers = [int(code) for code in parsed_codes if code.isdigit() and len(code) <= 3]
    if len(strip_numbers) < len(parsed_numbers) + 2 or not parsed_numbers:
        return False
    if min(strip_numbers) >= min(parsed_numbers):
        return False
    return set(parsed_numbers).issubset(strip_numbers)


def extract_group_name(image_path: Path, blocks: list[OcrBlock]) -> str:
    width, height = _image_size(image_path, blocks)
    candidates = [
        block
        for block in blocks
        if block.center_x <= width * 0.35 and block.center_y <= height * 0.22
    ]
    candidates = [
        block
        for block in candidates
        if len(block.text.strip()) <= 24 and not block.text.strip().isdigit()
    ]
    if not candidates:
        return ""

    top_center_y = min(block.center_y for block in candidates)
    if top_center_y > height * GROUP_NAME_TOP_BAND_RATIO:
        return ""

    min_text_height = min(max(block.height, 1.0) for block in candidates)
    row_tolerance = max(8.0, height * 0.01, min_text_height * 1.2)
    top_line_blocks = [
        block
        for block in candidates
        if block.center_y <= top_center_y + row_tolerance
    ]
    ordered = sorted(top_line_blocks, key=lambda block: (block.center_y, block.center_x))
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
