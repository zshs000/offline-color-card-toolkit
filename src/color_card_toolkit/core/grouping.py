from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from color_card_toolkit.core.models import (
    GroupedColorCard,
    GroupingResult,
    ImageRecognitionResult,
    ParsedGroupName,
    SkippedGroup,
)

_TRAILING_SEQUENCE_RE = re.compile(r"^(?P<base>.+?)\s*[\(（]\s*(?P<seq>\d+)\s*[\)）]\s*$")


def parse_group_name(raw_name: str) -> ParsedGroupName:
    normalized = (
        raw_name.strip()
        .replace("（", "(")
        .replace("）", ")")
        .replace("\u3000", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized)
    match = _TRAILING_SEQUENCE_RE.match(normalized)
    if match:
        return ParsedGroupName(
            raw_name=raw_name,
            base_name=match.group("base").strip(),
            sequence=int(match.group("seq")),
            explicit_sequence=True,
        )
    return ParsedGroupName(
        raw_name=raw_name,
        base_name=normalized,
        sequence=1,
        explicit_sequence=False,
    )


def build_recognition_result(
    image_path: str | Path,
    raw_name: str,
    color_codes: list[str],
    *,
    missing_codes: list[str] | None = None,
    warnings: list[str] | None = None,
    confidence: float = 0.0,
) -> ImageRecognitionResult:
    parsed = parse_group_name(raw_name)
    return ImageRecognitionResult(
        image_path=Path(image_path),
        raw_name=raw_name,
        base_name=parsed.base_name,
        sequence=parsed.sequence,
        color_codes=color_codes,
        explicit_sequence=parsed.explicit_sequence,
        missing_codes=missing_codes or [],
        warnings=warnings or [],
        confidence=confidence,
    )


def group_recognition_results(results: list[ImageRecognitionResult]) -> GroupingResult:
    valid_groups: list[GroupedColorCard] = []
    skipped_groups: list[SkippedGroup] = []

    explicit_groups: dict[str, list[ImageRecognitionResult]] = defaultdict(list)
    implicit_results: list[ImageRecognitionResult] = []

    for result in results:
        if not result.participate:
            continue
        if not result.base_name.strip():
            skipped_groups.append(SkippedGroup("(空组名)", f"{result.image_path.name} 组名为空"))
            continue
        if not result.color_codes:
            skipped_groups.append(SkippedGroup(result.base_name, f"{result.image_path.name} 色号为空"))
            continue
        if result.explicit_sequence:
            explicit_groups[result.base_name].append(result)
        else:
            implicit_results.append(result)

    for result in implicit_results:
        valid_groups.append(GroupedColorCard(result.base_name, list(result.color_codes)))

    for base_name, group_items in explicit_groups.items():
        sequence_map: dict[int, ImageRecognitionResult] = {}
        duplicates: list[int] = []
        for item in group_items:
            if item.sequence in sequence_map:
                duplicates.append(item.sequence)
            sequence_map[item.sequence] = item

        if duplicates:
            skipped_groups.append(
                SkippedGroup(base_name, f"序号重复：{', '.join(str(item) for item in sorted(set(duplicates)))}")
            )
            continue

        sequences = sorted(sequence_map)
        if not sequences or sequences[0] != 1:
            skipped_groups.append(SkippedGroup(base_name, "缺少第1张"))
            continue

        expected = list(range(1, sequences[-1] + 1))
        missing = [number for number in expected if number not in sequence_map]
        if missing:
            skipped_groups.append(
                SkippedGroup(base_name, f"缺少第{', '.join(str(number) for number in missing)}张")
            )
            continue

        merged_codes: list[str] = []
        for sequence in expected:
            merged_codes.extend(sequence_map[sequence].color_codes)
        valid_groups.append(GroupedColorCard(base_name, merged_codes))

    return GroupingResult(valid_groups=valid_groups, skipped_groups=skipped_groups)

