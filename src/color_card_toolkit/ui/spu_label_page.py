from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.core.resources import spu_label_template_path
from color_card_toolkit.core.spu_label_generator import convert_spu_excel_to_docx


class SpuLabelPage(QWidget):
    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._excel_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 42, 56, 42)
        layout.setSpacing(28)

        header = QHBoxLayout()
        back_button = QPushButton("返回")
        back_button.clicked.connect(self._on_back)
        title = QLabel("SPU名称生成不干胶模板")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(34)
        layout.addLayout(form)

        excel_label = QLabel("选择要转换的excel文件：")
        self.excel_path_label = QLabel("未选择")
        self.excel_path_label.setMinimumWidth(220)
        pick_excel = QPushButton("+")
        pick_excel.setFixedSize(64, 64)
        pick_excel.setStyleSheet("font-size: 28px; color: #6b7280;")
        pick_excel.clicked.connect(self._pick_excel)

        start_label = QLabel("选择起始单元格：")
        self.start_row_spin = QSpinBox()
        self.start_row_spin.setRange(1, 999999)
        self.start_row_spin.setValue(2)
        self.start_row_spin.setFixedWidth(72)
        self.start_column_spin = QSpinBox()
        self.start_column_spin.setRange(1, 16384)
        self.start_column_spin.setValue(2)
        self.start_column_spin.setFixedWidth(72)

        form.addWidget(excel_label, 0, 0, Qt.AlignRight)
        form.addWidget(pick_excel, 0, 1)
        form.addWidget(self.excel_path_label, 0, 2)
        form.addWidget(start_label, 0, 3, Qt.AlignRight)
        form.addWidget(self.start_row_spin, 0, 4)
        form.addWidget(QLabel("行  &"), 0, 5)
        form.addWidget(self.start_column_spin, 0, 6)
        form.addWidget(QLabel("列"), 0, 7)

        template_label = QLabel("要转换成的word模板：")
        template_button = QPushButton("Word 模板\n8144-不干胶贴模板.docx")
        template_button.setFixedSize(190, 72)
        template_button.setStyleSheet(
            "QPushButton { text-align: left; padding: 10px; color: #1f2937; background: #f8fafc; border: 1px solid #cbd5e1; }"
            "QPushButton:hover { background: #eef2f7; }"
        )
        template_button.clicked.connect(self._open_template_preview)
        form.addWidget(template_label, 1, 0, Qt.AlignRight)
        form.addWidget(template_button, 1, 1, 1, 2)

        output_name_label = QLabel("转换后的word名称：")
        self.output_name_edit = QLineEdit("SPU不干胶结果.docx")
        self.output_name_edit.setMinimumWidth(220)
        output_folder_label = QLabel("转换后的word保存地址：")
        self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
        self.output_folder_edit.setMinimumWidth(300)
        browse_output = QPushButton("浏览")
        browse_output.clicked.connect(self._pick_output_folder)

        form.addWidget(output_name_label, 2, 0, Qt.AlignRight)
        form.addWidget(self.output_name_edit, 2, 1, 1, 2)
        form.addWidget(output_folder_label, 2, 3, Qt.AlignRight)
        form.addWidget(self.output_folder_edit, 2, 4, 1, 3)
        form.addWidget(browse_output, 2, 7)

        footer = QHBoxLayout()
        confirm_button = QPushButton("确定")
        confirm_button.setFixedSize(176, 50)
        confirm_button.setStyleSheet(
            "QPushButton { background: #1f9ed4; color: white; border: 0; border-radius: 6px; font-size: 16px; font-weight: 600; }"
            "QPushButton:hover { background: #1689bc; }"
        )
        confirm_button.clicked.connect(self._confirm)
        footer.addWidget(confirm_button)
        footer.addStretch(1)
        layout.addLayout(footer)
        layout.addStretch(1)

    def _default_output_folder(self) -> Path:
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base_folder = Path(documents) if documents else Path.home() / "Documents"
        return base_folder / "SPU不干胶模板输出"

    def _pick_excel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要转换的 Excel 文件",
            str(Path.cwd()),
            "Excel Files (*.xlsx)",
        )
        if file_path:
            self._excel_path = Path(file_path)
            self.excel_path_label.setText(self._excel_path.name)
            self.excel_path_label.setToolTip(str(self._excel_path))

    def _pick_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择保存地址", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def _open_template_preview(self) -> None:
        template = spu_label_template_path()
        if not template.exists():
            QMessageBox.warning(self, "模板不存在", f"找不到内置模板：{template}")
            return
        preview_dir = Path(tempfile.gettempdir()) / "color-card-toolkit-template-preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / template.name
        shutil.copy2(template, preview_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(preview_path)))

    def _confirm(self) -> None:
        if self._excel_path is None:
            QMessageBox.information(self, "未选择 Excel", "请先选择要转换的 Excel 文件。")
            return

        output_name = self.output_name_edit.text().strip() or "SPU不干胶结果.docx"
        if not output_name.lower().endswith(".docx"):
            output_name += ".docx"
        output_folder_text = self.output_folder_edit.text().strip()
        output_folder = Path(output_folder_text) if output_folder_text else self._default_output_folder()
        output_path = output_folder / output_name

        try:
            generated = convert_spu_excel_to_docx(
                self._excel_path,
                output_path,
                start_row=self.start_row_spin.value(),
                start_column=self.start_column_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "转换失败", str(exc))
            return

        QMessageBox.information(self, "转换完成", f"Word 已生成：\n{generated}")
