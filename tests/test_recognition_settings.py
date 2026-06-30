from __future__ import annotations

from color_card_toolkit.core.recognition_settings import (
    RecognitionSettings,
    load_recognition_settings,
    save_recognition_settings,
)


def test_recognition_settings_roundtrip_and_clamps_concurrency(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    saved_path = save_recognition_settings(
        RecognitionSettings(
            base_url="https://example.test/v1",
            api_key="key",
            model="qwen3.6-flash",
            horizontal_use_yolo=True,
            cloud_concurrency=99,
        ),
        settings_path,
    )

    loaded = load_recognition_settings(saved_path)

    assert loaded.base_url == "https://example.test/v1"
    assert loaded.api_key == "key"
    assert loaded.model == "qwen3.6-flash"
    assert loaded.horizontal_use_yolo is True
    assert loaded.cloud_concurrency == 10


def test_recognition_settings_default_horizontal_yolo_is_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("COLOR_CARD_CLOUD_BASE_URL", raising=False)
    monkeypatch.delenv("COLOR_CARD_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("COLOR_CARD_CLOUD_MODEL", raising=False)

    loaded = load_recognition_settings(tmp_path / "missing.json")

    assert loaded.horizontal_use_yolo is False
    assert loaded.cloud_concurrency == 4
