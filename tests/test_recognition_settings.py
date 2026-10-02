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
            cloud_concurrency=99,
        ),
        settings_path,
    )

    loaded = load_recognition_settings(saved_path)

    assert loaded.base_url == "https://example.test/v1"
    assert loaded.api_key == "key"
    assert loaded.model == "qwen3.6-flash"
    assert loaded.cloud_concurrency == 10


def test_recognition_settings_defaults_without_yolo_setting(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("COLOR_CARD_CLOUD_BASE_URL", raising=False)
    monkeypatch.delenv("COLOR_CARD_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("COLOR_CARD_CLOUD_MODEL", raising=False)

    loaded = load_recognition_settings(tmp_path / "missing.json")

    assert loaded.cloud_concurrency == 4
    assert loaded.main_image_ruler_search_ratio == 0.20


def test_main_image_ruler_search_ratio_is_persisted_and_clamped(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    save_recognition_settings(
        RecognitionSettings(main_image_ruler_search_ratio=0.9),
        settings_path,
    )
    loaded = load_recognition_settings(settings_path)
    assert loaded.main_image_ruler_search_ratio == 0.50
