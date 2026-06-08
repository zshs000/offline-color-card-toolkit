from __future__ import annotations

from pathlib import Path

from docx import Document
from PIL import Image

from color_card_toolkit.core.grouping import group_recognition_results
from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import FakeOcrEngine
from color_card_toolkit.core.recognition import recognize_image
from color_card_toolkit.core.word_generator import generate_flat_template_docx


def block(text: str, x: float, y: float, w: float = 20, h: float = 12) -> OcrBlock:
    return OcrBlock(
        text=text,
        confidence=0.97,
        box=((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
    )


def test_stack_to_flat_service_workflow_generates_paginated_word(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (1400, 500), "white").save(image_path)
    ocr_blocks = [
        block("PU88(1)", 20, 20, 90, 24),
        block("2014", 1180, 40, 80, 30),
        block('Width:52" Thickness:0.9mm', 1180, 100, 220, 20),
    ]
    ocr_blocks.extend(block(str(number).zfill(2), 20 + index * 45, 180) for index, number in enumerate(range(1, 27)))
    engine = FakeOcrEngine({str(image_path): ocr_blocks})

    recognized = recognize_image(image_path, engine)
    grouped = group_recognition_results([recognized])
    output_path = tmp_path / "result.docx"

    generate_flat_template_docx(grouped.valid_groups, output_path, Path("docs/转平贴底纸模板.docx"))

    document = Document(str(output_path))
    assert recognized.base_name == "PU88"
    assert recognized.sequence == 1
    assert recognized.color_codes[:3] == ["01", "02", "03"]
    assert recognized.color_codes[-1] == "26"
    assert grouped.skipped_groups == []
    assert len(document.tables) == 2
    assert document.tables[0].cell(0, 0).text == "PU88 (1)"
    assert document.tables[1].cell(0, 0).text == "PU88 (2)"
    assert document.tables[1].cell(1, 0).text == "25"
    assert document.tables[1].cell(1, 1).text == "26"

