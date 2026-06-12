from __future__ import annotations

import threading
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

from color_card_toolkit.core.image_rename import ImageProcessResult, rename_scan_images
from color_card_toolkit.core.ocr_engine import RapidOcrEngine
from color_card_toolkit.ui.batch_worker import run_batch_task


class ScanRenamePage(QWidget):
    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._batch_controller = None
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
        self.browse_output_button = QPushButton("选择地址")
        self.browse_output_button.clicked.connect(self._pick_output_folder)
        output_layout.addWidget(QLabel("色卡改名后扫描图片保存的地址："), 0, 0)
        output_layout.addWidget(self.output_folder_edit, 0, 1)
        output_layout.addWidget(self.browse_output_button, 0, 2)
        layout.addWidget(output_box)

        image_box = QGroupBox("图片选择")
        image_layout = QHBoxLayout(image_box)
        self.image_summary = QLabel("未选择图片")
        self.pick_images_button = QPushButton("选择改名的色卡扫描图")
        self.pick_images_button.clicked.connect(self._pick_images)
        image_layout.addWidget(self.image_summary, 1)
        image_layout.addWidget(self.pick_images_button)
        layout.addWidget(image_box)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.confirm_button = QPushButton("确认")
        self.confirm_button.clicked.connect(self._confirm_rename)
        footer.addWidget(self.confirm_button)
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
        self._set_processing(True)
        failures: list[str] = []
        engine_holder = threading.local()

        def process(path: Path) -> ImageProcessResult:
            if not hasattr(engine_holder, "engine"):
                engine_holder.engine = RapidOcrEngine(
                    intra_op_num_threads=1,
                    inter_op_num_threads=1,
                )
            results = rename_scan_images([path], output_folder, engine_holder.engine)
            if not results:
                raise RuntimeError("未生成输出文件")
            return results[0]

        def item_failed(index: int, label: str, message: str) -> None:
            failures.append(f"{label}：{message}")

        self._batch_controller = run_batch_task(
            self._image_paths,
            process,
            on_progress=self._on_rename_progress,
            on_finished=lambda results, failed_count: self._on_rename_finished(
                results,
                failed_count,
                output_folder,
                failures,
            ),
            on_failed=self._on_rename_failed,
            on_item_failed=item_failed,
            max_workers=2,
            parent=self,
        )

    def _on_rename_progress(self, current: int, total: int, label: str) -> None:
        self.image_summary.setText(f"正在改名 {current}/{total}：{label}")

    def _on_rename_finished(
        self,
        results: list[ImageProcessResult],
        failed_count: int,
        output_folder: Path,
        failures: list[str],
    ) -> None:
        self._batch_controller = None
        self._set_processing(False)
        success_count = len(results)
        self._clear_selected_images()
        if failed_count:
            detail = "\n".join(failures[:5])
            suffix = f"\n\n失败明细：\n{detail}" if detail else ""
            QMessageBox.warning(
                self,
                "改名完成（部分失败）",
                f"已保存 {success_count} 张图片到：\n{output_folder}\n\n失败 {failed_count} 张。{suffix}",
            )
            return
        QMessageBox.information(self, "改名完成", f"已保存 {success_count} 张图片到：\n{output_folder}")

    def _on_rename_failed(self, message: str) -> None:
        self._batch_controller = None
        self._set_processing(False)
        QMessageBox.critical(self, "改名失败", message)

    def _set_processing(self, processing: bool) -> None:
        self.output_folder_edit.setEnabled(not processing)
        self.browse_output_button.setEnabled(not processing)
        self.pick_images_button.setEnabled(not processing)
        self.confirm_button.setEnabled(not processing)

    def _clear_selected_images(self) -> None:
        self._image_paths = []
        self.image_summary.setText("未选择图片")
