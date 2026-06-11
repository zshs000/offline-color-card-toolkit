from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal


class _BatchWorker(QObject):
    progress = Signal(int, int, str)
    item_failed = Signal(int, str, str)
    finished = Signal(object, int)
    failed = Signal(str)

    def __init__(self, items: Sequence[Any], processor: Callable[[Any], Any]) -> None:
        super().__init__()
        self._items = list(items)
        self._processor = processor

    def run(self) -> None:
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


@dataclass
class BatchTaskController:
    thread: QThread
    worker: _BatchWorker


def run_batch_task(
    items: Sequence[Any],
    processor: Callable[[Any], Any],
    *,
    on_progress: Callable[[int, int, str], None],
    on_finished: Callable[[list[Any], int], None],
    on_failed: Callable[[str], None],
    on_item_failed: Callable[[int, str, str], None] | None = None,
    parent: QObject | None = None,
) -> BatchTaskController:
    thread = QThread(parent)
    worker = _BatchWorker(items, processor)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    if on_item_failed is not None:
        worker.item_failed.connect(on_item_failed)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return BatchTaskController(thread=thread, worker=worker)


def _item_label(item: Any) -> str:
    name = getattr(item, "name", None)
    return str(name if name else item)
