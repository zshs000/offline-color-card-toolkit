from __future__ import annotations

from color_card_toolkit.core.color_code_parser import find_missing_numeric_codes, parse_color_codes
from color_card_toolkit.core.models import OcrBlock


def block(text: str, x: float, y: float, w: float = 20, h: float = 12) -> OcrBlock:
    return OcrBlock(
        text=text,
        confidence=0.98,
        box=((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
    )


def test_horizontal_codes_are_sorted_left_to_right_and_noise_is_filtered() -> None:
    blocks = [
        block("2014", 1200, 60, 80, 30),
        block('Width:52" Thickness:0.9mm', 1200, 130, 220, 20),
        block("01", 10, 250),
        block("02", 110, 252),
        block("03", 210, 249),
        block("04", 310, 250),
        block("05", 410, 251),
        block("06", 510, 250),
        block("08", 610, 250),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "horizontal"
    assert parsed.codes == ["01", "02", "03", "04", "05", "06", "08"]
    assert parsed.missing_codes == ["07"]


def test_horizontal_parser_splits_merged_two_digit_numeric_run() -> None:
    blocks = [
        block("2014", 1200, 60, 80, 30),
        block("10", 810, 250),
        block("11", 910, 250),
        block("121314151617", 1030, 250, 588, 39),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.codes == ["10", "11", "12", "13", "14", "15", "16", "17"]


def test_horizontal_parser_does_not_split_two_digit_codes_into_single_digits() -> None:
    blocks = [block(str(number), 20 + index * 45, 250) for index, number in enumerate(range(1, 10))]
    blocks.extend(
        [
            block("10111213141516", 430, 250, 300, 12),
            block("17181920212223", 750, 250, 300, 12),
            block("242526272829", 1070, 250, 260, 12),
        ]
    )

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number) for number in range(1, 30)]


def test_vertical_codes_are_sorted_left_column_then_right_column() -> None:
    blocks = [block(str(number), 80, 20 + index * 30) for index, number in enumerate(range(47, 70))]
    blocks.extend(block(str(number), 880, 20 + index * 30) for index, number in enumerate(range(70, 93)))
    blocks.extend(
        [
            block("Q弹雅镜", 720, 80, 120, 28),
            block("货号", 690, 20, 60, 20),
        ]
    )

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "vertical"
    assert parsed.codes[:3] == ["47", "48", "49"]
    assert parsed.codes[22:25] == ["69", "70", "71"]
    assert parsed.codes[-1] == "92"


def test_vertical_parser_keeps_only_code_columns_with_alphanumeric_codes() -> None:
    left_codes = ["1A"] + [str(number) for number in range(1, 26)]
    right_codes = [str(number) for number in range(26, 48)] + ["A1", "A2", "A3"]
    blocks = [block(code, 130, 210 + index * 30) for index, code in enumerate(left_codes)]
    blocks.extend(block(code, 1160, 200 + index * 30) for index, code in enumerate(right_codes))
    blocks.extend(
        [
            block("百香果", 115, 60, 120, 35),
            block("百香果", 1010, 60, 120, 35),
            block("货名", 900, 80, 50, 20),
            block("规格", 900, 155, 50, 20),
            block("专营各类:", 145, 1710, 160, 35),
            block("鞋材", 365, 1710, 80, 35),
            block("王袋", 560, 1710, 80, 35),
            block("家具等PU", 765, 1710, 130, 35),
            block("面料", 1010, 1710, 80, 35),
        ]
    )

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "vertical"
    assert parsed.codes == left_codes + right_codes


def test_missing_numeric_codes_preserve_width() -> None:
    assert find_missing_numeric_codes(["01", "02", "04"]) == ["03"]
