from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
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
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.core.cloud_recognition import (
    CloudVisionConfig,
    recognize_main_image_name_result_with_cloud,
)
from color_card_toolkit.core.image_rename import (
    ImageProcessResult,
    crop_main_images,
    rename_processed_image,
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
from color_card_toolkit.ui.batch_worker import run_batch_task


MAX_CLOUD_RETRY_ROUNDS = 3


@dataclass
class _MainImageWorkItem:
    source_path: Path
    image_result: ImageProcessResult
    attempts: list[ImageRecognitionResult]
    recognition_error: str = ""
    retryable: bool = False

    @property
    def name(self) -> str:
        return self.source_path.name


class MainImageCropPage(QWidget):
    def __init__(self, on_back) -> None:
        super().__init__()
        self._on_back = on_back
        self._image_paths: list[Path] = []
        self._batch_controller = None
        self._work_items: list[_MainImageWorkItem] = []
        self._active_cloud_config: CloudVisionConfig | None = None
        self._crop_output_folder: Path | None = None
        self._crop_failures: list[str] = []
        self._crop_failed_count = 0
        self._retry_round = 0
        self._recognition_started_at: datetime | None = None
        self._recognition_settings = load_recognition_settings()
        self._build_ui()

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
        settings_layout.addWidget(QLabel("选择截图的尺寸："), 0, 0)
        settings_layout.addWidget(self.size_combo, 0, 1)
        settings_layout.addWidget(QLabel("截图及改名后图片保存的地址："), 1, 0)
        settings_layout.addWidget(self.output_folder_edit, 1, 1)
        settings_layout.addWidget(self.browse_output_button, 1, 2)
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
        self.confirm_button = QPushButton("确认")
        self.confirm_button.clicked.connect(self._confirm_crop)
        footer.addWidget(self.confirm_button)
        layout.addStretch(1)
        layout.addLayout(footer)

    def _default_output_folder(self) -> Path:
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base_folder = Path(documents) if documents else Path.home() / "Documents"
        return base_folder / "主图截图及名称更改输出"

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

        output_folder_text = self.output_folder_edit.text().strip()
        output_folder = Path(output_folder_text) if output_folder_text else self._default_output_folder()
        crop_size_cm = int(self.size_combo.currentData())
        cloud_config = self._cloud_config_from_settings()
        if cloud_config is False:
            return
        if cloud_config is None:
            QMessageBox.warning(self, "未配置云端识别", "请先在“识别设置”中填写 Base URL、API Key 和 Model。")
            return

        self._set_processing(True)
        self._work_items = []
        self._active_cloud_config = cloud_config
        self._crop_output_folder = output_folder
        self._crop_failures = []
        self._crop_failed_count = 0
        self._retry_round = 0
        self._recognition_started_at = datetime.now()

        def process(path: Path) -> _MainImageWorkItem:
            attempt, recognition_error = _recognize_main_image_attempt(path, cloud_config, retry_count=0)

            def recognize_name(_source: Path) -> str:
                if recognition_error:
                    raise RuntimeError(recognition_error)
                return attempt.raw_name

            results = crop_main_images(
                [path],
                output_folder,
                None,
                crop_size_cm=crop_size_cm,
                name_recognizer=recognize_name,
            )
            if not results:
                raise RuntimeError("未生成输出文件")
            return _MainImageWorkItem(
                source_path=path,
                image_result=results[0],
                attempts=[attempt],
                recognition_error=recognition_error,
                retryable=bool(recognition_error),
            )

        def item_failed(index: int, label: str, message: str) -> None:
            self._crop_failures.append(f"{label}：{message}")

        self._batch_controller = run_batch_task(
            self._image_paths,
            process,
            on_progress=self._on_crop_progress,
            on_finished=self._on_initial_crop_finished,
            on_failed=self._on_crop_failed,
            on_item_failed=item_failed,
            max_workers=2,
            parent=self,
        )

    def _on_crop_progress(self, current: int, total: int, label: str) -> None:
        self.image_summary.setText(f"正在截图 {current}/{total}：{label}")

    def _on_initial_crop_finished(self, results: list[_MainImageWorkItem], failed_count: int) -> None:
        self._batch_controller = None
        self._work_items = list(results)
        self._crop_failed_count = failed_count
        self._continue_retry_or_finish()

    def _continue_retry_or_finish(self) -> None:
        pending = [item for item in self._work_items if item.retryable and item.recognition_error]
        if pending and self._retry_round < MAX_CLOUD_RETRY_ROUNDS:
            self._start_retry_round(pending)
            return
        self._finish_crop()

    def _start_retry_round(self, pending: list[_MainImageWorkItem]) -> None:
        cloud_config = self._active_cloud_config
        if cloud_config is None:
            self._finish_crop()
            return
        self._retry_round += 1
        retry_round = self._retry_round
        self.image_summary.setText(
            f"正在准备第 {retry_round}/{MAX_CLOUD_RETRY_ROUNDS} 轮重试，共 {len(pending)} 张"
        )

        def process(item: _MainImageWorkItem) -> _MainImageWorkItem:
            attempt, recognition_error = _recognize_main_image_attempt(
                item.source_path,
                cloud_config,
                retry_count=retry_round,
            )
            attempts = [*item.attempts, attempt]
            if recognition_error:
                return _MainImageWorkItem(
                    item.source_path,
                    item.image_result,
                    attempts,
                    recognition_error,
                    True,
                )
            try:
                renamed = rename_processed_image(item.image_result, attempt.raw_name)
            except Exception as exc:
                return _MainImageWorkItem(
                    item.source_path,
                    item.image_result,
                    attempts,
                    f"识别成功但改名失败：{exc}",
                    False,
                )
            return _MainImageWorkItem(item.source_path, renamed, attempts)

        self._batch_controller = run_batch_task(
            pending,
            process,
            on_progress=lambda current, total, label: self.image_summary.setText(
                f"第 {retry_round}/{MAX_CLOUD_RETRY_ROUNDS} 轮重试 {current}/{total}：{label}"
            ),
            on_finished=self._on_retry_round_finished,
            on_failed=self._on_crop_failed,
            max_workers=2,
            parent=self,
        )

    def _on_retry_round_finished(self, results: list[_MainImageWorkItem], failed_count: int) -> None:
        self._batch_controller = None
        updates = {item.source_path: item for item in results}
        self._work_items = [updates.get(item.source_path, item) for item in self._work_items]
        if failed_count:
            self._crop_failed_count += failed_count
        self._continue_retry_or_finish()

    def _finish_crop(self) -> None:
        self._batch_controller = None
        self._set_processing(False)
        output_folder = self._crop_output_folder or self._default_output_folder()
        image_results = [item.image_result for item in self._work_items]
        api_results = [attempt for item in self._work_items for attempt in item.attempts]
        recognition_failures = [item for item in self._work_items if item.recognition_error]
        success_count = len(image_results)
        finished_at = datetime.now()
        log_path = None
        if self._active_cloud_config is not None:
            try:
                log_path = write_recognition_log(
                    api_results,
                    failed_count=self._crop_failed_count + len(recognition_failures),
                    cloud_config=self._active_cloud_config,
                    started_at=self._recognition_started_at or finished_at,
                    finished_at=finished_at,
                )
            except Exception as exc:
                self._crop_failures.append(f"日志写入失败：{exc}")

        usage = summarize_api_usage(api_results)
        wall_seconds = max(0.0, (finished_at - (self._recognition_started_at or finished_at)).total_seconds())
        ratio = concurrency_ratio(usage["api_elapsed_seconds"], wall_seconds)
        warnings = [
            f"{result.source_path.name}：{warning}"
            for result in image_results
            for warning in result.warnings
        ]
        message = (
            f"已保存 {success_count} 张图片到：\n{output_folder}\n\n"
            f"输入 Token：{usage['prompt_tokens']:,}\n"
            f"输出 Token：{usage['completion_tokens']:,}\n"
            f"总 Token：{usage['total_tokens']:,}\n"
            f"预估费用：{usage['estimated_cost_rmb']:.6f} 元"
        )
        if self._recognition_started_at is not None:
            message += (
                f"\n实际耗时：{wall_seconds:.2f} 秒\n"
                f"API 耗时合计：{usage['api_elapsed_seconds']:.2f} 秒\n"
                f"并发倍率：{ratio:.2f}x"
            )
        if self._active_cloud_config is not None:
            message += (
                "\n计价参考："
                f"输入 {self._active_cloud_config.input_price_per_million_tokens:g} 元/百万 Token，"
                f"输出 {self._active_cloud_config.output_price_per_million_tokens:g} 元/百万 Token"
            )
        if log_path is not None:
            message += f"\nToken 日志：{log_path}"

        if recognition_failures:
            names = "\n".join(
                f"{item.source_path.name}：{item.recognition_error}"
                for item in recognition_failures[:10]
            )
            extra = len(recognition_failures) - 10
            if extra > 0:
                names += f"\n……另有 {extra} 张"
            message += (
                f"\n\n自动重试 {MAX_CLOUD_RETRY_ROUNDS} 次后仍有 "
                f"{len(recognition_failures)} 张名称识别失败，已保留原文件名：\n{names}\n\n请检查网络或云端配置。"
            )

        details = self._crop_failures + warnings
        if details:
            message += f"\n\n其他提示：\n" + "\n".join(details[:5])

        self._clear_selected_images()
        if self._crop_failed_count or recognition_failures or details:
            QMessageBox.warning(
                self,
                "截图完成（有提示）",
                message,
            )
            return
        QMessageBox.information(self, "截图完成", message)

    def _on_crop_failed(self, message: str) -> None:
        self._batch_controller = None
        self._set_processing(False)
        QMessageBox.critical(self, "截图失败", message)

    def _set_processing(self, processing: bool) -> None:
        self.output_folder_edit.setEnabled(not processing)
        self.browse_output_button.setEnabled(not processing)
        self.pick_images_button.setEnabled(not processing)
        self.confirm_button.setEnabled(not processing)
        self.size_combo.setEnabled(not processing)
        self.settings_button.setEnabled(not processing)

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
        dialog.setWindowTitle("识别设置")
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
        layout.addLayout(form)

        note = QLabel("这里与“叠贴转平贴模板生成”共用云端接口和模型配置；主图处理固定使用 2 并发。")
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
        )
        try:
            save_recognition_settings(self._recognition_settings)
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
