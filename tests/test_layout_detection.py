from __future__ import annotations

from PIL import Image

from color_card_toolkit.core.layout_detection import (
    _split_numeric_text_by_unit_count,
    infer_layout_orientation,
)


def test_infer_layout_orientation_uses_exif_rotation(tmp_path) -> None:
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (100, 300), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif)

    assert infer_layout_orientation(image_path) == "horizontal"


def test_split_numeric_text_by_unit_count_handles_zero_padded_codes() -> None:
    assert _split_numeric_text_by_unit_count("0102030405", 5) == ["01", "02", "03", "04", "05"]


def test_split_numeric_text_by_unit_count_handles_unpadded_codes() -> None:
    assert _split_numeric_text_by_unit_count("123456789101112", 12) == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
    ]


def test_split_numeric_text_by_unit_count_allows_real_missing_codes() -> None:
    assert _split_numeric_text_by_unit_count("123456789101112131415161718202122", 21) == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "20",
        "21",
        "22",
    ]


def test_split_numeric_text_by_unit_count_rejects_count_mismatch() -> None:
    assert _split_numeric_text_by_unit_count("123456789101112", 10) == []
