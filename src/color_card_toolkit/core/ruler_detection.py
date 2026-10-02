"""尺子刻度检测模块。

从 artifacts/diagnostics/try_tick_ruler_detection.py 与
try_tick_crop_preview.py 移植，移除了模块级副作用，对外只暴露 detect_ruler()。

适用前提：卡片左上角带 1mm 等距刻度尺，尺带浅色、刻度深色，dpi 800/1200。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

MAX_ANALYSIS_SIZE = 1800
TICK_BINARY_THRESHOLD = 165
RANSAC_ITERATIONS = 1500
RANSAC_INLIER_THRESHOLD = 3.5
FINAL_INLIER_THRESHOLD = 4.0
MIN_ENDPOINTS = 12
SUPPORTED_RULER_SPANS_MM = (150, 100)
HEALTH_MIN_INLIER_RATIO = 0.3
HEALTH_MIN_SUPPORT_RATIO = 0.9
_DPI_CANDIDATES = (800, 1200, 300, 600)
# Some scanners leave a broad white margin before the ruler. Keep the lower
# bound away from the image border, but search farther than the old 3%-12%
# window so the material/ruler corner is still in the coarse ROI.
COARSE_SEARCH_MIN_RATIO = 0.03
COARSE_SEARCH_MAX_RATIO = 0.20


def coarse_origin(
    gray: np.ndarray,
    *,
    max_search_ratio: float = COARSE_SEARCH_MAX_RATIO,
) -> tuple[int, int]:
    """在左上角小框内找灰度剖面最陡的跳变，作为尺子起点的粗位置。"""
    height, width = gray.shape
    x_profile = np.median(gray[int(height * 0.2) : int(height * 0.75), :], axis=0)
    y_profile = np.median(gray[:, int(width * 0.2) : int(width * 0.85)], axis=1)
    max_search_ratio = min(0.80, max(COARSE_SEARCH_MIN_RATIO + 0.01, float(max_search_ratio)))
    x_start, x_end = int(width * COARSE_SEARCH_MIN_RATIO), int(width * max_search_ratio)
    y_start, y_end = int(height * COARSE_SEARCH_MIN_RATIO), int(height * max_search_ratio)
    x = x_start + int(np.argmax(np.abs(np.diff(x_profile[x_start:x_end])))) + 1
    y = y_start + int(np.argmax(np.abs(np.diff(y_profile[y_start:y_end])))) + 1
    return x, y


def _local_contrast_endpoint(
    gray: np.ndarray,
    center_x: int,
    coarse_y: int,
) -> float | None:
    height, width = gray.shape
    if center_x < 8 or center_x + 8 >= width:
        return None
    y_start = max(0, coarse_y - int(height * 0.075))
    y_end = min(height, coarse_y + int(height * 0.02))
    center = gray[y_start:y_end, center_x - 1 : center_x + 2].mean(axis=1)
    left_background = gray[y_start:y_end, center_x - 7 : center_x - 4].mean(axis=1)
    right_background = gray[y_start:y_end, center_x + 4 : center_x + 7].mean(axis=1)
    background = np.maximum(left_background, right_background)
    contrast = background - center
    contrast = np.convolve(contrast, np.ones(3, dtype=np.float32) / 3, mode="same")
    threshold = max(7.0, float(np.percentile(contrast, 90)) * 0.22)
    active = (contrast >= threshold).astype(np.uint8)
    active = cv2.morphologyEx(
        active.reshape(-1, 1),
        cv2.MORPH_CLOSE,
        np.ones((3, 1), dtype=np.uint8),
    ).reshape(-1)

    padded = np.pad(active.astype(np.int8), (1, 1))
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    runs = [(start, end) for start, end in zip(starts, ends) if end - start >= 5]
    if not runs:
        return None
    start, end = max(runs, key=lambda run: run[1] - run[0])
    del start
    return float(y_start + end - 1)


def _local_contrast_endpoint_x(
    gray: np.ndarray,
    center_y: int,
    coarse_x: int,
) -> float | None:
    height, width = gray.shape
    if center_y < 8 or center_y + 8 >= height:
        return None
    x_start = max(0, coarse_x - int(width * 0.075))
    x_end = min(width, coarse_x + int(width * 0.02))
    center = gray[center_y - 1 : center_y + 2, x_start:x_end].mean(axis=0)
    upper_background = gray[center_y - 7 : center_y - 4, x_start:x_end].mean(axis=0)
    lower_background = gray[center_y + 4 : center_y + 7, x_start:x_end].mean(axis=0)
    background = np.maximum(upper_background, lower_background)
    contrast = background - center
    contrast = np.convolve(contrast, np.ones(3, dtype=np.float32) / 3, mode="same")
    threshold = max(7.0, float(np.percentile(contrast, 90)) * 0.22)
    active = (contrast >= threshold).astype(np.uint8)
    active = cv2.morphologyEx(
        active.reshape(1, -1),
        cv2.MORPH_CLOSE,
        np.ones((1, 3), dtype=np.uint8),
    ).reshape(-1)

    padded = np.pad(active.astype(np.int8), (1, 1))
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    runs = [(start, end) for start, end in zip(starts, ends) if end - start >= 5]
    if not runs:
        return None
    start, end = max(runs, key=lambda run: run[1] - run[0])
    del start
    return float(x_start + end - 1)


def tick_endpoints(
    gray: np.ndarray,
    coarse: tuple[int, int],
    *,
    top: bool,
) -> np.ndarray:
    """检测顶边（top=True）或左边（top=False）的刻度端点坐标。"""
    height, width = gray.shape
    coarse_x, coarse_y = coarse
    binary = np.where(gray < TICK_BINARY_THRESHOLD, 255, 0).astype(np.uint8)
    if top:
        y_start = max(0, coarse_y - int(height * 0.075))
        y_end = min(height, coarse_y + int(height * 0.012))
        roi = binary[y_start:y_end, int(width * 0.015) : int(width * 0.97)]
        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(25, int(width * 0.025)), 1),
        )
        horizontal_lines = cv2.morphologyEx(roi, cv2.MORPH_OPEN, horizontal_kernel)
        horizontal_lines = cv2.dilate(
            horizontal_lines,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)),
        )
        roi = cv2.bitwise_and(roi, cv2.bitwise_not(horizontal_lines))
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(5, int(height * 0.004))),
        )
        strokes = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
    else:
        x_start = max(0, coarse_x - int(width * 0.075))
        x_end = min(width, coarse_x + int(width * 0.012))
        roi = binary[int(height * 0.015) : int(height * 0.97), x_start:x_end]
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(5, int(width * 0.004)), 1),
        )
        strokes = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)

    count, _, stats, _ = cv2.connectedComponentsWithStats(strokes, connectivity=8)
    points = []
    for index in range(1, count):
        x, y, component_width, component_height, area = stats[index]
        if top:
            if component_height < 5 or component_height < component_width * 1.8:
                continue
            if component_width > width * 0.012 or component_height > height * 0.09:
                continue
            center_x = round(x + component_width / 2 + int(width * 0.015))
            endpoint_y = _local_contrast_endpoint(gray, center_x, coarse_y)
            if endpoint_y is not None:
                points.append((float(center_x), endpoint_y))
        else:
            if component_width < 5 or component_width < component_height * 1.8:
                continue
            if component_height > height * 0.012 or component_width > width * 0.09:
                continue
            center_y = round(y + component_height / 2 + int(height * 0.015))
            endpoint_x = _local_contrast_endpoint_x(gray, center_y, coarse_x)
            if endpoint_x is not None:
                points.append((endpoint_x, float(center_y)))
    return np.asarray(points, dtype=np.float64)


def fit_endpoint_line(
    points: np.ndarray,
    *,
    horizontal: bool,
    size: int,
    min_secondary_at_center: float | None = None,
    max_secondary_at_center: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RANSAC + Huber 拟合刻度端点直线，返回（线上一点，方向向量，内点掩码）。"""
    if len(points) < MIN_ENDPOINTS:
        raise RuntimeError(f"not enough tick endpoints: {len(points)}")
    rng = np.random.default_rng(7)
    best_inliers = None
    best_score = -1.0
    primary = 0 if horizontal else 1
    secondary = 1 - primary
    max_slope = math.tan(math.radians(3.0))
    for _ in range(RANSAC_ITERATIONS):
        first, second = points[rng.integers(0, len(points), 2)]
        delta_primary = second[primary] - first[primary]
        if abs(delta_primary) < size * 0.25:
            continue
        slope = (second[secondary] - first[secondary]) / delta_primary
        if abs(slope) > max_slope:
            continue
        center_secondary = first[secondary] + (size / 2 - first[primary]) * slope
        if min_secondary_at_center is not None and center_secondary < min_secondary_at_center:
            continue
        if max_secondary_at_center is not None and center_secondary > max_secondary_at_center:
            continue
        predicted = first[secondary] + (points[:, primary] - first[primary]) * slope
        residuals = np.abs(points[:, secondary] - predicted)
        inliers = residuals <= RANSAC_INLIER_THRESHOLD
        if inliers.sum() < MIN_ENDPOINTS:
            continue
        coverage = np.ptp(points[inliers, primary]) / size
        score = float(inliers.sum()) + coverage * 20
        if score > best_score:
            best_score = score
            best_inliers = inliers
    if best_inliers is None:
        raise RuntimeError("could not fit ruler tick endpoints")

    line = cv2.fitLine(
        points[best_inliers].astype(np.float32),
        cv2.DIST_HUBER,
        0,
        0.01,
        0.01,
    ).reshape(-1)
    direction = np.asarray((float(line[0]), float(line[1])), dtype=np.float64)
    point = np.asarray((float(line[2]), float(line[3])), dtype=np.float64)
    if horizontal and direction[0] < 0:
        direction *= -1
    if not horizontal and direction[1] < 0:
        direction *= -1
    residuals = np.abs(
        (points[:, 0] - point[0]) * direction[1]
        - (points[:, 1] - point[1]) * direction[0]
    )
    inliers = residuals <= FINAL_INLIER_THRESHOLD
    return point, direction, inliers


def intersection(
    first: tuple[np.ndarray, np.ndarray],
    second: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    first_point, first_direction = first
    second_point, second_direction = second
    determinant = (
        first_direction[0] * second_direction[1]
        - first_direction[1] * second_direction[0]
    )
    delta = second_point - first_point
    distance = (
        delta[0] * second_direction[1] - delta[1] * second_direction[0]
    ) / determinant
    return first_point + distance * first_direction


def line_angle(direction: np.ndarray, *, horizontal: bool) -> float:
    if horizontal:
        return math.degrees(math.atan2(direction[1], direction[0]))
    return math.degrees(math.atan2(-direction[0], direction[1]))


def _tick_spacing(
    points: np.ndarray,
    inliers: np.ndarray,
    *,
    primary: int,
    expected: float,
) -> float:
    coordinates = np.sort(points[inliers, primary])
    coordinates = coordinates[np.r_[True, np.diff(coordinates) > expected * 0.25]]
    gaps = np.diff(coordinates)
    usable = gaps[(gaps >= expected * 0.55) & (gaps <= expected * 1.45)]
    if len(usable) < 5:
        raise RuntimeError("not enough adjacent tick gaps")
    return float(np.median(usable))


def _observed_tick_spacing(
    points: np.ndarray,
    inliers: np.ndarray,
    *,
    primary: int,
) -> float:
    """Infer the 1 mm tick period directly from detected ruler endpoints."""
    coordinates = np.sort(points[inliers, primary])
    coordinates = coordinates[np.r_[True, np.diff(coordinates) > 2.5]]
    if len(coordinates) < 6:
        raise RuntimeError("not enough tick coordinates")

    gaps = np.diff(coordinates)
    maximum_gap = max(8.0, float(coordinates[-1] - coordinates[0]) / 40.0)
    usable = gaps[(gaps >= 3.0) & (gaps <= maximum_gap)]
    if len(usable) < 5:
        raise RuntimeError("not enough adjacent tick gaps")

    best_spacing = None
    best_score = -math.inf
    for candidate in np.unique(usable):
        ratios = usable / candidate
        multiples = np.rint(ratios)
        valid = (multiples >= 1) & (multiples <= 3)
        residuals = np.abs(ratios - multiples)
        score = float(
            np.sum(
                np.where(
                    valid,
                    np.exp(-((residuals / 0.12) ** 2)) / np.maximum(multiples, 1),
                    0.0,
                )
            )
        )
        if score > best_score:
            best_score = score
            best_spacing = float(candidate)

    if best_spacing is None:
        raise RuntimeError("could not infer tick spacing")
    ratios = usable / best_spacing
    multiples = np.rint(ratios)
    aligned = (
        (multiples >= 1)
        & (multiples <= 3)
        & (np.abs(ratios - multiples) <= 0.20)
    )
    estimates = usable[aligned] / multiples[aligned]
    if len(estimates) < 5:
        raise RuntimeError("tick spacing is not stable")
    return float(np.median(estimates))


def _fitted_lattice(
    coordinates: np.ndarray,
    expected_spacing: float,
) -> tuple[float, float]:
    """在期望间距 ±8% 内找最佳等距格点的（相位，间距）。"""
    candidates = np.linspace(
        expected_spacing * 0.92,
        expected_spacing * 1.08,
        1601,
    )
    angles = 2 * np.pi * coordinates[None, :] / candidates[:, None]
    means = np.mean(np.exp(1j * angles), axis=1)
    best = int(np.argmax(np.abs(means)))
    spacing = float(candidates[best])
    phase = float((np.angle(means[best]) % (2 * np.pi)) * spacing / (2 * np.pi))
    return phase, spacing


def _tick_strength(
    gray: np.ndarray,
    coordinate: float,
    *,
    line_point: np.ndarray,
    line_direction: np.ndarray,
    top: bool,
) -> float:
    height, width = gray.shape
    if top:
        center = round(coordinate)
        if center < 8 or center + 8 >= width:
            return 0.0
        distance = (coordinate - line_point[0]) / line_direction[0]
        endpoint = line_point[1] + distance * line_direction[1]
        start = max(0, round(endpoint) - int(height * 0.07))
        end = min(height, round(endpoint) + 6)
        center_values = gray[start:end, center - 1 : center + 2].mean(axis=1)
        first_background = gray[start:end, center - 7 : center - 4].mean(axis=1)
        second_background = gray[start:end, center + 4 : center + 7].mean(axis=1)
    else:
        center = round(coordinate)
        if center < 8 or center + 8 >= height:
            return 0.0
        distance = (coordinate - line_point[1]) / line_direction[1]
        endpoint = line_point[0] + distance * line_direction[0]
        start = max(0, round(endpoint) - int(width * 0.07))
        end = min(width, round(endpoint) + 6)
        center_values = gray[center - 1 : center + 2, start:end].mean(axis=0)
        first_background = gray[center - 7 : center - 4, start:end].mean(axis=0)
        second_background = gray[center + 4 : center + 7, start:end].mean(axis=0)

    contrast = np.maximum(first_background, second_background) - center_values
    contrast = np.convolve(contrast, np.ones(3, dtype=np.float32) / 3, mode="same")
    threshold = max(7.0, float(np.percentile(contrast, 90)) * 0.22)
    active = (contrast >= threshold).astype(np.uint8)
    active = cv2.morphologyEx(
        active.reshape(-1, 1),
        cv2.MORPH_CLOSE,
        np.ones((3, 1), dtype=np.uint8),
    ).reshape(-1)
    padded = np.pad(active.astype(np.int8), (1, 1))
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    endpoint_index = round(endpoint) - start
    lengths = [
        run_end - run_start
        for run_start, run_end in zip(starts, ends)
        if run_end - run_start >= 4 and abs((run_end - 1) - endpoint_index) <= 12
    ]
    return float(max(lengths, default=0))


def _scale_span(
    gray: np.ndarray,
    points: np.ndarray,
    inliers: np.ndarray,
    *,
    line_point: np.ndarray,
    line_direction: np.ndarray,
    top: bool,
    expected_spacing: float,
    span_mm: int,
) -> tuple[float, float, float, int, float, float]:
    """在指定毫米跨度内找最优窗口，返回（起点，终点，间距，支撑数，首尾强度）。"""
    primary = 0 if top else 1
    size = gray.shape[1] if top else gray.shape[0]
    phase, spacing = _fitted_lattice(
        points[inliers, primary],
        expected_spacing=expected_spacing,
    )
    coordinates = points[:, primary]
    indices = np.round((coordinates - phase) / spacing).astype(int)
    residuals = np.abs(coordinates - (phase + indices * spacing))
    aligned_indices = indices[residuals <= spacing * 0.28]
    support = {
        index: int(np.count_nonzero(aligned_indices == index))
        for index in np.unique(aligned_indices)
    }

    minimum_index = math.ceil((0 - phase) / spacing)
    maximum_index = math.floor(((size - 1) - phase) / spacing)
    strengths = {
        index: _tick_strength(
            gray,
            phase + index * spacing,
            line_point=line_point,
            line_direction=line_direction,
            top=top,
        )
        for index in range(minimum_index, maximum_index + 1)
    }

    best_start = None
    best_score = -math.inf
    for start_index in range(minimum_index, maximum_index - span_mm + 1):
        end_index = start_index + span_mm
        interval = range(start_index, end_index + 1)
        supported = sum(index in support for index in interval)
        raw_support = sum(support.get(index, 0) for index in interval)
        visible = sum(strengths[index] >= 4 for index in interval)
        darkness = sum(min(strengths[index], 20.0) for index in interval)
        major = sum(
            min(strengths[index], 45.0)
            for index in range(start_index, end_index + 1, 10)
        )
        endpoints = strengths[start_index] + strengths[end_index]
        score = (
            supported * 5.0
            + raw_support * 2.0
            + visible * 3.0
            + darkness * 0.2
            + major * 1.2
            + endpoints * 4.0
        )
        if score > best_score:
            best_score = score
            best_start = start_index

    if best_start is None:
        raise RuntimeError("could not find a complete ruler span")
    best_end = best_start + span_mm
    return (
        phase + best_start * spacing,
        phase + best_end * spacing,
        spacing,
        sum(index in support for index in range(best_start, best_end + 1)),
        strengths[best_start],
        strengths[best_end],
    )


@dataclass(frozen=True)
class RulerGeometry:
    """刻度检测结果，坐标为原图（未旋转）像素坐标。"""

    origin: tuple[float, float]
    rotation_degrees: float
    spacing_x: float
    spacing_y: float
    span_mm: int
    top_support: int
    left_support: int
    top_inlier_ratio: float
    left_inlier_ratio: float

    @property
    def healthy(self) -> bool:
        minimum_support = math.ceil((self.span_mm + 1) * HEALTH_MIN_SUPPORT_RATIO)
        return (
            self.spacing_x > 0
            and self.spacing_y > 0
            and self.top_inlier_ratio >= HEALTH_MIN_INLIER_RATIO
            and self.left_inlier_ratio >= HEALTH_MIN_INLIER_RATIO
            and self.top_support >= minimum_support
            and self.left_support >= minimum_support
        )


def _read_dpi(image: Image.Image) -> tuple[int, int]:
    raw_dpi = image.info.get("dpi")
    if isinstance(raw_dpi, tuple) and len(raw_dpi) >= 2:
        try:
            return int(round(float(raw_dpi[0]))), int(round(float(raw_dpi[1])))
        except (TypeError, ValueError):
            pass
    return 0, 0


def detect_ruler(
    image: Image.Image,
    dpi: tuple[int, int] | None = None,
    *,
    span_mm: int | None = None,
    coarse_search_ratio: float | None = None,
) -> RulerGeometry | None:
    """检测图片中的尺子刻度。

    返回 RulerGeometry（坐标为原图像素坐标），失败返回 None。
    检测失败时会依次尝试常见 dpi 取值（用于 dpi 缺失或错误的场景）。
    """
    scale = min(1.0, MAX_ANALYSIS_SIZE / max(image.width, image.height))
    analysis = image.convert("L").resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.BILINEAR,
    )
    gray = np.asarray(analysis, dtype=np.uint8)
    spans = (span_mm,) if span_mm is not None else SUPPORTED_RULER_SPANS_MM
    if any(value <= 0 for value in spans):
        raise ValueError("ruler span must be positive")

    search_ratio = (
        COARSE_SEARCH_MAX_RATIO
        if coarse_search_ratio is None
        else float(coarse_search_ratio)
    )
    direct = _detect_with_dpi(gray, scale, None, spans, coarse_search_ratio=search_ratio)
    if direct is not None and direct.healthy:
        return direct

    candidates = []
    if dpi is not None and dpi[0] > 0 and dpi[1] > 0:
        candidates.append(dpi)
    candidates.extend((value, value) for value in _DPI_CANDIDATES)

    seen = set()
    results = [direct] if direct is not None else []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        geometry = _detect_with_dpi(
            gray,
            scale,
            candidate,
            spans,
            coarse_search_ratio=search_ratio,
        )
        if geometry is not None:
            results.append(geometry)
    if not results:
        return None
    return max(
        results,
        key=lambda item: (
            item.healthy,
            item.span_mm,
            min(item.top_support, item.left_support) / (item.span_mm + 1),
            item.top_support + item.left_support,
            item.top_inlier_ratio + item.left_inlier_ratio,
        ),
    )


def _detect_with_dpi(
    gray: np.ndarray,
    scale: float,
    dpi: tuple[int, int] | None,
    spans: tuple[int, ...],
    *,
    coarse_search_ratio: float,
) -> RulerGeometry | None:
    height, width = gray.shape
    coarse = coarse_origin(gray, max_search_ratio=coarse_search_ratio)
    top_points = tick_endpoints(gray, coarse, top=True)
    left_points = tick_endpoints(gray, coarse, top=False)
    if len(top_points) < MIN_ENDPOINTS or len(left_points) < MIN_ENDPOINTS:
        return None
    try:
        top_point, top_direction, top_inliers = fit_endpoint_line(
            top_points,
            horizontal=True,
            size=width,
            min_secondary_at_center=coarse[1] - int(height * 0.10),
            max_secondary_at_center=coarse[1] + max(2, int(height * 0.01)),
        )
        left_point, left_direction, left_inliers = fit_endpoint_line(
            left_points,
            horizontal=False,
            size=height,
            min_secondary_at_center=coarse[0] - int(width * 0.10),
            max_secondary_at_center=coarse[0] + max(2, int(width * 0.01)),
        )
    except RuntimeError:
        return None

    try:
        if dpi is None:
            expected_x = _observed_tick_spacing(top_points, top_inliers, primary=0)
            expected_y = _observed_tick_spacing(left_points, left_inliers, primary=1)
        else:
            expected_x = float(dpi[0]) / 25.4 * scale
            expected_y = float(dpi[1]) / 25.4 * scale
            _tick_spacing(top_points, top_inliers, primary=0, expected=expected_x)
            _tick_spacing(left_points, left_inliers, primary=1, expected=expected_y)
    except RuntimeError:
        return None

    origin = intersection((top_point, top_direction), (left_point, left_direction))
    results = []
    for ruler_span in spans:
        try:
            _, _, spacing_x, top_support, _, _ = _scale_span(
                gray,
                top_points,
                top_inliers,
                line_point=top_point,
                line_direction=top_direction,
                top=True,
                expected_spacing=expected_x,
                span_mm=ruler_span,
            )
            _, _, spacing_y, left_support, _, _ = _scale_span(
                gray,
                left_points,
                left_inliers,
                line_point=left_point,
                line_direction=left_direction,
                top=False,
                expected_spacing=expected_y,
                span_mm=ruler_span,
            )
        except RuntimeError:
            spacing_x = expected_x
            spacing_y = expected_y
            top_support = 0
            left_support = 0
        results.append(
            RulerGeometry(
                origin=(origin[0] / scale, origin[1] / scale),
                rotation_degrees=line_angle(top_direction, horizontal=True),
                spacing_x=spacing_x / scale,
                spacing_y=spacing_y / scale,
                span_mm=ruler_span,
                top_support=top_support,
                left_support=left_support,
                top_inlier_ratio=float(top_inliers.mean()),
                left_inlier_ratio=float(left_inliers.mean()),
            )
        )
    return max(
        results,
        key=lambda item: (
            item.healthy,
            item.span_mm,
            min(item.top_support, item.left_support) / (item.span_mm + 1),
            item.top_support + item.left_support,
        ),
    )
