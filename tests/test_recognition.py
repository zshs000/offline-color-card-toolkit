from __future__ import annotations

from pathlib import Path

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
        "recognize_horizontal_image_with_cloud",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong orientation")),
    )

    result = recognize_image(image_path, cloud_config=config)

    assert result.recognition_source == "cloud_vertical_full"
    assert result.raw_name == "6002(1)"


def test_recognize_image_without_cloud_config_does_not_use_local_inference(tmp_path: Path) -> None:
    image_path = tmp_path / "931.jpg"
    Image.new("RGB", (120, 80), "white").save(image_path)

    result = recognize_image(image_path)

    assert result.raw_name == "931"
    assert result.color_codes == []
    assert "未调用本地 YOLO" in result.warnings[0]
