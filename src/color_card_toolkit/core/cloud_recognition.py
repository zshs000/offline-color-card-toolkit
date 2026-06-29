from __future__ import annotations

import base64
import json
import re
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
- raw_name: read the group/name code from the top-left area of the image.
- base_name: remove a trailing page marker from raw_name, such as (1), （2）, or -1.
- sequence: if raw_name explicitly contains a page marker such as (1), （2）, or -1, return that integer; otherwise return null.
- codes: read the numbers above the color blocks from left to right.
- Do not read Description, Thickness, Size, specifications, or other text.
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

    @property
    def enabled(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.model.strip())


class CloudRecognitionError(RuntimeError):
    pass


def recognize_horizontal_image_with_cloud(image_path: str | Path, config: CloudVisionConfig) -> ImageRecognitionResult:
    path = Path(image_path)
    if not config.enabled:
        raise CloudRecognitionError("cloud recognition config is incomplete")

    crops = crop_horizontal_api_regions(path, conf=0.1)
    if crops is not None:
        try:
            payload = _call_openai_compatible_vision(
                config,
                CROP_PROMPT,
                [crops.name_image, crops.code_image],
            )
            result = _result_from_payload(path, payload, source="cloud_crop", retry_count=0)
            _validate_cloud_result(result)
            return result
        except Exception as crop_exc:
            payload = _call_openai_compatible_vision(
                config,
                FULL_IMAGE_PROMPT,
                [_load_full_image(path)],
            )
            result = _result_from_payload(path, payload, source="cloud_retry_full", retry_count=1)
            result.warnings.append(f"裁剪云端识别失败，已整图重试：{crop_exc}")
            _validate_cloud_result(result)
            return result

    payload = _call_openai_compatible_vision(
        config,
        FULL_IMAGE_PROMPT,
        [_load_full_image(path)],
    )
    result = _result_from_payload(path, payload, source="cloud_full", retry_count=0)
    _validate_cloud_result(result)
    return result


def _call_openai_compatible_vision(
    config: CloudVisionConfig,
    prompt: str,
    images: list[Image.Image],
) -> dict[str, Any]:
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
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
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

    return _parse_json_object(content_text)


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


def _result_from_payload(
    image_path: Path,
    payload: dict[str, Any],
    *,
    source: str,
    retry_count: int,
) -> ImageRecognitionResult:
    raw_name = str(payload.get("raw_name") or "").strip()
    parsed = parse_group_name(raw_name or image_path.stem.strip())
    base_name = str(payload.get("base_name") or "").strip() or parsed.base_name
    sequence_value = payload.get("sequence")
    sequence, explicit_sequence = _parse_sequence(sequence_value, parsed.sequence, parsed.explicit_sequence)
    codes = _normalize_cloud_codes(payload.get("codes"))
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
    )


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
