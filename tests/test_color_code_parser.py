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


def test_horizontal_parser_splits_dense_merged_row_without_single_code_anchors() -> None:
    blocks = [
        block("505", 3800, 250, 280, 140),
        block('Width:52" Thickness:0.9mm', 3600, 440, 720, 60),
        block("010203040507080910", 65, 735, 1890, 100),
        block("111213141516171819", 1969, 737, 1920, 95),
        block("2021", 3909, 737, 400, 95),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "horizontal"
    assert parsed.codes == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
    ]
    assert parsed.missing_codes == ["06"]


def test_horizontal_parser_splits_dense_merged_row_with_punctuation_noise() -> None:
    blocks = [
        block("0102030405060708", 65, 735, 1590, 105),
        block("09", 1700, 735, 147, 77),
        block("10.1112131415161718192021", 1850, 735, 2426, 98),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "horizontal"
    assert parsed.codes == [str(number).zfill(2) for number in range(1, 22)]
    assert parsed.missing_codes == []


def test_horizontal_parser_keeps_single_long_dense_merged_row_over_page_noise() -> None:
    blocks = [
        block("520(1)", 200, 80, 180, 80),
        block("切", 900, 300, 40, 40),
        block("520", 3800, 250, 315, 140),
        block('Width:52" Thickness:0.9mm', 3600, 440, 730, 60),
        block("現貨版", 2100, 650, 500, 130),
        block("010203040506070809101112131415161718192021222324", 70, 735, 4245, 98),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.orientation == "horizontal"
    assert parsed.codes == [str(number).zfill(2) for number in range(1, 25)]
    assert parsed.missing_codes == []


def test_horizontal_parser_splits_single_zero_padded_merged_row_with_real_gaps() -> None:
    blocks = [
        block("1918(1)", 200, 80, 180, 80),
        block("現貨版", 2100, 250, 500, 130),
        block("0102030405060708091112131415161718202123242526282930", 60, 735, 4245, 98),
        block("1918", 3800, 250, 315, 140),
    ]

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "20",
        "21",
        "23",
        "24",
        "25",
        "26",
        "28",
        "29",
        "30",
    ]
    assert parsed.missing_codes == ["10", "19", "22", "27"]


def test_horizontal_parser_repairs_single_ocr_outlier_inside_dense_sequence() -> None:
    blocks = [block(str(number).zfill(2), 100 + index * 120, 250) for index, number in enumerate(range(1, 9))]
    blocks.append(block("60", 100 + 8 * 120, 250))
    blocks.extend(block(str(number), 100 + index * 120, 250) for index, number in enumerate(range(10, 14), start=9))

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number).zfill(2) for number in range(1, 14)]
    assert parsed.missing_codes == []


def test_horizontal_parser_completes_missing_codes_when_layout_gap_matches_slots() -> None:
    blocks = [block(str(number).zfill(2), 100 + index * 100, 250) for index, number in enumerate(range(1, 8))]
    blocks.append(block("12", 100 + 11 * 100, 250))

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number).zfill(2) for number in range(1, 13)]
    assert parsed.missing_codes == []


def test_horizontal_parser_does_not_complete_missing_code_without_layout_gap() -> None:
    blocks = [block(str(number).zfill(2), 100 + index * 100, 250) for index, number in enumerate([1, 2, 3, 4, 5, 7])]

    parsed = parse_color_codes(blocks)

    assert parsed.codes == ["01", "02", "03", "04", "05", "07"]
    assert parsed.missing_codes == ["06"]


def test_horizontal_parser_repairs_small_duplicate_rollback_ocr_error() -> None:
    blocks = [block(str(number), 100 + index * 100, 250) for index, number in enumerate([2, 3, 4, 5, 6, 7, 8])]
    blocks.append(block("6", 100 + 7 * 100, 250))
    blocks.extend(block(str(number), 100 + index * 100, 250) for index, number in enumerate(range(10, 15), start=8))

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number) for number in range(2, 15)]
    assert parsed.missing_codes == []


def test_horizontal_parser_does_not_repair_small_number_swap_as_ocr_outlier() -> None:
    blocks = [block(str(number).zfill(2), 100 + index * 100, 250) for index, number in enumerate(range(1, 11))]
    blocks.extend(
        [
            block("13", 100 + 10 * 100, 250),
            block("12", 100 + 11 * 100, 250),
            block("14", 100 + 12 * 100, 250),
            block("15", 100 + 13 * 100, 250),
        ]
    )

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number).zfill(2) for number in range(1, 11)] + ["13", "12", "14", "15"]
    assert parsed.missing_codes == ["11"]


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


def test_vertical_parser_completes_leading_number_after_alphanumeric_prefix() -> None:
    left_codes = ["1A"] + [str(number) for number in range(2, 26)]
    right_codes = [str(number) for number in range(26, 48)] + ["A1", "A2", "A3"]
    blocks = [block(code, 130, 210 + index * 30) for index, code in enumerate(left_codes)]
    blocks.extend(block(code, 1160, 210 + index * 30) for index, code in enumerate(right_codes))

    parsed = parse_color_codes(blocks)

    assert parsed.codes == ["1A"] + [str(number) for number in range(1, 48)] + ["A1", "A2", "A3"]
    assert parsed.missing_codes == []


def test_vertical_parser_completes_boundary_number_before_right_column() -> None:
    left_codes = [str(number) for number in range(1, 27)]
    right_codes = [str(number) for number in range(28, 53)] + ["A1", "A2"]
    blocks = [block(code, 130, 210 + index * 30) for index, code in enumerate(left_codes)]
    blocks.extend(block(code, 1160, 210 + index * 30) for index, code in enumerate(right_codes))

    parsed = parse_color_codes(blocks)

    assert parsed.codes == [str(number) for number in range(1, 53)] + ["A1", "A2"]
    assert parsed.missing_codes == []


def test_missing_numeric_codes_preserve_width() -> None:
    assert find_missing_numeric_codes(["01", "02", "04"]) == ["03"]


def test_missing_numeric_codes_ignores_implausibly_large_ranges() -> None:
    assert find_missing_numeric_codes(["1", "2", "10000"]) == []
