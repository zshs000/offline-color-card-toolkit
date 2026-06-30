from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from color_card_toolkit.core.cloud_recognition import CloudVisionConfig
from color_card_toolkit.core.models import ImageRecognitionResult
from color_card_toolkit.core.recognition_logging import write_recognition_log


def test_write_recognition_log_summarizes_usage_and_redacts_api_key(tmp_path: Path) -> None:
    result = ImageRecognitionResult(
        image_path=tmp_path / "931.jpg",
        raw_name="931",
        base_name="931",
        sequence=1,
        color_codes=["1", "2", "3"],
        recognition_source="cloud_full",
        api_prompt_tokens=1000,
        api_completion_tokens=100,
        api_total_tokens=1100,
        api_image_tokens=800,
        api_text_tokens=200,
        api_estimated_cost_rmb=0.00192,
        api_elapsed_seconds=7.5,
        api_model="qwen3.6-flash",
    )
    config = CloudVisionConfig(
        base_url="https://example.test/v1",
        api_key="secret-key",
        model="qwen3.6-flash",
        horizontal_use_yolo=False,
    )

    log_path = write_recognition_log(
        [result],
        failed_count=0,
        cloud_config=config,
        started_at=datetime(2026, 6, 30, 10, 0, 0),
        finished_at=datetime(2026, 6, 30, 10, 0, 8),
        logs_dir=tmp_path,
    )

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["cloud_config"]["api_key"] == "***"
    assert payload["cloud_config"]["horizontal_use_yolo"] is False
    assert payload["summary"]["prompt_tokens"] == 1000
    assert payload["summary"]["completion_tokens"] == 100
    assert payload["summary"]["estimated_cost_rmb"] == 0.00192
    assert payload["results"][0]["api_model"] == "qwen3.6-flash"
