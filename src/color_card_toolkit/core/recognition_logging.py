from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from color_card_toolkit.core.cloud_recognition import CloudVisionConfig
from color_card_toolkit.core.models import ImageRecognitionResult


def summarize_api_usage(results: list[ImageRecognitionResult]) -> dict[str, Any]:
    prompt_tokens = sum(result.api_prompt_tokens for result in results)
    completion_tokens = sum(result.api_completion_tokens for result in results)
    total_tokens = sum(result.api_total_tokens for result in results)
    image_tokens = sum(result.api_image_tokens for result in results)
    text_tokens = sum(result.api_text_tokens for result in results)
    estimated_cost = sum(result.api_estimated_cost_rmb for result in results)
    elapsed_seconds = sum(result.api_elapsed_seconds for result in results)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "image_tokens": image_tokens,
        "text_tokens": text_tokens,
        "estimated_cost_rmb": estimated_cost,
        "api_elapsed_seconds": elapsed_seconds,
    }


def write_recognition_log(
    results: list[ImageRecognitionResult],
    *,
    failed_count: int,
    cloud_config: CloudVisionConfig | None,
    started_at: datetime,
    finished_at: datetime,
    logs_dir: Path | None = None,
) -> Path:
    output_dir = logs_dir or Path.cwd() / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"recognition_{finished_at.strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "failed_count": failed_count,
        "cloud_config": _safe_cloud_config(cloud_config),
        "summary": summarize_api_usage(results),
        "results": [_result_payload(result) for result in results],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path


def _safe_cloud_config(config: CloudVisionConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "base_url": config.base_url,
        "api_key": "***" if config.api_key else "",
        "model": config.model,
        "enable_thinking": config.enable_thinking,
        "horizontal_use_yolo": config.horizontal_use_yolo,
        "input_price_per_million_tokens": config.input_price_per_million_tokens,
        "output_price_per_million_tokens": config.output_price_per_million_tokens,
    }


def _result_payload(result: ImageRecognitionResult) -> dict[str, Any]:
    return {
        "image_path": str(result.image_path),
        "raw_name": result.raw_name,
        "base_name": result.base_name,
        "sequence": result.sequence if result.explicit_sequence else None,
        "code_count": len(result.color_codes),
        "codes": result.color_codes,
        "missing_codes": result.missing_codes,
        "warnings": result.warnings,
        "confidence": result.confidence,
        "recognition_source": result.recognition_source,
        "api_retry_count": result.api_retry_count,
        "api_model": result.api_model,
        "api_prompt_tokens": result.api_prompt_tokens,
        "api_completion_tokens": result.api_completion_tokens,
        "api_total_tokens": result.api_total_tokens,
        "api_image_tokens": result.api_image_tokens,
        "api_text_tokens": result.api_text_tokens,
        "api_estimated_cost_rmb": result.api_estimated_cost_rmb,
        "api_elapsed_seconds": result.api_elapsed_seconds,
    }
