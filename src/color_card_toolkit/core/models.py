from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

Point = tuple[float, float]
Box = tuple[Point, Point, Point, Point]


@dataclass(frozen=True)
class OcrBlock:
    text: str
    confidence: float
    box: Box

    @property
    def min_x(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def max_x(self) -> float:
        return max(point[0] for point in self.box)

    @property
    def min_y(self) -> float:
        return min(point[1] for point in self.box)

    @property
    def max_y(self) -> float:
        return max(point[1] for point in self.box)

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass(frozen=True)
class ParsedColorCodes:
    codes: list[str]
    orientation: str
    missing_codes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedGroupName:
    raw_name: str
    base_name: str
    sequence: int
    explicit_sequence: bool


@dataclass
class ImageRecognitionResult:
    image_path: Path
    raw_name: str
    base_name: str
    sequence: int
    color_codes: list[str]
    explicit_sequence: bool = False
    participate: bool = True
    missing_codes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    recognition_source: str = ""
    api_retry_count: int = 0
    api_prompt_tokens: int = 0
    api_completion_tokens: int = 0
    api_total_tokens: int = 0
    api_image_tokens: int = 0
    api_text_tokens: int = 0
    api_estimated_cost_rmb: float = 0.0
    api_elapsed_seconds: float = 0.0
    api_model: str = ""

    @property
    def display_missing_codes(self) -> str:
        return ", ".join(self.missing_codes)

    @property
    def display_color_codes(self) -> str:
        return ", ".join(self.color_codes)


@dataclass(frozen=True)
class GroupedColorCard:
    base_name: str
    color_codes: list[str]

    @property
    def page_count(self) -> int:
        if not self.color_codes:
            return 0
        return (len(self.color_codes) + 23) // 24


@dataclass(frozen=True)
class SkippedGroup:
    base_name: str
    reason: str


@dataclass(frozen=True)
class GroupingResult:
    valid_groups: list[GroupedColorCard]
    skipped_groups: list[SkippedGroup]


def normalize_code_list(codes: Sequence[str] | str) -> list[str]:
    if isinstance(codes, str):
        raw_parts = codes.replace("，", ",").replace("、", ",").split(",")
    else:
        raw_parts = list(codes)
    return [part.strip() for part in raw_parts if str(part).strip()]
