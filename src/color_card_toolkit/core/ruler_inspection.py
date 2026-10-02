from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from color_card_toolkit.core.ruler_detection import RulerGeometry, detect_ruler


@dataclass(frozen=True)
class RulerInspection:
    source_path: Path
    status: str
    message: str
    geometry: RulerGeometry | None
    dpi: tuple[int, int]
    suggested_ratio: float | None = None

    @property
    def passed(self) -> bool:
        return self.geometry is not None and self.geometry.healthy


def inspect_image_ruler(
    image_path: str | Path,
    *,
    crop_size_cm: int,
    search_ratio: float,
    suggest_retry: bool = True,
) -> RulerInspection:
    """Run the local ruler health check without contacting any cloud service."""
    path = Path(image_path)
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened)
            dpi = _read_dpi(image)
            geometry = detect_ruler(
                image,
                dpi,
                span_mm=crop_size_cm * 10,
                coarse_search_ratio=search_ratio,
            )
    except Exception as exc:
        return RulerInspection(
            source_path=path,
            status="failed",
            message=f"图片无法读取或检测异常：{exc}",
            geometry=None,
            dpi=(0, 0),
        )

    if geometry is not None and geometry.healthy:
        return RulerInspection(
            source_path=path,
            status="passed",
            message=(
                f"标尺检测通过：顶部支撑 {geometry.top_support}，左侧支撑 "
                f"{geometry.left_support}，旋转 {geometry.rotation_degrees:.2f}°"
            ),
            geometry=geometry,
            dpi=dpi,
        )

    suggested_ratio = None
    if suggest_retry:
        suggested_ratio = _suggest_ratio(
            image,
            dpi,
            crop_size_cm=crop_size_cm,
            current_ratio=search_ratio,
        )

    if geometry is None:
        message = "未找到完整的顶部和左侧标尺，可能是白边较宽、对比度不足或标尺不完整。"
    else:
        expected = (geometry.span_mm + 1) * 0.9
        message = (
            "找到标尺但健康度不足："
            f"顶部支撑 {geometry.top_support}、左侧支撑 {geometry.left_support}，"
            f"需要约 {expected:.0f} 个有效刻度。"
        )
    if suggested_ratio is not None:
        message += f" 建议将搜索范围调整到 {suggested_ratio:.0%} 后重试。"

    return RulerInspection(
        source_path=path,
        status="weak" if geometry is not None else "failed",
        message=message,
        geometry=geometry,
        dpi=dpi,
        suggested_ratio=suggested_ratio,
    )


def _suggest_ratio(
    image: Image.Image,
    dpi: tuple[int, int],
    *,
    crop_size_cm: int,
    current_ratio: float,
) -> float | None:
    candidates = [0.25, 0.30, 0.35, 0.40, 0.50]
    for candidate in candidates:
        if candidate <= current_ratio + 0.001:
            continue
        geometry = detect_ruler(
            image,
            dpi,
            span_mm=crop_size_cm * 10,
            coarse_search_ratio=candidate,
        )
        if geometry is not None and geometry.healthy:
            return candidate
    return None


def _read_dpi(image: Image.Image) -> tuple[int, int]:
    raw_dpi = image.info.get("dpi")
    if isinstance(raw_dpi, tuple) and len(raw_dpi) >= 2:
        try:
            x = int(round(float(raw_dpi[0])))
            y = int(round(float(raw_dpi[1])))
            if x > 0 and y > 0:
                return x, y
        except (TypeError, ValueError):
            pass
    return 300, 300
