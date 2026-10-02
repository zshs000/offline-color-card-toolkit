from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from color_card_toolkit.core.cloud_recognition import (
    CloudVisionConfig,
    recognize_horizontal_image_with_cloud,
    recognize_vertical_image_with_cloud,
)
from color_card_toolkit.core.grouping import parse_group_name
from color_card_toolkit.core.models import ImageRecognitionResult


def recognize_image(
    image_path: str | Path,
    _ocr_engine: object | None = None,
    *,
    cloud_config: CloudVisionConfig | None = None,
) -> ImageRecognitionResult:
    """Recognize a stack-to-flat image through the cloud path only.

    ``_ocr_engine`` remains an ignored compatibility parameter for callers from
    older integrations. The application no longer initializes or invokes a
    local YOLO/OCR layout-recognition path.
    """
    path = Path(image_path)
    if cloud_config is None or not cloud_config.enabled:
        return _manual_result_for_image(path, "叠贴转平贴现在需要完整云端识别配置，未调用本地 YOLO。")

    try:
        if infer_layout_orientation(path) == "vertical":
            return recognize_vertical_image_with_cloud(path, cloud_config)
        return recognize_horizontal_image_with_cloud(path, cloud_config)
    except Exception as exc:
        result = _manual_result_for_image(path, f"云端识别失败：{exc}。请手动修正识别结果。")
        result.recognition_source = "cloud_failed"
        return result


def infer_layout_orientation(image_path: str | Path) -> str:
    path = Path(image_path)
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened)
        width, height = image.size
    return "vertical" if height > width else "horizontal"


def _manual_result_for_image(image_path: Path, warning: str) -> ImageRecognitionResult:
    fallback_name = image_path.stem.strip()
    group = parse_group_name(fallback_name)
    return ImageRecognitionResult(
        image_path=image_path,
        raw_name=fallback_name,
        base_name=group.base_name,
        sequence=group.sequence,
        color_codes=[],
        explicit_sequence=group.explicit_sequence,
        warnings=[warning],
        confidence=0.0,
    )
