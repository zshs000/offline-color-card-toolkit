from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from color_card_toolkit.core import cloud_recognition
from color_card_toolkit.core.cloud_recognition import (
    CloudRecognitionError,
    CloudVisionConfig,
    recognize_horizontal_image_with_cloud,
)


def _config() -> CloudVisionConfig:
    return CloudVisionConfig(base_url="https://example.test/v1", api_key="key", model="model")


def test_cloud_horizontal_uses_crops_when_yolo_regions_are_available(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "931.jpg"
    Image.new("RGB", (120, 80), "white").save(image_path)
    crop = Image.new("RGB", (20, 10), "white")
    monkeypatch.setattr(
        cloud_recognition,
        "crop_horizontal_api_regions",
        lambda path, conf=0.1: SimpleNamespace(name_image=crop, code_image=crop),
    )
    calls = []

    def fake_call(config, prompt, images):
        calls.append((prompt, images))
        return {"raw_name": "931", "base_name": "931", "sequence": None, "codes": ["1", "2", "3"]}

    monkeypatch.setattr(cloud_recognition, "_call_openai_compatible_vision", fake_call)

    result = recognize_horizontal_image_with_cloud(image_path, _config())

    assert result.raw_name == "931"
    assert result.color_codes == ["1", "2", "3"]
    assert result.recognition_source == "cloud_crop"
    assert result.api_retry_count == 0
    assert len(calls) == 1
    assert len(calls[0][1]) == 2


def test_cloud_horizontal_uses_full_image_when_crops_are_missing(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "931.jpg"
    Image.new("RGB", (120, 80), "white").save(image_path)
    monkeypatch.setattr(cloud_recognition, "crop_horizontal_api_regions", lambda path, conf=0.1: None)
    calls = []

    def fake_call(config, prompt, images):
        calls.append((prompt, images))
        return {"raw_name": "931", "base_name": "931", "sequence": None, "codes": ["1", "2", "3"]}

    monkeypatch.setattr(cloud_recognition, "_call_openai_compatible_vision", fake_call)

    result = recognize_horizontal_image_with_cloud(image_path, _config())

    assert result.recognition_source == "cloud_full"
    assert result.api_retry_count == 0
    assert len(calls) == 1
    assert len(calls[0][1]) == 1
    assert calls[0][1][0].size == (120, 80)


def test_cloud_horizontal_retries_full_image_when_crop_result_is_invalid(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "931.jpg"
    Image.new("RGB", (120, 80), "white").save(image_path)
    crop = Image.new("RGB", (20, 10), "white")
    monkeypatch.setattr(
        cloud_recognition,
        "crop_horizontal_api_regions",
        lambda path, conf=0.1: SimpleNamespace(name_image=crop, code_image=crop),
    )
    calls = []

    def fake_call(config, prompt, images):
        calls.append((prompt, images))
        if len(calls) == 1:
            raise CloudRecognitionError("bad json")
        return {"raw_name": "931", "base_name": "931", "sequence": None, "codes": ["1", "2", "3"]}

    monkeypatch.setattr(cloud_recognition, "_call_openai_compatible_vision", fake_call)

    result = recognize_horizontal_image_with_cloud(image_path, _config())

    assert result.recognition_source == "cloud_retry_full"
    assert result.api_retry_count == 1
    assert len(calls) == 2
    assert len(calls[1][1]) == 1
    assert any("整图重试" in warning for warning in result.warnings)
