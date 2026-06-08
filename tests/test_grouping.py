from __future__ import annotations

from color_card_toolkit.core.grouping import build_recognition_result, group_recognition_results, parse_group_name


def test_parse_group_name_accepts_half_and_full_width_parentheses() -> None:
    parsed = parse_group_name("PU88（2）")

    assert parsed.base_name == "PU88"
    assert parsed.sequence == 2
    assert parsed.explicit_sequence is True


def test_implicit_single_image_group_is_valid() -> None:
    result = build_recognition_result("a.jpg", "PU-6159", ["01", "02"])

    grouped = group_recognition_results([result])

    assert [group.base_name for group in grouped.valid_groups] == ["PU-6159"]
    assert grouped.valid_groups[0].color_codes == ["01", "02"]
    assert grouped.skipped_groups == []


def test_discontinuous_explicit_group_is_skipped_entirely() -> None:
    first = build_recognition_result("a.jpg", "PU88(1)", ["01"])
    third = build_recognition_result("c.jpg", "PU88(3)", ["03"])

    grouped = group_recognition_results([first, third])

    assert grouped.valid_groups == []
    assert len(grouped.skipped_groups) == 1
    assert grouped.skipped_groups[0].base_name == "PU88"
    assert "缺少第2张" in grouped.skipped_groups[0].reason


def test_explicit_group_merges_codes_in_sequence_order() -> None:
    second = build_recognition_result("b.jpg", "PU88(2)", ["03", "04"])
    first = build_recognition_result("a.jpg", "PU88(1)", ["01", "02"])

    grouped = group_recognition_results([second, first])

    assert len(grouped.valid_groups) == 1
    assert grouped.valid_groups[0].base_name == "PU88"
    assert grouped.valid_groups[0].color_codes == ["01", "02", "03", "04"]

