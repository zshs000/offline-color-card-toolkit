from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl, Qt
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

from color_card_toolkit.core.cloud_recognition import CloudVisionConfig
from color_card_toolkit.core.grouping import group_recognition_results, parse_group_name
from color_card_toolkit.core.models import ImageRecognitionResult, normalize_code_list
from color_card_toolkit.core.ocr_engine import RapidOcrEngine
from color_card_toolkit.core.recognition import recognize_image
from color_card_toolkit.core.resources import flat_template_path
from color_card_toolkit.core.word_generator import generate_flat_template_docx
from color_card_toolkit.ui.batch_worker import run_batch_task


class StackToFlatPage(QWidget):
    HEADERS = ["参与", "图片", "原始组名", "基础组名", "序号", "色号列表", "疑似缺号", "提示"]

    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._results: list[ImageRecognitionResult] = []
        self._batch_controller = None
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
        self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
        browse_output = QPushButton("选择目录")
        browse_output.clicked.connect(self._pick_output_folder)
        output_layout.addWidget(QLabel("Word 名称："), 0, 0)
        output_layout.addWidget(self.output_name_edit, 0, 1)
        output_layout.addWidget(QLabel("保存目录："), 1, 0)
        output_layout.addWidget(self.output_folder_edit, 1, 1)
        output_layout.addWidget(browse_output, 1, 2)
        layout.addWidget(output_box)

        cloud_box = QGroupBox("横版云端识别")
        cloud_layout = QGridLayout(cloud_box)
        self.cloud_base_url_edit = QLineEdit(os.environ.get("COLOR_CARD_CLOUD_BASE_URL", ""))
        self.cloud_api_key_edit = QLineEdit(os.environ.get("COLOR_CARD_CLOUD_API_KEY", ""))
        self.cloud_api_key_edit.setEchoMode(QLineEdit.Password)
        self.cloud_model_edit = QLineEdit(os.environ.get("COLOR_CARD_CLOUD_MODEL", ""))
        cloud_layout.addWidget(QLabel("Base URL:"), 0, 0)
        cloud_layout.addWidget(self.cloud_base_url_edit, 0, 1)
        cloud_layout.addWidget(QLabel("API Key:"), 1, 0)
        cloud_layout.addWidget(self.cloud_api_key_edit, 1, 1)
        cloud_layout.addWidget(QLabel("Model:"), 2, 0)
        cloud_layout.addWidget(self.cloud_model_edit, 2, 1)
        cloud_layout.addWidget(QLabel("仅横版使用云端识别；竖版仍走本地识别。三项都填写后启用。"), 3, 0, 1, 2)
        layout.addWidget(cloud_box)

        image_box = QGroupBox("图片选择")
        image_layout = QHBoxLayout(image_box)
        self.image_summary = QLabel("未选择图片")
        self.pick_images_button = QPushButton("选择图片")
        self.pick_images_button.clicked.connect(self._pick_images)
        self.recognize_button = QPushButton("开始识别")
        self.recognize_button.clicked.connect(self._recognize_images)
        image_layout.addWidget(self.image_summary, 1)
        image_layout.addWidget(self.pick_images_button)
        image_layout.addWidget(self.recognize_button)
        layout.addWidget(image_box)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.generate_button = QPushButton("生成 Word")
        self.generate_button.clicked.connect(self._generate_word)
        footer.addWidget(self.generate_button)
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

    def _default_output_folder(self) -> Path:
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base_folder = Path(documents) if documents else Path.home() / "Documents"
        return base_folder / "线下色卡采集工具集输出"

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
        self._results = []
        self._set_processing(True)
        cloud_config = self._cloud_config_from_ui()
        if cloud_config is False:
            self._set_processing(False)
            return

        engine_holder = threading.local()

        def process(path: Path) -> ImageRecognitionResult:
            try:
                if not hasattr(engine_holder, "engine"):
                    engine_holder.engine = RapidOcrEngine(
                        intra_op_num_threads=1,
                        inter_op_num_threads=1,
                    )
                if cloud_config:
                    return recognize_image(path, engine_holder.engine, cloud_config=cloud_config)
                return recognize_image(path, engine_holder.engine)
            except Exception as exc:
                return _manual_result_for_image(path, f"OCR 识别失败：{exc}。已使用文件名作为组名，请手动修正。")

        self._batch_controller = run_batch_task(
            self._image_paths,
            process,
            on_progress=self._on_recognition_progress,
            on_finished=lambda results, failed_count: self._on_recognition_finished(
                results,
                failed_count + _manual_failure_count(results),
            ),
            on_failed=self._on_recognition_failed,
            max_workers=2,
            parent=self,
        )

    def _on_recognition_progress(self, current: int, total: int, label: str) -> None:
        self.image_summary.setText(f"正在识别 {current}/{total}：{label}")

    def _on_recognition_finished(self, results: list[ImageRecognitionResult], failed_count: int) -> None:
        self._batch_controller = None
        self._results = list(results)
        self._populate_table(self._results)
        self._set_processing(False)
        self.image_summary.setText(f"已识别 {len(self._results)} 张图片")
        cloud_summary = _cloud_recognition_summary(self._results)
        if cloud_summary:
            self.image_summary.setText(f"{self.image_summary.text()}; {cloud_summary}")
        if failed_count:
            QMessageBox.warning(
                self,
                "部分图片识别失败",
                f"{failed_count} 张图片识别失败，已生成可编辑行供手动修正。",
            )

    def _on_recognition_failed(self, message: str) -> None:
        self._batch_controller = None
        self._set_processing(False)
        QMessageBox.critical(self, "识别失败", message)

    def _cloud_config_from_ui(self) -> CloudVisionConfig | None | bool:
        base_url = self.cloud_base_url_edit.text().strip()
        api_key = self.cloud_api_key_edit.text().strip()
        model = self.cloud_model_edit.text().strip()
        if not any((base_url, api_key, model)):
            return None
        if not all((base_url, api_key, model)):
            QMessageBox.warning(self, "云端配置不完整", "Base URL、API Key、Model 必须同时填写。")
            return False
        return CloudVisionConfig(base_url=base_url, api_key=api_key, model=model)

    def _set_processing(self, processing: bool) -> None:
        self.pick_images_button.setEnabled(not processing)
        self.recognize_button.setEnabled(not processing)
        self.generate_button.setEnabled(not processing)
        self.cloud_base_url_edit.setEnabled(not processing)
        self.cloud_api_key_edit.setEnabled(not processing)
        self.cloud_model_edit.setEnabled(not processing)

    def _manual_result_for_image(self, path: Path, warning: str) -> ImageRecognitionResult:
        return _manual_result_for_image(path, warning)

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

    def _clear_recognition_state(self) -> None:
        self._image_paths = []
        self._results = []
        self.table.setRowCount(0)
        self.image_summary.setText("未选择图片")

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
                recognition_source=original.recognition_source,
                api_retry_count=original.api_retry_count,
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
        output_folder_text = self.output_folder_edit.text().strip()
        output_folder = Path(output_folder_text) if output_folder_text else self._default_output_folder()
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

        self._clear_recognition_state()
        QMessageBox.information(self, "生成完成", f"Word 已生成：\n{generated}")


def _manual_result_for_image(path: Path, warning: str) -> ImageRecognitionResult:
    fallback_name = path.stem.strip()
    parsed = parse_group_name(fallback_name)
    return ImageRecognitionResult(
        image_path=path,
        raw_name=fallback_name,
        base_name=parsed.base_name,
        sequence=parsed.sequence,
        color_codes=[],
        explicit_sequence=parsed.explicit_sequence,
        warnings=[warning],
        confidence=0.0,
    )


def _manual_failure_count(results: list[ImageRecognitionResult]) -> int:
    return sum(
        1
        for result in results
        if result.recognition_source == "cloud_failed"
        or any(warning.startswith("OCR 识别失败") for warning in result.warnings)
    )


def _cloud_recognition_summary(results: list[ImageRecognitionResult]) -> str:
    crop = sum(1 for result in results if result.recognition_source == "cloud_crop")
    full = sum(1 for result in results if result.recognition_source == "cloud_full")
    retry = sum(1 for result in results if result.recognition_source == "cloud_retry_full")
    failed = sum(1 for result in results if result.recognition_source == "cloud_failed")
    if not any((crop, full, retry, failed)):
        return ""
    return f"云端：裁剪 {crop}，整图 {full}，重试 {retry}，失败 {failed}"
