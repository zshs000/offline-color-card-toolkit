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
_MAX_MISSING_RANGE_WIDTH = 300


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

    vertical_candidates = [_clean_vertical_block(block) for block in blocks if _is_vertical_code_candidate(block.text)]
    vertical_columns = _best_vertical_columns(vertical_candidates)
    rows = _cluster_blocks(candidates, "y")
    best_row = _best_cluster(rows)
    dense_row = _best_dense_numeric_row(rows)
    columns = [cluster for cluster in _cluster_blocks(candidates, "x") if len(cluster.blocks) >= 3]
    best_columns = sorted(columns, key=lambda cluster: len(cluster.blocks), reverse=True)[:2]

    row_count = len(best_row.blocks) if best_row else 0
    column_count = sum(len(cluster.blocks) for cluster in best_columns)

    if _should_use_vertical_columns(vertical_columns, row_count):
        codes = _codes_from_vertical_columns(vertical_columns)
        orientation = "vertical"
    elif column_count >= 6 and column_count > row_count + 2:
        codes = _codes_from_vertical_columns(best_columns)
        orientation = "vertical"
    elif dense_row:
        codes = _codes_from_dense_numeric_row(dense_row)
        orientation = "horizontal"
    elif best_row and row_count >= 2:
        ordered = sorted(best_row.blocks, key=lambda block: block.center_x)
        codes = _codes_from_horizontal_row(ordered)
        orientation = "horizontal"
    elif best_columns:
        codes = _codes_from_vertical_columns(best_columns)
        orientation = "vertical"
    else:
        ordered = sorted(candidates, key=lambda block: (block.center_y, block.center_x))
        codes = _expand_merged_numeric_runs([normalize_text(block.text) for block in ordered])
        orientation = "unknown"

    codes = _repair_single_numeric_sequence_outliers(codes)
    codes = _drop_outlier_codes(codes)
    missing = find_missing_numeric_codes(codes)
    warnings: list[str] = []
    if missing:
        warnings.append(f"疑似缺少：{', '.join(missing)}")

    return ParsedColorCodes(codes=codes, orientation=orientation, missing_codes=missing, warnings=warnings)


def find_missing_numeric_codes(codes: list[str]) -> list[str]:
    numeric_codes = [code for code in codes if code.isdigit()]
    if len(numeric_codes) < 3:
        return []

    numbers = sorted({int(code) for code in numeric_codes})
    if not numbers:
        return []

    width = _missing_code_width(numeric_codes)
    if numbers[-1] - numbers[0] + 1 > _MAX_MISSING_RANGE_WIDTH:
        return []
    missing = [number for number in range(numbers[0], numbers[-1] + 1) if number not in numbers]
    return [str(number).zfill(width) for number in missing]


def _missing_code_width(numeric_codes: list[str]) -> int:
    if any(len(code) > 1 and code.startswith("0") for code in numeric_codes):
        return max(len(code) for code in numeric_codes)
    return 0


def _clean_block(block: OcrBlock) -> OcrBlock:
    return OcrBlock(text=_normalize_code_candidate_text(block.text), confidence=block.confidence, box=block.box)


def _clean_vertical_block(block: OcrBlock) -> OcrBlock:
    return OcrBlock(text=_normalize_vertical_code_text(block.text), confidence=block.confidence, box=block.box)


def _is_candidate_code(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(keyword in lowered for keyword in _NOISE_KEYWORDS):
        return False
    if re.search(r"\b\d+(?:\.\d+)?\s*(mm|cm|inch|in)\b", lowered):
        return False
    if _is_dense_numeric_candidate(normalized):
        return True
    if normalized.isdigit():
        return len(normalized) <= 24
    if len(normalized) > 8:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", normalized))


def _normalize_code_candidate_text(text: str) -> str:
    normalized = normalize_text(text)
    if _is_dense_numeric_candidate(normalized):
        return re.sub(r"\D", "", normalized)
    return normalized


def _is_dense_numeric_candidate(text: str) -> bool:
    normalized = normalize_text(text)
    digits = re.sub(r"\D", "", normalized)
    if len(digits) < 6 or len(digits) > 80:
        return False
    return bool(re.fullmatch(r"[\d\s.,，。:：;；\\-_/]+", normalized))


def _is_vertical_code_candidate(text: str) -> bool:
    normalized = _normalize_vertical_code_text(text)
    if not normalized:
        return False
    if any(keyword in normalized.lower() for keyword in _NOISE_KEYWORDS):
        return False
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return False
    return bool(re.fullmatch(r"(?:[A-Z]{0,2}\d{1,3}[A-Z]{0,2}|\d{1,3})", normalized))


def _normalize_vertical_code_text(text: str) -> str:
    normalized = normalize_text(text).upper().replace(" ", "")
    if re.search(r"\d", normalized):
        normalized = normalized.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"}))
    return re.sub(r"[^0-9A-Z\u4e00-\u9fff]", "", normalized)


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
        return _infer_dense_merged_width(codes)
    multi_digit_widths = [width for width in numeric_widths if width >= 2]
    if multi_digit_widths:
        return int(median(multi_digit_widths))
    return int(median(numeric_widths))


def _infer_dense_merged_width(codes: list[str]) -> int:
    numeric_codes = [code for code in codes if code.isdigit()]
    if not numeric_codes:
        return 0
    if any(_is_zero_padded_merged_run(code) for code in numeric_codes):
        return 2

    for width in (2, 3):
        if any(len(code) % width != 0 for code in numeric_codes):
            continue
        parts = [code[index : index + width] for code in numeric_codes for index in range(0, len(code), width)]
        if _looks_like_dense_sequence(parts):
            return width
    return 0


def _is_zero_padded_merged_run(code: str) -> bool:
    return code.isdigit() and code.startswith("0") and len(code) >= 6 and len(code) % 2 == 0


def _best_dense_numeric_row(rows: list[_Cluster]) -> _Cluster | None:
    scored: list[tuple[int, float, _Cluster]] = []
    for row in rows:
        ordered = sorted(row.blocks, key=lambda block: block.center_x)
        codes = _expand_merged_numeric_runs([normalize_text(block.text) for block in ordered])
        numeric_codes = [code for code in codes if code.isdigit() and len(code) <= 3]
        if len(numeric_codes) < 6:
            continue
        if not (_looks_like_dense_sequence(numeric_codes) or _looks_like_gapped_sequence(numeric_codes)):
            continue
        scored.append((len(numeric_codes), _cluster_span(row.blocks, "x"), row))
    if not scored:
        return None
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def _looks_like_gapped_sequence(parts: list[str]) -> bool:
    if len(parts) < 6 or not all(part.isdigit() for part in parts):
        return False
    numbers = [int(part) for part in parts]
    if numbers[0] > 3:
        return False
    if any(current <= previous for previous, current in zip(numbers, numbers[1:])):
        return False
    span = numbers[-1] - numbers[0] + 1
    return span <= len(numbers) + max(4, int(len(numbers) * 0.25))


def _codes_from_dense_numeric_row(row: _Cluster) -> list[str]:
    ordered = sorted(row.blocks, key=lambda block: block.center_x)
    numeric_blocks: list[OcrBlock] = []
    texts: list[str] = []
    for block in ordered:
        text = normalize_text(block.text)
        if not text.isdigit():
            continue
        numeric_blocks.append(block)
        texts.append(text)
    codes = _expand_merged_numeric_runs(texts)
    return _complete_horizontal_layout_gaps(numeric_blocks, codes)


def _codes_from_horizontal_row(blocks: list[OcrBlock]) -> list[str]:
    ordered = sorted(blocks, key=lambda block: block.center_x)
    codes = _expand_merged_numeric_runs([normalize_text(block.text) for block in ordered])
    return _complete_horizontal_layout_gaps(ordered, codes)


def _complete_horizontal_layout_gaps(blocks: list[OcrBlock], codes: list[str]) -> list[str]:
    if len(blocks) != len(codes) or len(codes) < 4:
        return codes
    if not all(code.isdigit() for code in codes):
        return codes

    numbers = [int(code) for code in codes]
    centers = [block.center_x for block in blocks]
    adjacent_gaps = [
        centers[index + 1] - centers[index]
        for index in range(len(numbers) - 1)
        if numbers[index + 1] - numbers[index] == 1 and centers[index + 1] > centers[index]
    ]
    if len(adjacent_gaps) < 2:
        return codes

    normal_gap = median(adjacent_gaps)
    if normal_gap <= 0:
        return codes

    completed: list[str] = [codes[0]]
    for index in range(len(codes) - 1):
        current_number = numbers[index]
        next_number = numbers[index + 1]
        number_gap = next_number - current_number
        pixel_gap = centers[index + 1] - centers[index]
        if 1 < number_gap <= 12 and _matches_missing_layout_slots(pixel_gap, normal_gap, number_gap):
            width = _sequence_width(codes[index], codes[index + 1])
            completed.extend(_format_expected_number(number, width) for number in range(current_number + 1, next_number))
        completed.append(codes[index + 1])
    return completed


def _matches_missing_layout_slots(pixel_gap: float, normal_gap: float, number_gap: int) -> bool:
    slot_gap = pixel_gap / normal_gap
    tolerance = max(0.45, number_gap * 0.25)
    return abs(slot_gap - number_gap) <= tolerance


def _looks_like_dense_sequence(parts: list[str]) -> bool:
    if len(parts) < 6 or not all(part.isdigit() for part in parts):
        return False

    numbers = [int(part) for part in parts]
    if any(current <= previous for previous, current in zip(numbers, numbers[1:])):
        return False

    span = numbers[-1] - numbers[0] + 1
    if span <= 0:
        return False
    return span <= len(numbers) + 3


def _repair_single_numeric_sequence_outliers(codes: list[str]) -> list[str]:
    repaired = list(codes)
    numeric_positions = [index for index, code in enumerate(repaired) if code.isdigit()]
    for position_index in range(1, len(numeric_positions) - 1):
        previous_index = numeric_positions[position_index - 1]
        current_index = numeric_positions[position_index]
        next_index = numeric_positions[position_index + 1]

        previous_code = repaired[previous_index]
        current_code = repaired[current_index]
        next_code = repaired[next_index]
        previous_number = int(previous_code)
        current_number = int(current_code)
        next_number = int(next_code)
        expected_number = previous_number + 1
        if next_number != expected_number + 1 or current_number == expected_number:
            continue
        if abs(current_number - expected_number) < 10:
            continue
        if len(current_code) > 3:
            continue
        repaired[current_index] = _format_expected_number(expected_number, _sequence_width(previous_code, next_code))
    return repaired


def _sequence_width(previous_code: str, next_code: str) -> int:
    if previous_code.startswith("0") or next_code.startswith("0"):
        return max(len(previous_code), len(next_code))
    return 0


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


def _best_vertical_columns(blocks: list[OcrBlock]) -> list[_Cluster]:
    columns = [
        cluster
        for cluster in _cluster_blocks(blocks, "x")
        if len(cluster.blocks) >= 3 and _cluster_span(cluster.blocks, "y") >= 30
    ]
    return sorted(columns, key=lambda cluster: len(cluster.blocks), reverse=True)[:2]


def _should_use_vertical_columns(columns: list[_Cluster], row_count: int) -> bool:
    column_count = sum(len(cluster.blocks) for cluster in columns)
    if column_count < 6:
        return False
    if len(columns) >= 2:
        return True
    return column_count > row_count + 2


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


def _codes_from_vertical_columns(columns: list[_Cluster]) -> list[str]:
    column_codes: list[list[str]] = []
    for column in sorted(columns, key=lambda cluster: cluster.axis_value):
        column_blocks = sorted(column.blocks, key=lambda block: block.center_y)
        column_codes.append(_repair_vertical_column_codes(column_blocks))
    column_codes = _complete_vertical_column_ranges(column_codes)
    codes: list[str] = []
    for codes_in_column in column_codes:
        codes.extend(codes_in_column)
    return _expand_merged_numeric_runs(codes)


def _repair_vertical_column_codes(blocks: list[OcrBlock]) -> list[str]:
    if not blocks:
        return []

    texts = [_normalize_vertical_code_text(block.text) for block in blocks]
    slots = _vertical_slots(blocks)
    sequence_start = _best_vertical_sequence_start(texts, slots)
    if sequence_start is None:
        return [text for text in texts if text]

    repaired: list[str] = []
    for text, slot in zip(texts, slots):
        if not text:
            continue
        expected_number = sequence_start + slot
        if expected_number <= 0:
            repaired.append(text)
            continue
        expected_text = str(expected_number)
        if _should_repair_vertical_code(text, expected_text):
            repaired.append(expected_text)
        else:
            repaired.append(text)
    return repaired


def _vertical_slots(blocks: list[OcrBlock]) -> list[int]:
    if len(blocks) <= 1:
        return list(range(len(blocks)))

    centers = [block.center_y for block in blocks]
    diffs = [current - previous for previous, current in zip(centers, centers[1:]) if current - previous > 4]
    if not diffs:
        return list(range(len(blocks)))

    gap = median(diffs)
    if gap <= 0:
        return list(range(len(blocks)))

    first = centers[0]
    slots: list[int] = []
    last_slot = -1
    for center in centers:
        slot = int(round((center - first) / gap))
        if slot <= last_slot:
            slot = last_slot + 1
        slots.append(slot)
        last_slot = slot
    return slots


def _best_vertical_sequence_start(texts: list[str], slots: list[int]) -> int | None:
    starts: dict[int, int] = {}
    numeric_count = 0
    for text, slot in zip(texts, slots):
        if not text.isdigit():
            continue
        numeric_count += 1
        value = int(text)
        starts[value - slot] = starts.get(value - slot, 0) + 1

    if numeric_count < 4 or not starts:
        return None

    start, score = max(starts.items(), key=lambda item: (item[1], -abs(item[0])))
    if score < max(3, int(numeric_count * 0.35)):
        return None
    return start


def _should_repair_vertical_code(text: str, expected_text: str) -> bool:
    if text == expected_text:
        return False
    if _is_protected_alphanumeric_code(text):
        return False
    if text.isdigit():
        return len(text) <= 3
    return bool(re.fullmatch(r"[0-9A-Z]{1,4}", text))


def _is_protected_alphanumeric_code(text: str) -> bool:
    return bool(re.fullmatch(r"(?:[A-Z]\d{1,3}|\d{1,3}[A-Z])", text))


def _complete_vertical_column_ranges(column_codes: list[list[str]]) -> list[list[str]]:
    if not column_codes:
        return []

    completed = [_complete_dense_numeric_range(codes) for codes in column_codes]
    if len(completed) < 2:
        return completed

    left_codes = completed[0]
    right_codes = completed[1]
    right_first = _first_numeric_value(right_codes)
    left_numbers = _numeric_values(left_codes)
    if right_first is None or len(left_numbers) < 8:
        return completed

    left_start = min(left_numbers)
    if left_start <= 2 or _has_leading_alphanumeric(left_codes):
        left_start = 1
    left_end = right_first - 1
    if left_end >= left_start and _range_density(left_numbers, left_start, left_end) >= 0.75:
        completed[0] = _complete_numeric_range_preserving_alphanumerics(left_codes, left_start, left_end)
    return completed


def _complete_dense_numeric_range(codes: list[str]) -> list[str]:
    numbers = _numeric_values(codes)
    if len(numbers) < 8:
        return codes
    start = min(numbers)
    end = max(numbers)
    if end <= start:
        return codes
    if _range_density(numbers, start, end) < 0.85:
        return codes
    return _complete_numeric_range_preserving_alphanumerics(codes, start, end)


def _complete_numeric_range_preserving_alphanumerics(codes: list[str], start: int, end: int) -> list[str]:
    before_first: list[str] = []
    after_number: dict[int, list[str]] = {}
    trailing: list[str] = []
    seen_alphanumeric: set[str] = set()

    for index, code in enumerate(codes):
        if code.isdigit():
            continue
        if code in seen_alphanumeric:
            continue
        seen_alphanumeric.add(code)
        previous_number = _previous_numeric_value(codes, index)
        if previous_number is None:
            before_first.append(code)
        elif start <= previous_number <= end:
            after_number.setdefault(previous_number, []).append(code)
        else:
            trailing.append(code)

    completed: list[str] = list(before_first)
    for number in range(start, end + 1):
        completed.append(str(number))
        completed.extend(after_number.get(number, []))
    completed.extend(trailing)
    return completed


def _numeric_values(codes: list[str]) -> list[int]:
    return [int(code) for code in codes if code.isdigit()]


def _first_numeric_value(codes: list[str]) -> int | None:
    for code in codes:
        if code.isdigit():
            return int(code)
    return None


def _previous_numeric_value(codes: list[str], index: int) -> int | None:
    for code in reversed(codes[:index]):
        if code.isdigit():
            return int(code)
    return None


def _has_leading_alphanumeric(codes: list[str]) -> bool:
    for code in codes:
        if code.isdigit():
            return False
        if code:
            return True
    return False


def _range_density(numbers: list[int], start: int, end: int) -> float:
    width = end - start + 1
    if width <= 0:
        return 0.0
    in_range = {number for number in numbers if start <= number <= end}
    return len(in_range) / width


def _drop_outlier_codes(codes: list[str]) -> list[str]:
    if not codes:
        return codes
    numeric_codes = [code for code in codes if code.isdigit()]
    if len(numeric_codes) >= 2:
        common_width = int(median([len(code) for code in numeric_codes]))
        if common_width <= 2:
            return [code for code in codes if not (code.isdigit() and len(code) > 2)]
    return codes
