from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from color_card_toolkit.core.models import OcrBlock, ParsedColorCodes

_NOISE_KEYWORDS = (
    "width",
    "thickness",
    "instock",
    "global recycled",
    "standard",
    "description",
    "emboss",
    "size",
    "货号",
    "货名",
    "规格",
    "现货",
    "现货版",
)


@dataclass(frozen=True)
class _Cluster:
    blocks: list[OcrBlock]
    axis_value: float


def normalize_text(text: str) -> str:
    translation = str.maketrans(
        {
            "（": "(",
            "）": ")",
            "：": ":",
            "，": ",",
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
        }
    )
    return re.sub(r"\s+", " ", text.translate(translation).strip())


def parse_color_codes(blocks: list[OcrBlock]) -> ParsedColorCodes:
    candidates = [_clean_block(block) for block in blocks if _is_candidate_code(block.text)]
    if not candidates:
        return ParsedColorCodes(codes=[], orientation="unknown", warnings=["未识别到色号"])

    rows = _cluster_blocks(candidates, "y")
    best_row = _best_cluster(rows)
    columns = [cluster for cluster in _cluster_blocks(candidates, "x") if len(cluster.blocks) >= 3]
    best_columns = sorted(columns, key=lambda cluster: len(cluster.blocks), reverse=True)[:2]

    row_count = len(best_row.blocks) if best_row else 0
    column_count = sum(len(cluster.blocks) for cluster in best_columns)

    if column_count >= 6 and column_count > row_count + 2:
        ordered = _ordered_vertical(best_columns)
        orientation = "vertical"
    elif best_row and row_count >= 2:
        ordered = sorted(best_row.blocks, key=lambda block: block.center_x)
        orientation = "horizontal"
    elif best_columns:
        ordered = _ordered_vertical(best_columns)
        orientation = "vertical"
    else:
        ordered = sorted(candidates, key=lambda block: (block.center_y, block.center_x))
        orientation = "unknown"

    codes = _expand_merged_numeric_runs([normalize_text(block.text) for block in ordered])
    codes = _drop_outlier_codes(codes)
    missing = find_missing_numeric_codes(codes)
    warnings: list[str] = []
    if missing:
        warnings.append(f"疑似缺少：{', '.join(missing)}")

    return ParsedColorCodes(codes=codes, orientation=orientation, missing_codes=missing, warnings=warnings)


def find_missing_numeric_codes(codes: list[str]) -> list[str]:
    numeric_codes = [code for code in codes if code.isdigit()]
    if len(numeric_codes) < 3 or len(numeric_codes) != len(codes):
        return []

    numbers = sorted({int(code) for code in numeric_codes})
    if not numbers:
        return []

    width = max(len(code) for code in numeric_codes)
    missing = [number for number in range(numbers[0], numbers[-1] + 1) if number not in numbers]
    return [str(number).zfill(width) for number in missing]


def _clean_block(block: OcrBlock) -> OcrBlock:
    return OcrBlock(text=normalize_text(block.text), confidence=block.confidence, box=block.box)


def _is_candidate_code(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(keyword in lowered for keyword in _NOISE_KEYWORDS):
        return False
    if re.search(r"\b\d+(?:\.\d+)?\s*(mm|cm|inch|in)\b", lowered):
        return False
    if normalized.isdigit():
        return len(normalized) <= 24
    if len(normalized) > 8:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", normalized))


def _expand_merged_numeric_runs(codes: list[str]) -> list[str]:
    fallback_width = _fallback_expansion_width(codes)

    expanded: list[str] = []
    for code in codes:
        sequential_parts = _split_by_expected_sequence(code, expanded)
        if sequential_parts:
            expanded.extend(sequential_parts)
        elif fallback_width >= 2 and code.isdigit() and len(code) > fallback_width and len(code) % fallback_width == 0:
            expanded.extend(code[index : index + fallback_width] for index in range(0, len(code), fallback_width))
        else:
            expanded.append(code)
    return expanded


def _fallback_expansion_width(codes: list[str]) -> int:
    numeric_widths = [len(code) for code in codes if code.isdigit() and 1 <= len(code) <= 3]
    if not numeric_widths:
        return 0
    multi_digit_widths = [width for width in numeric_widths if width >= 2]
    if multi_digit_widths:
        return int(median(multi_digit_widths))
    return int(median(numeric_widths))


def _split_by_expected_sequence(code: str, previous_codes: list[str]) -> list[str]:
    if not code.isdigit():
        return []

    previous_code = next((item for item in reversed(previous_codes) if item.isdigit()), "")
    if not previous_code:
        return []

    previous_number = int(previous_code)
    expected_number = previous_number + 1
    expected_width = len(previous_code) if previous_code.startswith("0") else 0
    first_expected_text = _format_expected_number(expected_number, expected_width)
    if len(code) < max(3, len(first_expected_text) * 2):
        return []

    remaining = code
    parts: list[str] = []
    while remaining:
        expected_text = _format_expected_number(expected_number, expected_width)
        if not remaining.startswith(expected_text):
            return []
        parts.append(expected_text)
        remaining = remaining[len(expected_text) :]
        expected_number += 1
    return parts


def _format_expected_number(number: int, width: int) -> str:
    return str(number).zfill(width) if width else str(number)


def _cluster_blocks(blocks: list[OcrBlock], axis: str) -> list[_Cluster]:
    if not blocks:
        return []
    sizes = [block.height if axis == "y" else block.width for block in blocks]
    tolerance = max(12.0, median(sizes) * 1.4)
    sorted_blocks = sorted(blocks, key=lambda block: block.center_y if axis == "y" else block.center_x)

    clusters: list[list[OcrBlock]] = []
    for block in sorted_blocks:
        value = block.center_y if axis == "y" else block.center_x
        if not clusters:
            clusters.append([block])
            continue
        current = clusters[-1]
        current_center = sum(
            item.center_y if axis == "y" else item.center_x for item in current
        ) / len(current)
        if abs(value - current_center) <= tolerance:
            current.append(block)
        else:
            clusters.append([block])

    result: list[_Cluster] = []
    for cluster in clusters:
        axis_value = sum(item.center_y if axis == "y" else item.center_x for item in cluster) / len(cluster)
        result.append(_Cluster(blocks=cluster, axis_value=axis_value))
    return result


def _best_cluster(clusters: list[_Cluster]) -> _Cluster | None:
    if not clusters:
        return None
    return max(clusters, key=lambda cluster: (len(cluster.blocks), _cluster_span(cluster.blocks, "x")))


def _cluster_span(blocks: list[OcrBlock], axis: str) -> float:
    if axis == "x":
        return max(block.max_x for block in blocks) - min(block.min_x for block in blocks)
    return max(block.max_y for block in blocks) - min(block.min_y for block in blocks)


def _ordered_vertical(columns: list[_Cluster]) -> list[OcrBlock]:
    ordered: list[OcrBlock] = []
    for column in sorted(columns, key=lambda cluster: cluster.axis_value):
        ordered.extend(sorted(column.blocks, key=lambda block: block.center_y))
    return ordered


def _drop_outlier_codes(codes: list[str]) -> list[str]:
    if not codes:
        return codes
    numeric_codes = [code for code in codes if code.isdigit()]
    if len(numeric_codes) >= 2:
        common_width = int(median([len(code) for code in numeric_codes]))
        if common_width <= 2:
            return [code for code in codes if not (code.isdigit() and len(code) > 2)]
    return codes
