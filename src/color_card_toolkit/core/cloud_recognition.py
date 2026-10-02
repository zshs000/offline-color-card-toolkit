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
from color_card_toolkit.core.models import ImageRecognitionResult

FULL_IMAGE_PROMPT = """You are a color-card recognition assistant. The user provides one full color-card image.

Return only JSON. Do not explain. Do not use Markdown.

Requirements:
- raw_name: read only the primary group/name identifier from the white-background label/tag.
- The white-background label/tag is the authoritative source for raw_name and has priority over all other text in the image.
- Ignore text outside the white-background label/tag when choosing raw_name.
- 组名必须从白底标签/白底贴纸中读取。
- 不要把非白底区域、装饰文字、说明文字、货名文字当作组名。
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

MAIN_IMAGE_NAME_PROMPT = """You are a product material name recognition assistant. The user provides one full material scan.

Return only JSON. Do not explain. Do not use Markdown.

Requirements:
- Find the white rectangular product label anywhere in the full image.
- Read only the product name/code printed inside that white rectangular label.
- Ignore all ruler numbers, ruler ticks, material patterns, and text outside that white label.
- Preserve Chinese characters, letters, digits, spaces, hyphens, and parentheses exactly as printed.
- Do not invent or complete unclear characters.
- If the label cannot be read, return an empty string.

Output shape:
{"name":""}"""

MAIN_IMAGE_CLOUD_MAX_SIZE = 2048

# 百炼多模态接口对单个 Data URI 的 Base64 字符串限制为 10 MiB。这里预留
# 一点余量，避免严格的小于判断、请求封装或网关差异导致刚好卡在边界上。
MAX_DATA_URI_BYTES = 10 * 1024 * 1024
DATA_URI_TARGET_BYTES = MAX_DATA_URI_BYTES - 128 * 1024
DATA_URI_RETRY_TARGET_BYTES = 8 * 1024 * 1024
DATA_URI_PREFIX = "data:image/jpeg;base64,"
JPEG_QUALITY_LEVELS = (92, 85, 75, 65, 55, 45)
MIN_ADAPTIVE_IMAGE_SIDE = 64


@dataclass(frozen=True)
class CloudVisionConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90
    enable_thinking: bool | None = False
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


def recognize_main_image_name_with_cloud(image_path: str | Path, config: CloudVisionConfig) -> str:
    result = recognize_main_image_name_result_with_cloud(image_path, config)
    if not result.raw_name:
        message = result.warnings[-1] if result.warnings else "cloud response did not contain a readable main-image name"
        raise CloudRecognitionError(message)
    return result.raw_name


def recognize_main_image_name_result_with_cloud(
    image_path: str | Path,
    config: CloudVisionConfig,
) -> ImageRecognitionResult:
    path = Path(image_path)
    if not config.enabled:
        raise CloudRecognitionError("cloud recognition config is incomplete")

    response = _call_openai_compatible_vision(
        config,
        MAIN_IMAGE_NAME_PROMPT,
        [_load_main_image_for_cloud(path)],
    )
    parse_error = ""
    try:
        payload = _parse_json_object(response.content_text)
        name = _normalize_cloud_name(str(payload.get("name") or ""))
    except Exception as exc:
        name = ""
        parse_error = str(exc)

    result = _result_from_payload(
        path,
        {"raw_name": name, "base_name": name, "codes": []},
        source="cloud_main_image",
        retry_count=0,
        usage=response.usage,
        elapsed_seconds=response.elapsed_seconds,
        config=config,
    )
    if parse_error:
        result.warnings.append(f"云端返回无法解析：{parse_error}")
    if not name:
        result.warnings.append("cloud response did not contain a readable main-image name")
    return result


def _call_openai_compatible_vision(
    config: CloudVisionConfig,
    prompt: str,
    images: list[Image.Image],
) -> CloudVisionResponse:
    url = _chat_completions_url(config.base_url)
    start = time.perf_counter()

    # 绝大多数图片在第一次编码时就能满足限制；如果网关仍返回 413，
    # 再用更小的目标重新编码一次，兼容服务端对整体请求体的额外限制。
    target_sizes = (DATA_URI_TARGET_BYTES, DATA_URI_RETRY_TARGET_BYTES)
    for attempt, target_bytes in enumerate(target_sizes):
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": _image_to_data_url(image, max_bytes=target_bytes)},
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
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 413 and attempt == 0:
                continue
            raise CloudRecognitionError(f"cloud API HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise CloudRecognitionError(f"cloud API request failed: {exc}") from exc
    else:  # pragma: no cover - the loop either breaks or raises above
        raise CloudRecognitionError("cloud API request failed after image compression retry")

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


def _load_main_image_for_cloud(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail(
            (MAIN_IMAGE_CLOUD_MAX_SIZE, MAIN_IMAGE_CLOUD_MAX_SIZE),
            Image.Resampling.LANCZOS,
        )
        return image


def _chat_completions_url(base_url: str) -> str:
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return f"{cleaned}/chat/completions"


def _image_to_data_url(image: Image.Image, *, max_bytes: int = DATA_URI_TARGET_BYTES) -> str:
    """Encode an image as a Bailian-compatible Data URI.

    The API limit applies to the encoded Data URI item, not the source file.
    Keep the original quality and dimensions whenever possible, then lower JPEG
    quality and finally downscale until the encoded value fits the target.
    """
    working = image.convert("RGB")
    for _ in range(10):
        for quality in JPEG_QUALITY_LEVELS:
            data_url = _encode_jpeg_data_url(working, quality=quality)
            if len(data_url.encode("ascii")) < max_bytes:
                return data_url

        width, height = working.size
        if min(width, height) <= MIN_ADAPTIVE_IMAGE_SIDE:
            break
        next_size = (
            max(MIN_ADAPTIVE_IMAGE_SIDE, round(width * 0.75)),
            max(MIN_ADAPTIVE_IMAGE_SIDE, round(height * 0.75)),
        )
        if next_size == working.size:
            break
        working = working.resize(next_size, Image.Resampling.LANCZOS)

    # This is only reachable for an unusually small caller-provided limit. The
    # normal 8-10 MiB targets always fit well before this point.
    data_url = _encode_jpeg_data_url(working, quality=25)
    if len(data_url.encode("ascii")) < max_bytes:
        return data_url
    raise CloudRecognitionError(
        f"image remains too large after adaptive compression ({len(data_url.encode('ascii'))} bytes)"
    )


def _encode_jpeg_data_url(image: Image.Image, *, quality: int) -> str:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"{DATA_URI_PREFIX}{encoded}"


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
    raw_name = _normalize_cloud_name(str(payload.get("raw_name") or ""))
    parsed = parse_group_name(raw_name or image_path.stem.strip())
    base_name = _normalize_cloud_name(str(payload.get("base_name") or "")) or parsed.base_name
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


def _parse_sequence(value: Any, fallback: int, fallback_explicit: bool) -> tuple[int, bool]:
    if value is None or value == "":
        return fallback, fallback_explicit
    try:
        return int(value), True
    except (TypeError, ValueError):
        return fallback, fallback_explicit


def _normalize_cloud_name(value: str) -> str:
    """Clean a cloud-recognized name.

    Removes spaces inserted between CJK characters (e.g. ``60 后`` -> ``60后``)
    and collapses redundant whitespace, so that names group consistently.
    """
    text = value.strip()
    if not text:
        return text
    # Characters that a name space should be collapsed against: CJK chars,
    # ASCII digits/letters, and half/full-width parentheses. The model
    # sometimes inserts stray spaces (e.g. "60 后", "申 公 豹", "柔镜 （3）").
    cjk = r"\u4e00-\u9fff\u3400-\u4dbf"
    edge = rf"{cjk}0-9A-Za-z（）()"
    # Remove whitespace that touches a CJK character on either side.
    pattern = rf"(?<=[{edge}])\s+(?=[{cjk}])|(?<=[{cjk}])\s+(?=[{edge}])"
    text = re.sub(pattern, "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
