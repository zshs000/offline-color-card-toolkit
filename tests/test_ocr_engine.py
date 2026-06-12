from __future__ import annotations

from color_card_toolkit.core.color_code_parser import parse_color_codes
from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import (
    RapidOcrEngine,
    _merge_horizontal_variant_blocks,
    _select_supplemental_blocks,
)


def block(text: str, x: float, y: float, w: float = 80, h: float = 36) -> OcrBlock:
    return OcrBlock(
        text=text,
        confidence=0.96,
        box=((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
    )


def test_rapid_ocr_engine_passes_thread_limits_to_factory(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_create_engine(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(RapidOcrEngine, "_create_engine", staticmethod(fake_create_engine))

    RapidOcrEngine(intra_op_num_threads=1, inter_op_num_threads=1)

    assert captured == {"intra_op_num_threads": 1, "inter_op_num_threads": 1}


def test_horizontal_variant_blocks_keep_color_code_row_over_page_noise() -> None:
    blocks = [
        block("1807", 3740, 250, 360, 140),
        block('Width:52"Thickness:0.9mm', 3560, 435, 740, 60),
        block("01", 100, 740),
        block("030405", 260, 740, 280),
        block("09", 960, 740),
        block("10", 1160, 740),
        block("111213", 1340, 740, 280),
        block("14", 1900, 740),
        block("15", 2100, 740),
        block("16", 2300, 740),
        block("1820", 2500, 740, 180),
        block("22", 2920, 740),
        block("23", 3120, 740),
        block("24 25", 3320, 740, 220),
        block("26", 3700, 740),
        block("08", 4200, 740),
    ]

    merged = _merge_horizontal_variant_blocks(blocks)
    parsed = parse_color_codes(merged)

    assert parsed.codes == [
        "01",
        "03",
        "04",
        "05",
        "09",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "18",
        "20",
        "22",
        "23",
        "24",
        "25",
        "26",
        "08",
    ]


def test_strong_horizontal_variant_replaces_side_strip_duplicates() -> None:
    side_blocks = [
        block("04", 560, 740),
        block("26", 3980, 740),
    ]
    horizontal_blocks = [
        block("01", 100, 740),
        block("030405", 260, 740, 280),
        block("09", 960, 740),
        block("10", 1160, 740),
        block("111213", 1340, 740, 280),
        block("14", 1900, 740),
        block("15", 2100, 740),
        block("16", 2300, 740),
        block("1820", 2500, 740, 180),
        block("22", 2920, 740),
        block("23", 3120, 740),
        block("24 25", 3320, 740, 220),
        block("26", 3700, 740),
        block("08", 4200, 740),
    ]

    selected = _select_supplemental_blocks(side_blocks, [horizontal_blocks])

    assert selected == horizontal_blocks
