from __future__ import annotations

from PIL import Image

from color_card_toolkit.core.layout_detection import infer_layout_orientation


def test_infer_layout_orientation_uses_exif_rotation(tmp_path) -> None:
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (100, 300), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif)

    assert infer_layout_orientation(image_path) == "horizontal"
