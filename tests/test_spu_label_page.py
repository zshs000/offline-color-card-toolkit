from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

import color_card_toolkit.ui.spu_label_page as spu_page_module
from color_card_toolkit.ui.main_window import MainWindow
from color_card_toolkit.ui.spu_label_page import SpuLabelPage


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


@pytest.fixture(autouse=True)
def _cleanup_qt_widgets():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()


def test_spu_label_page_defaults_to_second_row_second_column() -> None:
    _app()
    page = SpuLabelPage(on_back=lambda: None)

    assert page.start_row_spin.value() == 2
    assert page.start_column_spin.value() == 2
    assert Path(page.output_folder_edit.text()).name == "SPU不干胶模板输出"


def test_spu_label_page_generates_docx_with_selected_inputs(monkeypatch, tmp_path: Path) -> None:
    _app()
    page = SpuLabelPage(on_back=lambda: None)
    excel_path = tmp_path / "sample.xlsx"
    output_dir = tmp_path / "out"
    expected_output = output_dir / "result.docx"
    page._excel_path = excel_path
    page.output_folder_edit.setText(str(output_dir))
    page.output_name_edit.setText("result")
    captured: dict[str, object] = {}

    def fake_convert(excel_path_arg, output_path_arg, *, start_row, start_column):
        captured["excel_path"] = excel_path_arg
        captured["output_path"] = output_path_arg
        captured["start_row"] = start_row
        captured["start_column"] = start_column
        return expected_output

    monkeypatch.setattr(spu_page_module, "convert_spu_excel_to_docx", fake_convert)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    page._confirm()

    assert captured == {
        "excel_path": excel_path,
        "output_path": expected_output,
        "start_row": 2,
        "start_column": 2,
    }


def test_home_page_routes_spu_label_entry() -> None:
    _app()
    window = MainWindow()
    buttons = window._home_page.findChildren(QPushButton)

    next(button for button in buttons if button.text() == "SPU名称生成不干胶模板").click()

    assert window._stack.currentWidget() is window._spu_label_page
