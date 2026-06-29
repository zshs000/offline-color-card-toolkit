from __future__ import annotations

from pathlib import Path

from PIL import Image

import color_card_toolkit.core.recognition as recognition_module
from color_card_toolkit.core.cloud_recognition import CloudVisionConfig
from color_card_toolkit.core.models import ImageRecognitionResult, OcrBlock, ParsedColorCodes
from color_card_toolkit.core.recognition import _should_prefer_strip_codes, extract_group_name, recognize_image


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


def test_recognize_image_routes_vertical_to_cloud_when_configured(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "6002(1).jpg"
    Image.new("RGB", (80, 120), "white").save(image_path)
    config = CloudVisionConfig(base_url="https://example.test/v1", api_key="key", model="model")

    def fake_cloud(path, cloud_config):
        assert path == image_path
        assert cloud_config == config
        return ImageRecognitionResult(
            image_path=path,
            raw_name="6002(1)",
            base_name="6002",
            sequence=1,
            color_codes=["1", "2", "3"],
            recognition_source="cloud_vertical_full",
        )

    monkeypatch.setattr(recognition_module, "recognize_vertical_image_with_cloud", fake_cloud)
    monkeypatch.setattr(
        recognition_module,
        "_recognize_vertical_with_layout_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local vertical path should not run")),
    )

    result = recognize_image(image_path, object(), cloud_config=config)

    assert result.recognition_source == "cloud_vertical_full"
    assert result.raw_name == "6002(1)"


def test_horizontal_strip_codes_replace_noisy_main_result() -> None:
    main = ParsedColorCodes(codes=["1807(1)", "TOCK", "1807"], orientation="horizontal")
    strip = ParsedColorCodes(
        codes=["01", "03", "04", "05", "09", "10", "11", "12"],
        orientation="horizontal",
    )

    assert _should_prefer_strip_codes(strip, main)


def test_horizontal_strip_codes_replace_same_count_main_result_with_fewer_missing_codes() -> None:
    main = ParsedColorCodes(
        codes=["01", "02", "03", "04", "05", "06", "08", "60", "11", "12"],
        orientation="horizontal",
        missing_codes=[
            "07",
            "09",
            "10",
            "13",
            "14",
            "15",
            "16",
            "17",
            "18",
            "19",
            "20",
            "21",
        ],
    )
    strip = ParsedColorCodes(
        codes=["01", "02", "03", "04", "05", "06", "08", "09", "11", "12"],
        orientation="horizontal",
        missing_codes=["07", "10"],
    )

    assert _should_prefer_strip_codes(strip, main)


def test_horizontal_strip_codes_replace_suffix_main_result_when_leading_codes_were_missed() -> None:
    main = ParsedColorCodes(
        codes=["03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],
        orientation="horizontal",
    )
    strip = ParsedColorCodes(
        codes=["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],
        orientation="horizontal",
    )

    assert _should_prefer_strip_codes(strip, main)
