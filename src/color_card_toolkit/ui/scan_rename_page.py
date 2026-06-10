from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.core.image_rename import rename_scan_images
from color_card_toolkit.core.ocr_engine import RapidOcrEngine


class ScanRenamePage(QWidget):
    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._ocr_engine = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        back_button = QPushButton("返回")
        back_button.clicked.connect(self._on_back)
        title = QLabel("色卡扫描图改名")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        output_box = QGroupBox("保存设置")
        output_layout = QGridLayout(output_box)
        self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
        browse_output = QPushButton("选择地址")
        browse_output.clicked.connect(self._pick_output_folder)
        output_layout.addWidget(QLabel("色卡改名后扫描图片保存的地址："), 0, 0)
        output_layout.addWidget(self.output_folder_edit, 0, 1)
        output_layout.addWidget(browse_output, 0, 2)
        layout.addWidget(output_box)

        image_box = QGroupBox("图片选择")
        image_layout = QHBoxLayout(image_box)
        self.image_summary = QLabel("未选择图片")
        pick_images = QPushButton("选择改名的色卡扫描图")
        pick_images.clicked.connect(self._pick_images)
        image_layout.addWidget(self.image_summary, 1)
        image_layout.addWidget(pick_images)
        layout.addWidget(image_box)

        footer = QHBoxLayout()
        footer.addStretch(1)
        confirm_button = QPushButton("确认")
        confirm_button.clicked.connect(self._confirm_rename)
        footer.addWidget(confirm_button)
        layout.addStretch(1)
        layout.addLayout(footer)

    def _default_output_folder(self) -> Path:
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base_folder = Path(documents) if documents else Path.home() / "Documents"
        return base_folder / "色卡扫描图改名输出"

    def _pick_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择保存地址", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def _pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择改名的色卡扫描图",
            str(Path.cwd()),
            "Images (*.jpg *.jpeg *.png)",
        )
        self._image_paths = [Path(file) for file in files]
        self.image_summary.setText(f"已选择 {len(self._image_paths)} 张图片" if files else "未选择图片")

    def _confirm_rename(self) -> None:
        if not self._image_paths:
            QMessageBox.information(self, "未选择图片", "请先选择需要改名的色卡扫描图。")
            return

        output_folder_text = self.output_folder_edit.text().strip()
        output_folder = Path(output_folder_text) if output_folder_text else self._default_output_folder()

        try:
            if self._ocr_engine is None:
                self._ocr_engine = RapidOcrEngine()
            results = rename_scan_images(self._image_paths, output_folder, self._ocr_engine)
        except Exception as exc:
            QMessageBox.critical(self, "改名失败", str(exc))
            return

        self._clear_selected_images()
        QMessageBox.information(self, "改名完成", f"已保存 {len(results)} 张图片到：\n{output_folder}")

    def _clear_selected_images(self) -> None:
        self._image_paths = []
        self.image_summary.setText("未选择图片")
