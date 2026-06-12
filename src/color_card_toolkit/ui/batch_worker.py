from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _BatchWorker(QObject):
    progress = Signal(int, int, str)
    item_failed = Signal(int, str, str)
    finished = Signal(object, int)
    failed = Signal(str)

    def __init__(self, items: Sequence[Any], processor: Callable[[Any], Any], *, max_workers: int = 1) -> None:
        super().__init__()
        self._items = list(items)
        self._processor = processor
        self._max_workers = max(1, int(max_workers))

    def run(self) -> None:
        if self._max_workers <= 1 or len(self._items) <= 1:
            self._run_serial()
        else:
            self._run_parallel()

    def _run_serial(self) -> None:
        results: list[Any] = []
        failed_count = 0
        total = len(self._items)
        try:
            for index, item in enumerate(self._items):
                label = _item_label(item)
                self.progress.emit(index + 1, total, label)
                try:
                    results.append(self._processor(item))
                except Exception as exc:
                    failed_count += 1
                    self.item_failed.emit(index, label, str(exc))
            self.finished.emit(results, failed_count)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _run_parallel(self) -> None:
        results_by_index: dict[int, Any] = {}
        failed_count = 0
        completed_count = 0
        total = len(self._items)
        workers = min(self._max_workers, total)
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="color-card-batch") as executor:
                future_items = {
                    executor.submit(self._processor, item): (index, item)
                    for index, item in enumerate(self._items)
                }
                for future in as_completed(future_items):
                    index, item = future_items[future]
                    label = _item_label(item)
                    completed_count += 1
                    try:
                        results_by_index[index] = future.result()
                    except Exception as exc:
                        failed_count += 1
                        self.item_failed.emit(index, label, str(exc))
                    self.progress.emit(completed_count, total, label)
            ordered_results = [
                results_by_index[index]
                for index in range(total)
                if index in results_by_index
            ]
            self.finished.emit(ordered_results, failed_count)
        except Exception as exc:
            self.failed.emit(str(exc))


_active_controllers: dict[int, "BatchTaskController"] = {}


class BatchTaskController(QObject):
    def __init__(
        self,
        items: Sequence[Any],
        processor: Callable[[Any], Any],
        *,
        on_progress: Callable[[int, int, str], None],
        on_finished: Callable[[list[Any], int], None],
        on_failed: Callable[[str], None],
        on_item_failed: Callable[[int, str, str], None] | None = None,
        max_workers: int = 1,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_progress = on_progress
        self._on_finished = on_finished
        self._on_failed = on_failed
        self._on_item_failed = on_item_failed
        self.thread = QThread(self)
        self.worker = _BatchWorker(items, processor, max_workers=max_workers)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._handle_progress)
        self.worker.item_failed.connect(self._handle_item_failed)
        self.worker.finished.connect(self._handle_finished)
        self.worker.failed.connect(self._handle_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._release)

    def start(self) -> None:
        _active_controllers[id(self)] = self
        self.thread.start()

    @Slot(int, int, str)
    def _handle_progress(self, current: int, total: int, label: str) -> None:
        self._on_progress(current, total, label)

    @Slot(int, str, str)
    def _handle_item_failed(self, index: int, label: str, message: str) -> None:
        if self._on_item_failed is not None:
            self._on_item_failed(index, label, message)

    @Slot(object, int)
    def _handle_finished(self, results: list[Any], failed_count: int) -> None:
        self._on_finished(results, failed_count)

    @Slot(str)
    def _handle_failed(self, message: str) -> None:
        self._on_failed(message)

    @Slot()
    def _release(self) -> None:
        _active_controllers.pop(id(self), None)
        self.deleteLater()


def run_batch_task(
    items: Sequence[Any],
    processor: Callable[[Any], Any],
    *,
    on_progress: Callable[[int, int, str], None],
    on_finished: Callable[[list[Any], int], None],
    on_failed: Callable[[str], None],
    on_item_failed: Callable[[int, str, str], None] | None = None,
    max_workers: int = 1,
    parent: QObject | None = None,
) -> BatchTaskController:
    controller = BatchTaskController(
        items,
        processor,
        on_progress=on_progress,
        on_finished=on_finished,
        on_failed=on_failed,
        on_item_failed=on_item_failed,
        max_workers=max_workers,
        parent=parent,
    )
    controller.start()
    return controller


def _item_label(item: Any) -> str:
    name = getattr(item, "name", None)
    return str(name if name else item)
