from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from color_card_toolkit.core.grouping import parse_group_name
from color_card_toolkit.core.layout_detection import crop_horizontal_api_regions
from color_card_toolkit.core.models import ImageRecognitionResult

CROP_PROMPT = """You are a color-card recognition assistant. The user provides two images:
1. The top-left group/name area.
2. The number row above the color blocks.

Return only JSON. Do not explain. Do not use Markdown.

Requirements:
- raw_name: read the group/name code from the first image.
- base_name: remove a trailing page marker from raw_name, such as (1), （2）, or -1.
- sequence: if raw_name explicitly contains a page marker such as (1), （2）, or -1, return that integer; otherwise return null.
- codes: read the number row in the second image from left to right.
- Do not read Description, Thickness, Size, specifications, or other text.
- Do not fill numbers that are not present in the image.
- Return all codes as strings.

Output shape:
{"raw_name":"","base_name":"","sequence":null,"codes":[]}"""

FULL_IMAGE_PROMPT = """You are a color-card recognition assistant. The user provides one full color-card image.

Return only JSON. Do not explain. Do not use Markdown.

Requirements:
- raw_name: read only the primary group/name identifier from the upper-left name box or the leftmost upper name area.
- The upper-left name area has priority over all other text in the image.
- If the upper-left name area contains a Chinese group name, return that Chinese name exactly.
- If the upper-left name area contains a numeric/alphanumeric identifier, return that identifier exactly.
- Do not use the upper-right Description/货名 area for raw_name, even if it contains a code and a title.
- base_name: remove a trailing page marker from raw_name, such as (1), （2）, or -1.
- sequence: if raw_name explicitly contains a page marker such as (1), （2）, or -1, return that integer; otherwise return null.
- codes: read the numbers above the color blocks from left to right.
- Do not read Description, Thickness, Size, specifications, or other text.
- Do not fill numbers that are not present in the image.
- Return all codes as strings.

Output shape:
{"raw_name":"","base_name":"","sequence":null,"codes":[]}"""

VERTICAL_FULL_IMAGE_PROMPT = """You are a color-card recognition assistant. The user provides one full vertical color-card image.

Return only JSON. Do not explain. Do not use Markdown.

Requirements:
- raw_name: read only the primary group/name identifier from the upper-left name box or the leftmost upper name area.
- The upper-left name area has priority over all other text in the image.
- If the upper-left name area contains a Chinese group name, return that Chinese name exactly.
- If the upper-left name area contains a numeric/alphanumeric identifier, return that identifier exactly.
- Do not use Description, Thickness, Size, specifications, or other text for raw_name.
- base_name: remove a trailing page marker from raw_name, such as (1), （2）, or -1.
- sequence: if raw_name explicitly contains a page marker such as (1), （2）, or -1, return that integer; otherwise return null.
- codes: read all color numbers beside the color blocks.
- Codes may be numeric, such as 1 or 28, or alphanumeric, such as A1, A2, A3, B1, or B2.
- Missing or skipped numeric codes are normal; do not force the result into a continuous sequence.
- The vertical color-card may have either 2 code columns or 3 code columns.
- Detect the actual number of code columns from the image.
- The `codes` array order must be column order, not row order.
- If there are 2 columns, return all codes from the left column top-to-bottom, then all codes from the right column top-to-bottom.
- If there are 3 columns, return all codes from the left column top-to-bottom, then all codes from the middle column top-to-bottom, then all codes from the right column top-to-bottom.
- Do not invent a missing middle column. Do not merge separate columns.
- Do not fill numbers that are not present in the image.
- Return all codes as strings.

Output shape:
{"raw_name":"","base_name":"","sequence":null,"codes":[]}"""


@dataclass(frozen=True)
class CloudVisionConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90
    enable_thinking: bool | None = False
    horizontal_use_yolo: bool = True
    concurrency: int = 4
    input_price_per_million_tokens: float = 1.2
    output_price_per_million_tokens: float = 7.2

    @property
    def enabled(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.model.strip())


class CloudRecognitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudVisionResponse:
    content_text: str
    usage: dict[str, Any]
    elapsed_seconds: float


def recognize_horizontal_image_with_cloud(image_path: str | Path, config: CloudVisionConfig) -> ImageRecognitionResult:
    path = Path(image_path)
    if not config.enabled:
        raise CloudRecognitionError("cloud recognition config is incomplete")

    crops = crop_horizontal_api_regions(path, conf=0.1) if config.horizontal_use_yolo else None
    if crops is not None:
        crop_result: ImageRecognitionResult | None = None
        try:
            response = _call_openai_compatible_vision(
                config,
                CROP_PROMPT,
                [crops.name_image, crops.code_image],
            )
            crop_result = _result_from_response(path, response, config=config, source="cloud_crop", retry_count=0)
            result = crop_result
            _validate_cloud_result(result)
            return result
        except Exception as crop_exc:
            response = _call_openai_compatible_vision(
                config,
                FULL_IMAGE_PROMPT,
                [_load_full_image(path)],
            )
            result = _result_from_response(path, response, config=config, source="cloud_retry_full", retry_count=1)
            if crop_result is not None:
                _merge_api_usage(result, crop_result)
            result.warnings.append(f"裁剪云端识别失败，已整图重试：{crop_exc}")
            _validate_cloud_result(result)
            return result

    response = _call_openai_compatible_vision(
        config,
        FULL_IMAGE_PROMPT,
        [_load_full_image(path)],
    )
    result = _result_from_response(path, response, config=config, source="cloud_full", retry_count=0)
    _validate_cloud_result(result)
    return result


def recognize_vertical_image_with_cloud(image_path: str | Path, config: CloudVisionConfig) -> ImageRecognitionResult:
    path = Path(image_path)
    if not config.enabled:
        raise CloudRecognitionError("cloud recognition config is incomplete")

    response = _call_openai_compatible_vision(
        config,
        VERTICAL_FULL_IMAGE_PROMPT,
        [_load_full_image(path)],
    )
    result = _result_from_response(path, response, config=config, source="cloud_vertical_full", retry_count=0)
    _validate_cloud_result(result)
    return result


def _call_openai_compatible_vision(
    config: CloudVisionConfig,
    prompt: str,
    images: list[Image.Image],
) -> CloudVisionResponse:
    url = _chat_completions_url(config.base_url)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(
        {
            "type": "image_url",
            "image_url": {"url": _image_to_data_url(image)},
        }
        for image in images
    )
    body = {
        "model": config.model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
    }
    if config.enable_thinking is not None:
        body["enable_thinking"] = config.enable_thinking
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise CloudRecognitionError(f"cloud API HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise CloudRecognitionError(f"cloud API request failed: {exc}") from exc

    try:
        data = json.loads(response_body)
        content_text = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise CloudRecognitionError(f"cloud API response shape is invalid: {response_body[:500]}") from exc

    return CloudVisionResponse(
        content_text=content_text,
        usage=data.get("usage") if isinstance(data.get("usage"), dict) else {},
        elapsed_seconds=time.perf_counter() - start,
    )


def _chat_completions_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return f"{cleaned}/chat/completions"


def _image_to_data_url(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=92)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _load_full_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise CloudRecognitionError(f"cloud response is not JSON: {text[:500]}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise CloudRecognitionError("cloud response JSON is not an object")
    return value


def _result_from_response(
    image_path: Path,
    response: CloudVisionResponse,
    *,
    config: CloudVisionConfig,
    source: str,
    retry_count: int,
) -> ImageRecognitionResult:
    payload = _parse_json_object(response.content_text)
    return _result_from_payload(
        image_path,
        payload,
        source=source,
        retry_count=retry_count,
        usage=response.usage,
        elapsed_seconds=response.elapsed_seconds,
        config=config,
    )


def _result_from_payload(
    image_path: Path,
    payload: dict[str, Any],
    *,
    source: str,
    retry_count: int,
    usage: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
    config: CloudVisionConfig | None = None,
) -> ImageRecognitionResult:
    raw_name = str(payload.get("raw_name") or "").strip()
    parsed = parse_group_name(raw_name or image_path.stem.strip())
    base_name = str(payload.get("base_name") or "").strip() or parsed.base_name
    sequence_value = payload.get("sequence")
    sequence, explicit_sequence = _parse_sequence(sequence_value, parsed.sequence, parsed.explicit_sequence)
    codes = _normalize_cloud_codes(payload.get("codes"))
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    input_price = config.input_price_per_million_tokens if config is not None else 0.0
    output_price = config.output_price_per_million_tokens if config is not None else 0.0
    estimated_cost = (prompt_tokens / 1_000_000 * input_price) + (completion_tokens / 1_000_000 * output_price)
    return ImageRecognitionResult(
        image_path=image_path,
        raw_name=raw_name,
        base_name=base_name,
        sequence=sequence,
        color_codes=codes,
        explicit_sequence=explicit_sequence,
        missing_codes=[],
        warnings=[],
        confidence=1.0,
        recognition_source=source,
        api_retry_count=retry_count,
        api_prompt_tokens=prompt_tokens,
        api_completion_tokens=completion_tokens,
        api_total_tokens=total_tokens,
        api_image_tokens=int(prompt_details.get("image_tokens") or 0),
        api_text_tokens=int(prompt_details.get("text_tokens") or 0),
        api_estimated_cost_rmb=estimated_cost,
        api_elapsed_seconds=elapsed_seconds,
        api_model=config.model if config is not None else "",
    )


def _merge_api_usage(target: ImageRecognitionResult, extra: ImageRecognitionResult) -> None:
    target.api_prompt_tokens += extra.api_prompt_tokens
    target.api_completion_tokens += extra.api_completion_tokens
    target.api_total_tokens += extra.api_total_tokens
    target.api_image_tokens += extra.api_image_tokens
    target.api_text_tokens += extra.api_text_tokens
    target.api_estimated_cost_rmb += extra.api_estimated_cost_rmb
    target.api_elapsed_seconds += extra.api_elapsed_seconds


def _parse_sequence(value: Any, fallback: int, fallback_explicit: bool) -> tuple[int, bool]:
    if value is None or value == "":
        return fallback, fallback_explicit
    try:
        return int(value), True
    except (TypeError, ValueError):
        return fallback, fallback_explicit


def _normalize_cloud_codes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    codes: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            codes.append(text)
    return codes


def _validate_cloud_result(result: ImageRecognitionResult) -> None:
    if not result.raw_name.strip():
        raise CloudRecognitionError("cloud result raw_name is empty")
    if len(result.color_codes) < 3:
        raise CloudRecognitionError("cloud result has fewer than 3 codes")
