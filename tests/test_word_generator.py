from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from color_card_toolkit.core.models import GroupedColorCard
from color_card_toolkit.core.word_generator import CODE_ROW_INDICES, generate_flat_template_docx


def test_word_generator_fills_header_and_24_code_slots(tmp_path: Path) -> None:
    template = Path("docs/转平贴底纸模板.docx")
    output = tmp_path / "output.docx"
    codes = [str(number).zfill(2) for number in range(1, 27)]

    generate_flat_template_docx([GroupedColorCard("PU88", codes)], output, template)

    document = Document(str(output))
    assert len(document.tables) == 2
    assert document.tables[0].cell(0, 0).text == "PU88 (1)"
    assert document.tables[1].cell(0, 0).text == "PU88 (2)"
    assert document.tables[0].cell(0, 0).paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER

    first_page_codes = []
    for row_index in CODE_ROW_INDICES:
        first_page_codes.extend(document.tables[0].cell(row_index, column).text for column in range(6))
    assert first_page_codes == codes[:24]
    assert document.tables[0].cell(1, 0).paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.LEFT
    assert document.tables[0].cell(7, 5).paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.LEFT

    second_page_codes = []
    for row_index in CODE_ROW_INDICES:
        second_page_codes.extend(document.tables[1].cell(row_index, column).text for column in range(6))
    assert second_page_codes[:2] == ["25", "26"]
    assert all(value == "" for value in second_page_codes[2:])
