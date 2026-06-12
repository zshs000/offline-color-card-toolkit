from __future__ import annotations

from pathlib import Path

from PIL import Image

from color_card_toolkit.core.models import OcrBlock, ParsedColorCodes
from color_card_toolkit.core.recognition import _should_prefer_strip_codes, extract_group_name


def block(text: str, x: float, y: float, w: float = 20, h: float = 12) -> OcrBlock:
    return OcrBlock(
        text=text,
        confidence=0.97,
        box=((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
    )


def test_extract_group_name_uses_only_top_text_line(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (1900, 750), "white").save(image_path)
    blocks = [
        block("PU6159(1)", 60, 38, 130, 30),
        block("厂家直销", 120, 90, 260, 70),
        block("批发零售", 120, 165, 250, 45),
    ]

    assert extract_group_name(image_path, blocks) == "PU6159(1)"


def test_extract_group_name_does_not_fallback_to_promo_text(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (1900, 750), "white").save(image_path)
    blocks = [
        block("厂家直销", 120, 90, 260, 70),
        block("批发零售", 120, 165, 250, 45),
    ]

    assert extract_group_name(image_path, blocks) == ""


def test_horizontal_strip_codes_replace_noisy_main_result() -> None:
    main = ParsedColorCodes(codes=["1807(1)", "TOCK", "1807"], orientation="horizontal")
    strip = ParsedColorCodes(
        codes=["01", "03", "04", "05", "09", "10", "11", "12"],
        orientation="horizontal",
    )

    assert _should_prefer_strip_codes(strip, main)
