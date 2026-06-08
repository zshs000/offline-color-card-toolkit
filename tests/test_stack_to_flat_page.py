from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

import color_card_toolkit.ui.stack_to_flat_page as stack_to_flat_page_module
from color_card_toolkit.core.models import ImageRecognitionResult
from color_card_toolkit.ui.stack_to_flat_page import StackToFlatPage


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def test_generate_word_clears_recognition_state(monkeypatch, tmp_path: Path) -> None:
    _app()
    page = StackToFlatPage(on_back=lambda: None)
    page.output_folder_edit.setText(str(tmp_path))
    page.output_name_edit.setText("result.docx")
    page._image_paths = [tmp_path / "PU88.png"]
    page._results = [
        ImageRecognitionResult(
            image_path=tmp_path / "PU88.png",
            raw_name="PU88",
            base_name="PU88",
            sequence=1,
            color_codes=["01", "02"],
        )
    ]
    page._populate_table(page._results)

    generated_path = tmp_path / "result.docx"
    monkeypatch.setattr(
        stack_to_flat_page_module,
        "generate_flat_template_docx",
        lambda groups, output_path: generated_path,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    page._generate_word()

    assert page._image_paths == []
    assert page._results == []
    assert page.table.rowCount() == 0
    assert page.image_summary.text() == "未选择图片"
    assert page.output_folder_edit.text() == str(tmp_path)
    assert page.output_name_edit.text() == "result.docx"


def test_output_folder_defaults_to_user_output_directory() -> None:
    _app()
    page = StackToFlatPage(on_back=lambda: None)

    assert Path(page.output_folder_edit.text()).name == "线下色卡采集工具集输出"
