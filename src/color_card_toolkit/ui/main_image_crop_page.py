from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.core.cloud_recognition import (
    CloudVisionConfig,
    recognize_main_image_name_result_with_cloud,
)
from color_card_toolkit.core.image_rename import (
    _safe_filename,
    crop_image_from_geometry,
    unique_output_path,
)
from color_card_toolkit.core.models import ImageRecognitionResult
from color_card_toolkit.core.recognition_logging import (
    concurrency_ratio,
    summarize_api_usage,
    write_recognition_log,
)
from color_card_toolkit.core.recognition_settings import (
    RecognitionSettings,
    load_recognition_settings,
    save_recognition_settings,
)
from color_card_toolkit.core.ruler_inspection import RulerInspection, inspect_image_ruler
from color_card_toolkit.ui.batch_worker import run_batch_task
from color_card_toolkit.ui.main_image_preview import MainImagePreviewServer


MAX_CLOUD_RETRY_ROUNDS = 3


@dataclass
class _HealthWorkItem:
    source_path: Path
    inspection: RulerInspection

    @property
    def name(self) -> str:
        return self.source_path.name


@dataclass
class _CloudWorkItem:
    source_path: Path
    inspection: RulerInspection
    result: ImageRecognitionResult
    recognition_error: str = ""
    retryable: bool = False
    attempts: list[ImageRecognitionResult] | None = None

    @property
    def name(self) -> str:
        return self.source_path.name

    def all_attempts(self) -> list[ImageRecognitionResult]:
        return list(self.attempts or [self.result])


@dataclass
class _PreviewEntry:
    item_id: str
    source_path: Path
    preview_path: Path
    recognized_name: str
    cloud_result: ImageRecognitionResult

    @property
    def name(self) -> str:
        return self.source_path.name


class MainImageCropPage(QWidget):
    """Main-image workflow: local ruler gate, cloud name recognition, browser review."""

    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._batch_controller = None
        self._health_items: list[_HealthWorkItem] = []
        self._cloud_items: list[_CloudWorkItem] = []
        self._preview_entries: list[_PreviewEntry] = []
        self._preview_server: MainImagePreviewServer | None = None
        self._preview_dir: Path | None = None
        self._preview_confirmed = False
        self._active_cloud_config: CloudVisionConfig | None = None
        self._crop_output_folder: Path | None = None
        self._crop_size_cm = 10
        self._crop_failures: list[str] = []
        self._health_failed_count = 0
        self._cloud_failed_count = 0
        self._crop_failed_count = 0
        self._health_log_path: Path | None = None
        self._retry_round = 0
        self._recognition_started_at: datetime | None = None
        self._recognition_settings = load_recognition_settings()
        self._build_ui()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._close_preview_server()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        back_button = QPushButton("返回")
        back_button.clicked.connect(self._on_back)
        title = QLabel("主图截图及名称更改")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(back_button)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        settings_box = QGroupBox("截图设置")
        settings_layout = QGridLayout(settings_box)
        self.size_combo = QComboBox()
        self.size_combo.addItem("10cm * 10cm", 10)
        self.size_combo.addItem("15cm * 15cm", 15)
        self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
        self.browse_output_button = QPushButton("选择地址")
        self.browse_output_button.clicked.connect(self._pick_output_folder)
        self.ruler_summary = QLabel()
        self._refresh_ruler_summary()
        settings_layout.addWidget(QLabel("选择截图的尺寸："), 0, 0)
        settings_layout.addWidget(self.size_combo, 0, 1)
        settings_layout.addWidget(QLabel("截图及改名后图片保存的地址："), 1, 0)
        settings_layout.addWidget(self.output_folder_edit, 1, 1)
        settings_layout.addWidget(self.browse_output_button, 1, 2)
        settings_layout.addWidget(self.ruler_summary, 2, 0, 1, 3)
        layout.addWidget(settings_box)

        image_box = QGroupBox("图片选择")
        image_layout = QHBoxLayout(image_box)
        self.image_summary = QLabel("未选择图片")
        self.pick_images_button = QPushButton("选择对应要截图及改名的图片")
        self.pick_images_button.clicked.connect(self._pick_images)
        image_layout.addWidget(self.image_summary, 1)
        image_layout.addWidget(self.pick_images_button)
        layout.addWidget(image_box)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.settings_button = QPushButton("识别设置")
        self.settings_button.clicked.connect(self._open_settings_dialog)
        footer.addWidget(self.settings_button)
        self.preview_checkbox = QCheckBox("识别后打开浏览器复核")
        self.preview_checkbox.setChecked(True)
        self.preview_checkbox.setToolTip("取消后将使用云端名称直接保存，不打开浏览器复核页")
        footer.addWidget(self.preview_checkbox)
        self.confirm_button = QPushButton("确认")
        self.confirm_button.clicked.connect(self._confirm_crop)
        footer.addWidget(self.confirm_button)
        layout.addStretch(1)
        layout.addLayout(footer)

    def _default_output_folder(self) -> Path:
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base_folder = Path(documents) if documents else Path.home() / "Documents"
        return base_folder / "主图截图及名称更改输出"

    def _refresh_ruler_summary(self) -> None:
        percent = self._recognition_settings.main_image_ruler_search_ratio * 100
        self.ruler_summary.setText(
            f"标尺检测搜索范围：{percent:.0f}%（主图功能专用；先检测通过后才调用云端）"
        )

    def _pick_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择保存地址", self.output_folder_edit.text())
        if folder:
            self.output_folder_edit.setText(folder)

    def _pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择对应要截图及改名的图片",
            str(Path.cwd()),
            "Images (*.jpg *.jpeg *.png)",
        )
        self._image_paths = [Path(file) for file in files]
        self.image_summary.setText(f"已选择 {len(self._image_paths)} 张图片" if files else "未选择图片")

    def _confirm_crop(self) -> None:
        if not self._image_paths:
            QMessageBox.information(self, "未选择图片", "请先选择对应要截图及改名的图片。")
            return

        cloud_config = self._cloud_config_from_settings()
        if cloud_config is False:
            return

        output_folder_text = self.output_folder_edit.text().strip()
        self._crop_output_folder = (
            Path(output_folder_text) if output_folder_text else self._default_output_folder()
        )
        self._crop_size_cm = int(self.size_combo.currentData())
        self._active_cloud_config = cloud_config
        self._health_items = []
        self._cloud_items = []
        self._preview_entries = []
        self._crop_failures = []
        self._health_failed_count = 0
        self._cloud_failed_count = 0
        self._crop_failed_count = 0
        self._health_log_path = None
        self._retry_round = 0
        self._recognition_started_at = datetime.now()
        self._set_processing(True)
        self._start_health_check()

    def _start_health_check(self) -> None:
        ratio = self._recognition_settings.main_image_ruler_search_ratio
        crop_size_cm = self._crop_size_cm

        def process(path: Path) -> _HealthWorkItem:
            inspection = inspect_image_ruler(
                path,
                crop_size_cm=crop_size_cm,
                search_ratio=ratio,
                suggest_retry=True,
            )
            return _HealthWorkItem(path, inspection)

        self._batch_controller = run_batch_task(
            self._image_paths,
            process,
            on_progress=self._on_health_progress,
            on_finished=self._on_health_finished,
            on_failed=self._on_health_failed,
            on_item_failed=lambda _index, label, message: self._crop_failures.append(
                f"{label}：{message}"
            ),
            max_workers=2,
            parent=self,
        )

    def _on_health_progress(self, current: int, total: int, label: str) -> None:
        self.image_summary.setText(f"正在检测标尺 {current}/{total}：{label}")

    def _on_health_finished(self, results: list[_HealthWorkItem], failed_count: int) -> None:
        self._batch_controller = None
        self._health_items = list(results)
        self._health_log_path = self._write_health_report(self._health_items)
        failed = [item for item in self._health_items if not item.inspection.passed]
        self._health_failed_count = failed_count + len(failed)
        passed = [item for item in self._health_items if item.inspection.passed]
        if not passed:
            self._set_processing(False)
            self._show_health_failure(failed)
            return
        if failed and not self._ask_continue_after_health_check(passed, failed):
            self._set_processing(False)
            return
        self._start_cloud_recognition(passed)

    def _ask_continue_after_health_check(
        self,
        passed: list[_HealthWorkItem],
        failed: list[_HealthWorkItem],
    ) -> bool:
        details = "\n".join(self._format_inspection(item) for item in failed[:8])
        extra = len(failed) - 8
        if extra > 0:
            details += f"\n……另有 {extra} 张"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("标尺健康检测有问题")
        box.setText(
            f"检测通过 {len(passed)} 张，未通过 {len(failed)} 张。\n"
            "未通过的图片不会裁剪，也不会调用云端。"
        )
        if self._health_log_path is not None:
            details += f"\n\n健康检测报告：{self._health_log_path}"
        box.setDetailedText(details)
        continue_button = box.addButton("继续识别通过的图片", QMessageBox.AcceptRole)
        stop_button = box.addButton("停止并调整参数", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is stop_button:
            return False
        return box.clickedButton() is continue_button

    def _show_health_failure(self, failed: list[_HealthWorkItem]) -> None:
        details = "\n".join(self._format_inspection(item) for item in failed[:12])
        QMessageBox.warning(
            self,
            "标尺检测未通过",
            "没有图片通过标尺健康检测。\n"
            "本次未调用云端，也没有生成中心裁剪结果。\n\n"
            f"{details}\n\n健康检测报告：{self._health_log_path or '未写入'}\n\n"
            "请在识别设置中调整标尺搜索范围后重试。",
        )
        self.image_summary.setText("标尺检测未通过，未调用云端")

    def _format_inspection(self, item: _HealthWorkItem) -> str:
        inspection = item.inspection
        suggestion = (
            f"建议 {inspection.suggested_ratio:.0%}"
            if inspection.suggested_ratio is not None
            else "暂无可靠建议"
        )
        return f"{item.source_path.name}：{inspection.message}（{suggestion}）"

    def _write_health_report(self, items: list[_HealthWorkItem]) -> Path | None:
        try:
            output_dir = Path.cwd() / "logs"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"ruler_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            rows = []
            for item in items:
                inspection = item.inspection
                geometry = inspection.geometry
                rows.append(
                    {
                        "source_path": str(item.source_path),
                        "status": inspection.status,
                        "passed": inspection.passed,
                        "message": inspection.message,
                        "suggested_ratio": inspection.suggested_ratio,
                        "dpi": list(inspection.dpi),
                        "geometry": (
                            {
                                "origin": [float(geometry.origin[0]), float(geometry.origin[1])],
                                "rotation_degrees": geometry.rotation_degrees,
                                "spacing_x": geometry.spacing_x,
                                "spacing_y": geometry.spacing_y,
                                "span_mm": geometry.span_mm,
                                "top_support": geometry.top_support,
                                "left_support": geometry.left_support,
                                "top_inlier_ratio": geometry.top_inlier_ratio,
                                "left_inlier_ratio": geometry.left_inlier_ratio,
                                "healthy": geometry.healthy,
                            }
                            if geometry is not None
                            else None
                        ),
                    }
                )
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "search_ratio": self._recognition_settings.main_image_ruler_search_ratio,
                "crop_size_cm": self._crop_size_cm,
                "items": rows,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return path
        except Exception:
            return None

    def _start_cloud_recognition(self, health_items: list[_HealthWorkItem]) -> None:
        cloud_config = self._active_cloud_config
        if cloud_config is None:
            self._set_processing(False)
            self.image_summary.setText("标尺检测完成，但未配置云端识别")
            QMessageBox.information(
                self,
                "标尺检测完成",
                "本地标尺健康检测已完成。请在识别设置中填写 Base URL、API Key 和 Model 后再进行云端识别。",
            )
            return

        def process(item: _HealthWorkItem) -> _CloudWorkItem:
            result, error = _recognize_main_image_attempt(
                item.source_path,
                cloud_config,
                retry_count=0,
            )
            return _CloudWorkItem(
                source_path=item.source_path,
                inspection=item.inspection,
                result=result,
                recognition_error=error,
                retryable=bool(error),
                attempts=[result],
            )

        self._batch_controller = run_batch_task(
            health_items,
            process,
            on_progress=self._on_cloud_progress,
            on_finished=self._on_cloud_finished,
            on_failed=self._on_cloud_failed,
            on_item_failed=lambda _index, label, message: self._crop_failures.append(
                f"{label}：{message}"
            ),
            max_workers=2,
            parent=self,
        )

    def _on_cloud_progress(self, current: int, total: int, label: str) -> None:
        self.image_summary.setText(f"正在云端识别 {current}/{total}：{label}")

    def _on_cloud_finished(self, results: list[_CloudWorkItem], failed_count: int) -> None:
        self._batch_controller = None
        self._cloud_items = list(results)
        self._cloud_failed_count = failed_count
        self._continue_retry_or_preview()

    def _continue_retry_or_preview(self) -> None:
        pending = [item for item in self._cloud_items if item.retryable and item.recognition_error]
        if pending and self._retry_round < MAX_CLOUD_RETRY_ROUNDS:
            self._start_retry_round(pending)
            return
        self._start_preview_generation()

    def _start_retry_round(self, pending: list[_CloudWorkItem]) -> None:
        cloud_config = self._active_cloud_config
        if cloud_config is None:
            self._start_preview_generation()
            return
        self._retry_round += 1
        retry_round = self._retry_round
        self.image_summary.setText(
            f"正在准备第 {retry_round}/{MAX_CLOUD_RETRY_ROUNDS} 轮重试，共 {len(pending)} 张"
        )

        def process(item: _CloudWorkItem) -> _CloudWorkItem:
            result, error = _recognize_main_image_attempt(
                item.source_path,
                cloud_config,
                retry_count=retry_round,
            )
            attempts = [*item.all_attempts(), result]
            return _CloudWorkItem(
                source_path=item.source_path,
                inspection=item.inspection,
                result=result,
                recognition_error=error,
                retryable=bool(error),
                attempts=attempts,
            )

        self._batch_controller = run_batch_task(
            pending,
            process,
            on_progress=lambda current, total, label: self.image_summary.setText(
                f"第 {retry_round}/{MAX_CLOUD_RETRY_ROUNDS} 轮重试 {current}/{total}：{label}"
            ),
            on_finished=self._on_retry_round_finished,
            on_failed=self._on_cloud_failed,
            max_workers=2,
            parent=self,
        )

    def _on_retry_round_finished(self, results: list[_CloudWorkItem], failed_count: int) -> None:
        self._batch_controller = None
        updates = {item.source_path: item for item in results}
        self._cloud_items = [updates.get(item.source_path, item) for item in self._cloud_items]
        if failed_count:
            self._cloud_failed_count += failed_count
        self._continue_retry_or_preview()

    def _start_preview_generation(self) -> None:
        successful = [
            item for item in self._cloud_items
            if not item.recognition_error and item.result.raw_name
        ]
        if not successful:
            self._finish_without_preview("没有成功识别出可用名称")
            return
        self._preview_dir = Path(tempfile.mkdtemp(prefix="color-card-main-preview-"))
        self._preview_confirmed = False
        preview_ids = {item.source_path: str(index + 1) for index, item in enumerate(successful)}

        def process(item: _CloudWorkItem) -> _PreviewEntry:
            item_id = preview_ids[item.source_path]
            output = self._preview_dir / f"{item_id}{item.source_path.suffix.lower() or '.jpg'}"
            geometry = item.inspection.geometry
            if geometry is None:
                raise RuntimeError("健康检测结果缺少标尺几何信息")
            crop_image_from_geometry(item.source_path, output, self._crop_size_cm, geometry)
            return _PreviewEntry(
                item_id=item_id,
                source_path=item.source_path,
                preview_path=output,
                recognized_name=item.result.raw_name,
                cloud_result=item.result,
            )

        self.image_summary.setText(f"正在生成复核图，共 {len(successful)} 张")
        self._batch_controller = run_batch_task(
            successful,
            process,
            on_progress=lambda current, total, label: self.image_summary.setText(
                f"正在生成复核图 {current}/{total}：{label}"
            ),
            on_finished=self._on_preview_generation_finished,
            on_failed=self._on_cloud_failed,
            on_item_failed=lambda _index, label, message: self._crop_failures.append(
                f"{label}：{message}"
            ),
            max_workers=2,
            parent=self,
        )

    def _on_preview_generation_finished(self, results: list[_PreviewEntry], failed_count: int) -> None:
        self._batch_controller = None
        self._preview_entries = list(results)
        self._crop_failed_count = failed_count
        if not self._preview_entries:
            self._finish_without_preview("复核图生成失败")
            return
        if self.preview_checkbox.isChecked():
            self._open_preview_browser()
        else:
            self._save_preview_entries(
                [
                    {"id": item.item_id, "name": item.recognized_name, "include": True}
                    for item in self._preview_entries
                ]
            )

    def _open_preview_browser(self) -> None:
        payload = [
            {
                "id": item.item_id,
                "source_name": item.source_path.name,
                "source_path": str(item.source_path),
                "preview_path": str(item.preview_path),
                "recognized_name": item.recognized_name,
            }
            for item in self._preview_entries
        ]
        self._preview_server = MainImagePreviewServer(
            payload, parent=self, crop_size_cm=self._crop_size_cm
        )
        self._preview_server.confirmed.connect(self._save_preview_entries)
        QMessageBox.information(
            self,
            "准备打开浏览器",
            "云端识别已完成，将打开本地复核页面。请在浏览器中检查名称后点击“确认保存”。",
        )
        self._preview_server.start()
        self.confirm_button.setText("等待浏览器确认")
        self.image_summary.setText(
            f"复核页面已打开，共 {len(self._preview_entries)} 张；请在浏览器中确认保存（{self._preview_server.url}）"
        )

    def _save_preview_entries(self, selections: list[dict[str, object]]) -> None:
        if self._preview_confirmed:
            return
        self._preview_confirmed = True
        entry_map = {item.item_id: item for item in self._preview_entries}
        output_folder = self._crop_output_folder or self._default_output_folder()
        output_folder.mkdir(parents=True, exist_ok=True)
        saved = 0
        skipped = 0
        save_warnings: list[str] = []
        for selection in selections:
            item = entry_map.get(str(selection.get("id") or ""))
            if item is None:
                continue
            if not bool(selection.get("include", True)):
                skipped += 1
                continue
            name = _safe_filename(str(selection.get("name") or ""))
            if not name:
                name = _safe_filename(item.source_path.stem) or "未命名"
                save_warnings.append(f"{item.source_path.name} 名称为空，已使用原文件名")
            try:
                output_path = unique_output_path(output_folder, name, item.source_path.suffix)
                shutil.copy2(item.preview_path, output_path)
                saved += 1
            except Exception as exc:
                save_warnings.append(f"{item.source_path.name} 保存失败：{exc}")

        self._close_preview_server()
        self._finish_run(saved, skipped, save_warnings)

    def _finish_without_preview(self, reason: str) -> None:
        if self._cloud_items:
            self._close_preview_server()
            self._finish_run(0, 0, [reason])
            return
        self._close_preview_server()
        self._set_processing(False)
        self.image_summary.setText(reason)
        QMessageBox.warning(self, "主图处理未完成", f"{reason}。没有生成最终文件。")

    def _finish_run(self, saved: int, skipped: int, save_warnings: list[str]) -> None:
        finished_at = datetime.now()
        log_path = None
        api_results = [attempt for item in self._cloud_items for attempt in item.all_attempts()]
        if self._active_cloud_config is not None:
            try:
                log_path = write_recognition_log(
                    api_results,
                    failed_count=self._health_failed_count + self._cloud_failed_count + self._crop_failed_count,
                    cloud_config=self._active_cloud_config,
                    started_at=self._recognition_started_at or finished_at,
                    finished_at=finished_at,
                )
            except Exception as exc:
                save_warnings.append(f"日志写入失败：{exc}")

        usage = summarize_api_usage(api_results)
        started_at = self._recognition_started_at or finished_at
        wall_seconds = max(0.0, (finished_at - started_at).total_seconds())
        ratio = concurrency_ratio(usage["api_elapsed_seconds"], wall_seconds)
        output_folder = self._crop_output_folder or self._default_output_folder()
        message = (
            f"已保存 {saved} 张图片到：\n{output_folder}\n\n"
            f"跳过 {skipped} 张\n"
            f"输入 Token：{usage['prompt_tokens']:,}\n"
            f"输出 Token：{usage['completion_tokens']:,}\n"
            f"总 Token：{usage['total_tokens']:,}\n"
            f"预估费用：{usage['estimated_cost_rmb']:.6f} 元\n"
            f"实际耗时：{wall_seconds:.2f} 秒\n"
            f"API 耗时合计：{usage['api_elapsed_seconds']:.2f} 秒\n"
            f"并发倍率：{ratio:.2f}x"
        )
        if log_path is not None:
            message += f"\nToken 日志：{log_path}"
        details = self._crop_failures + save_warnings
        failed_names = [item.source_path.name for item in self._cloud_items if item.recognition_error]
        if failed_names:
            details.append("云端名称识别失败：" + ", ".join(failed_names[:10]))
        if details:
            message += "\n\n提示：\n" + "\n".join(details[:10])

        self._set_processing(False)
        self._clear_selected_images()
        self.confirm_button.setText("确认")
        if self._health_failed_count or self._cloud_failed_count or self._crop_failed_count or details:
            QMessageBox.warning(self, "主图处理完成（有提示）", message)
        else:
            QMessageBox.information(self, "主图处理完成", message)

    def _close_preview_server(self) -> None:
        if self._preview_server is not None:
            self._preview_server.close()
            self._preview_server.deleteLater()
            self._preview_server = None
        if self._preview_dir is not None:
            shutil.rmtree(self._preview_dir, ignore_errors=True)
            self._preview_dir = None

    def _on_cloud_failed(self, message: str) -> None:
        self._batch_controller = None
        self._set_processing(False)
        QMessageBox.critical(self, "处理失败", message)

    def _on_health_failed(self, message: str) -> None:
        self._batch_controller = None
        self._set_processing(False)
        QMessageBox.critical(self, "标尺检测失败", message)

    def _set_processing(self, processing: bool) -> None:
        self.output_folder_edit.setEnabled(not processing)
        self.browse_output_button.setEnabled(not processing)
        self.pick_images_button.setEnabled(not processing)
        self.confirm_button.setEnabled(not processing)
        self.size_combo.setEnabled(not processing)
        self.settings_button.setEnabled(not processing)
        self.preview_checkbox.setEnabled(not processing)

    def _clear_selected_images(self) -> None:
        self._image_paths = []
        self.image_summary.setText("未选择图片")

    def _cloud_config_from_settings(self) -> CloudVisionConfig | None | bool:
        base_url = self._recognition_settings.base_url.strip()
        api_key = self._recognition_settings.api_key.strip()
        model = self._recognition_settings.model.strip()
        if not any((base_url, api_key, model)):
            return None
        if not all((base_url, api_key, model)):
            QMessageBox.warning(self, "云端配置不完整", "Base URL、API Key、Model 必须同时填写。")
            return False
        return CloudVisionConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            horizontal_use_yolo=self._recognition_settings.horizontal_use_yolo,
            concurrency=self._recognition_settings.cloud_concurrency,
        )

    def _open_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("主图识别设置")
        layout = QVBoxLayout(dialog)
        form = QGridLayout()
        base_url_edit = QLineEdit(self._recognition_settings.base_url)
        api_key_edit = QLineEdit(self._recognition_settings.api_key)
        api_key_edit.setEchoMode(QLineEdit.Password)
        model_edit = QLineEdit(self._recognition_settings.model)
        form.addWidget(QLabel("Base URL:"), 0, 0)
        form.addWidget(base_url_edit, 0, 1)
        form.addWidget(QLabel("API Key:"), 1, 0)
        form.addWidget(api_key_edit, 1, 1)
        form.addWidget(QLabel("Model:"), 2, 0)
        form.addWidget(model_edit, 2, 1)

        ruler_spin = QSpinBox()
        ruler_spin.setRange(5, 50)
        ruler_spin.setValue(round(self._recognition_settings.main_image_ruler_search_ratio * 100))
        ruler_spin.setSuffix(" %")
        ruler_spin.setToolTip("在图片左上区域搜索标尺交点的最大范围；默认 20%。")
        form.addWidget(QLabel("标尺检测搜索范围："), 3, 0)
        form.addWidget(ruler_spin, 3, 1)
        layout.addLayout(form)

        note = QLabel(
            "主图会先在本地做标尺健康检测，只有通过的图片才调用云端。"
            "检测失败不会进行中心裁剪。此参数只作用于主图功能。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return

        self._recognition_settings = RecognitionSettings(
            base_url=base_url_edit.text().strip(),
            api_key=api_key_edit.text().strip(),
            model=model_edit.text().strip(),
            horizontal_use_yolo=self._recognition_settings.horizontal_use_yolo,
            cloud_concurrency=self._recognition_settings.cloud_concurrency,
            main_image_ruler_search_ratio=ruler_spin.value() / 100,
        )
        try:
            save_recognition_settings(self._recognition_settings)
            self._refresh_ruler_summary()
        except Exception as exc:
            QMessageBox.warning(self, "设置保存失败", str(exc))


def _recognize_main_image_attempt(
    path: Path,
    config: CloudVisionConfig,
    *,
    retry_count: int,
) -> tuple[ImageRecognitionResult, str]:
    try:
        result = recognize_main_image_name_result_with_cloud(path, config)
    except Exception as exc:
        message = str(exc)
        return (
            ImageRecognitionResult(
                image_path=path,
                raw_name="",
                base_name=path.stem,
                sequence=1,
                color_codes=[],
                warnings=[message],
                recognition_source="cloud_main_image_failed",
                api_retry_count=retry_count,
                api_model=config.model,
            ),
            message,
        )

    result.api_retry_count = retry_count
    if result.raw_name:
        return result, ""
    message = result.warnings[-1] if result.warnings else "云端未返回可识别名称"
    return result, message
