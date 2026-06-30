from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


APP_FOLDER_NAME = "线下色卡采集工具集"
SETTINGS_FILENAME = "recognition_settings.json"


@dataclass
class RecognitionSettings:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    horizontal_use_yolo: bool = False
    cloud_concurrency: int = 4


def default_settings_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_FOLDER_NAME / SETTINGS_FILENAME


def load_recognition_settings(path: Path | None = None) -> RecognitionSettings:
    settings_path = path or default_settings_path()
    settings = RecognitionSettings(
        base_url=os.environ.get("COLOR_CARD_CLOUD_BASE_URL", ""),
        api_key=os.environ.get("COLOR_CARD_CLOUD_API_KEY", ""),
        model=os.environ.get("COLOR_CARD_CLOUD_MODEL", ""),
    )
    if not settings_path.exists():
        return settings
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return settings
    if not isinstance(payload, dict):
        return settings
    return RecognitionSettings(
        base_url=str(payload.get("base_url") or settings.base_url),
        api_key=str(payload.get("api_key") or settings.api_key),
        model=str(payload.get("model") or settings.model),
        horizontal_use_yolo=bool(payload.get("horizontal_use_yolo", settings.horizontal_use_yolo)),
        cloud_concurrency=_clamp_concurrency(payload.get("cloud_concurrency", settings.cloud_concurrency)),
    )


def save_recognition_settings(settings: RecognitionSettings, path: Path | None = None) -> Path:
    settings.cloud_concurrency = _clamp_concurrency(settings.cloud_concurrency)
    settings_path = path or default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path


def _clamp_concurrency(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 4
    return min(10, max(1, parsed))
