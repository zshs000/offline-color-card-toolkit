from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

import color_card_toolkit.ui.main_image_crop_page as main_crop_module
import color_card_toolkit.ui.scan_rename_page as scan_rename_module
from color_card_toolkit.core.image_rename import ImageProcessResult
from color_card_toolkit.ui.main_window import MainWindow
from color_card_toolkit.ui.main_image_crop_page import MainImageCropPage
from color_card_toolkit.ui.scan_rename_page import ScanRenamePage


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


def test_scan_rename_page_defaults_to_scan_output_folder() -> None:
    _app()
    page = ScanRenamePage(on_back=lambda: None)

    assert Path(page.output_folder_edit.text()).name == "色卡扫描图改名输出"


def test_scan_rename_page_clears_selected_images_after_success(monkeypatch, tmp_path: Path) -> None:
    _app()
    page = ScanRenamePage(on_back=lambda: None)
    source = tmp_path / "scan.jpg"
    output = tmp_path / "renamed" / "PU88.jpg"
    page.output_folder_edit.setText(str(output.parent))
    page._image_paths = [source]
    page._ocr_engine = object()
    page.image_summary.setText("已选择 1 张图片")

    monkeypatch.setattr(
        scan_rename_module,
        "rename_scan_images",
        lambda image_paths, output_dir, ocr_engine: [ImageProcessResult(source, output, "PU88")],
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    page._confirm_rename()

    assert page._image_paths == []
    assert page.image_summary.text() == "未选择图片"
    assert page.output_folder_edit.text() == str(output.parent)


def test_main_image_crop_page_defaults_to_crop_output_folder_and_10cm() -> None:
    _app()
    page = MainImageCropPage(on_back=lambda: None)

    assert Path(page.output_folder_edit.text()).name == "主图截图及名称更改输出"
    assert page.size_combo.currentData() == 10


def test_main_image_crop_page_passes_selected_size_and_clears_after_success(monkeypatch, tmp_path: Path) -> None:
    _app()
    page = MainImageCropPage(on_back=lambda: None)
    source = tmp_path / "main.jpg"
    output = tmp_path / "cropped" / "Main01.jpg"
    page.output_folder_edit.setText(str(output.parent))
    page.size_combo.setCurrentIndex(1)
    page._image_paths = [source]
    page._ocr_engine = object()
    page.image_summary.setText("已选择 1 张图片")
    captured: dict[str, object] = {}

    def fake_crop(image_paths, output_dir, ocr_engine, *, crop_size_cm):
        captured["crop_size_cm"] = crop_size_cm
        return [ImageProcessResult(source, output, "Main01")]

    monkeypatch.setattr(main_crop_module, "crop_main_images", fake_crop)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    page._confirm_crop()

    assert captured["crop_size_cm"] == 15
    assert page._image_paths == []
    assert page.image_summary.text() == "未选择图片"
    assert page.output_folder_edit.text() == str(output.parent)


def test_home_page_exposes_four_entries_and_routes_new_features() -> None:
    _app()
    window = MainWindow()
    buttons = window._home_page.findChildren(QPushButton)
    labels = [button.text() for button in buttons]

    assert labels == [
        "叠贴转平贴模板生成",
        "色卡扫描图改名",
        "主图截图及名称更改",
        "SPU名称生成不干胶模板",
    ]

    next(button for button in buttons if button.text() == "色卡扫描图改名").click()
    assert window._stack.currentWidget() is window._scan_rename_page

    window.show_home()
    next(button for button in buttons if button.text() == "主图截图及名称更改").click()
    assert window._stack.currentWidget() is window._main_image_crop_page


def test_home_entry_buttons_define_readable_text_color() -> None:
    _app()
    window = MainWindow()

    for button in window._home_page.findChildren(QPushButton):
        assert "color:" in button.parentWidget().styleSheet()
