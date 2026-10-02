from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import color_card_toolkit.core.recognition as recognition_module
from color_card_toolkit.core.cloud_recognition import CloudVisionConfig
from color_card_toolkit.core.models import ImageRecognitionResult
from color_card_toolkit.core.recognition import infer_layout_orientation, recognize_image


def test_infer_layout_orientation_uses_exif_rotation(tmp_path: Path) -> None:
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (100, 300), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif)

    assert infer_layout_orientation(image_path) == "horizontal"


@pytest.mark.parametrize(
    ("width", "height", "orientation", "source"),
    [
        (80, 120, "vertical", "cloud_vertical_full"),
        (1000, 1000, "vertical", "cloud_vertical_full"),
        (1100, 1000, "vertical", "cloud_vertical_full"),
        (1199, 1000, "vertical", "cloud_vertical_full"),
        (1200, 1000, "horizontal", "cloud_full"),
        (1201, 1000, "horizontal", "cloud_full"),
    ],
)
def test_recognize_image_preserves_layout_threshold(
    monkeypatch, tmp_path: Path, width: int, height: int, orientation: str, source: str
) -> None:
    image_path = tmp_path / "6002(1).jpg"
    Image.new("RGB", (width, height), "white").save(image_path)
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
            recognition_source=source,
        )

    wrong_orientation = "horizontal" if orientation == "vertical" else "vertical"
    monkeypatch.setattr(recognition_module, f"recognize_{orientation}_image_with_cloud", fake_cloud)
    monkeypatch.setattr(
        recognition_module,
        f"recognize_{wrong_orientation}_image_with_cloud",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong orientation")),
    )

    result = recognize_image(image_path, cloud_config=config)

    assert result.recognition_source == source
    assert result.raw_name == "6002(1)"


def test_recognize_image_without_cloud_config_does_not_use_local_inference(tmp_path: Path) -> None:
    image_path = tmp_path / "931.jpg"
    Image.new("RGB", (120, 80), "white").save(image_path)

    result = recognize_image(image_path)

    assert result.raw_name == "931"
    assert result.color_codes == []
    assert "未调用本地 YOLO" in result.warnings[0]
