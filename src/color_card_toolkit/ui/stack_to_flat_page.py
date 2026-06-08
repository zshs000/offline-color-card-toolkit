from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.core.grouping import group_recognition_results, parse_group_name
from color_card_toolkit.core.models import ImageRecognitionResult, normalize_code_list
from color_card_toolkit.core.ocr_engine import RapidOcrEngine
from color_card_toolkit.core.recognition import recognize_image
from color_card_toolkit.core.resources import flat_template_path
from color_card_toolkit.core.word_generator import generate_flat_template_docx


class StackToFlatPage(QWidget):
    HEADERS = ["参与", "图片", "原始组名", "基础组名", "序号", "色号列表", "疑似缺号", "提示"]

    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._results: list[ImageRecognitionResult] = []
        self._ocr_engine = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        back_button = QPushButton("返回")
        back_button.clicked.connect(self._on_back)
        title = QLabel("叠贴转平贴模板生成")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        template_box = QGroupBox("平贴模板")
        template_layout = QHBoxLayout(template_box)
        self.template_label = QLabel(str(flat_template_path()))
        open_template = QPushButton("打开查看")
        open_template.clicked.connect(self._open_template)
        template_layout.addWidget(QLabel("内置模板："))
        template_layout.addWidget(self.template_label, 1)
        template_layout.addWidget(open_template)
        layout.addWidget(template_box)

        output_box = QGroupBox("输出设置")
        output_layout = QGridLayout(output_box)
        self.output_name_edit = QLineEdit("转平贴结果.docx")
        self.output_folder_edit = QLineEdit(str(Path.cwd()))
        browse_output = QPushButton("选择目录")
        browse_output.clicked.connect(self._pick_output_folder)
        output_layout.addWidget(QLabel("Word 名称："), 0, 0)
        output_layout.addWidget(self.output_name_edit, 0, 1)
        output_layout.addWidget(QLabel("保存目录："), 1, 0)
        output_layout.addWidget(self.output_folder_edit, 1, 1)
        output_layout.addWidget(browse_output, 1, 2)
        layout.addWidget(output_box)

        image_box = QGroupBox("图片选择")
        image_layout = QHBoxLayout(image_box)
        self.image_summary = QLabel("未选择图片")
        pick_images = QPushButton("选择图片")
        pick_images.clicked.connect(self._pick_images)
        recognize_button = QPushButton("开始识别")
        recognize_button.clicked.connect(self._recognize_images)
        image_layout.addWidget(self.image_summary, 1)
        image_layout.addWidget(pick_images)
        image_layout.addWidget(recognize_button)
        layout.addWidget(image_box)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        generate_button = QPushButton("生成 Word")
        generate_button.clicked.connect(self._generate_word)
        footer.addWidget(generate_button)
        layout.addLayout(footer)

    def _open_template(self) -> None:
        path = flat_template_path()
        if not path.exists():
            QMessageBox.warning(self, "模板不存在", f"找不到内置模板：{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _pick_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def _pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择待转换图片",
            str(Path.cwd()),
            "Images (*.jpg *.jpeg *.png)",
        )
        self._image_paths = [Path(file) for file in files]
        self.image_summary.setText(f"已选择 {len(self._image_paths)} 张图片" if files else "未选择图片")

    def _recognize_images(self) -> None:
        if not self._image_paths:
            QMessageBox.information(self, "未选择图片", "请先选择 .jpg/.jpeg/.png 图片。")
            return
        try:
            if self._ocr_engine is None:
                self._ocr_engine = RapidOcrEngine()
            self._results = [recognize_image(path, self._ocr_engine) for path in self._image_paths]
        except Exception as exc:
            QMessageBox.warning(self, "识别失败", str(exc))
            return
        self._populate_table(self._results)

    def _populate_table(self, results: list[ImageRecognitionResult]) -> None:
        self.table.setRowCount(len(results))
        for row, result in enumerate(results):
            checkbox = QCheckBox()
            checkbox.setChecked(result.participate)
            checkbox.setProperty("row", row)
            checkbox.stateChanged.connect(lambda state, r=row: self._set_participate(r, state == Qt.Checked))
            self.table.setCellWidget(row, 0, checkbox)
            self._set_item(row, 1, result.image_path.name, editable=False)
            self._set_item(row, 2, result.raw_name)
            self._set_item(row, 3, result.base_name)
            self._set_item(row, 4, str(result.sequence))
            self._set_item(row, 5, result.display_color_codes)
            self._set_item(row, 6, result.display_missing_codes, editable=False)
            self._set_item(row, 7, "；".join(result.warnings), editable=False)

    def _set_item(self, row: int, column: int, text: str, *, editable: bool = True) -> None:
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, column, item)

    def _set_participate(self, row: int, participate: bool) -> None:
        if 0 <= row < len(self._results):
            self._results[row].participate = participate

    def _results_from_table(self) -> list[ImageRecognitionResult]:
        rows: list[tuple[int, ImageRecognitionResult, str, str, int, list[str], bool]] = []
        for row, original in enumerate(self._results):
            raw_name = self._item_text(row, 2)
            base_name = self._item_text(row, 3)
            sequence_text = self._item_text(row, 4)
            parsed = parse_group_name(raw_name)
            try:
                sequence = int(sequence_text)
            except ValueError:
                sequence = parsed.sequence
            cleaned_base_name = base_name.strip() or parsed.base_name
            rows.append(
                (
                    row,
                    original,
                    raw_name,
                    cleaned_base_name,
                    sequence,
                    normalize_code_list(self._item_text(row, 5)),
                    parsed.explicit_sequence,
                )
            )

        base_counts: dict[str, int] = {}
        for _, _, _, base_name, _, _, _ in rows:
            base_counts[base_name] = base_counts.get(base_name, 0) + 1

        results: list[ImageRecognitionResult] = []
        for row, original, raw_name, base_name, sequence, color_codes, explicit_sequence in rows:
            result = ImageRecognitionResult(
                image_path=original.image_path,
                raw_name=raw_name,
                base_name=base_name,
                sequence=sequence,
                explicit_sequence=explicit_sequence or sequence != 1 or base_counts.get(base_name, 0) > 1,
                color_codes=color_codes,
                participate=original.participate,
                missing_codes=original.missing_codes,
                warnings=list(original.warnings),
                confidence=original.confidence,
            )
            results.append(result)
        return results

    def _item_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def _generate_word(self) -> None:
        if not self._results:
            QMessageBox.information(self, "没有识别结果", "请先完成识别，或在识别结果表中确认数据。")
            return

        output_name = self.output_name_edit.text().strip() or "转平贴结果.docx"
        if not output_name.lower().endswith(".docx"):
            output_name += ".docx"
        output_folder = Path(self.output_folder_edit.text().strip() or os.getcwd())
        output_path = output_folder / output_name

        grouping_result = group_recognition_results(self._results_from_table())
        if grouping_result.skipped_groups:
            skipped_text = "\n".join(f"{item.base_name}：{item.reason}" for item in grouping_result.skipped_groups)
            QMessageBox.warning(self, "部分色卡组已跳过", skipped_text)
        if not grouping_result.valid_groups:
            QMessageBox.warning(self, "无法生成", "没有可生成的有效色卡组。")
            return

        try:
            generated = generate_flat_template_docx(grouping_result.valid_groups, output_path)
        except Exception as exc:
            QMessageBox.critical(self, "生成失败", str(exc))
            return

        QMessageBox.information(self, "生成完成", f"Word 已生成：\n{generated}")
