from __future__ import annotations

from color_card_toolkit.ui.batch_worker import _BatchWorker


def test_batch_worker_processes_items_and_continues_after_item_failure() -> None:
    worker = _BatchWorker([1, 2, 3], _processor)
    progress: list[tuple[int, int, str]] = []
    failures: list[tuple[int, str, str]] = []
    finished: list[tuple[list[str], int]] = []
    fatal: list[str] = []

    worker.progress.connect(lambda current, total, label: progress.append((current, total, label)))
    worker.item_failed.connect(lambda index, label, error: failures.append((index, label, error)))
    worker.finished.connect(lambda results, failed_count: finished.append((results, failed_count)))
    worker.failed.connect(fatal.append)

    worker.run()

    assert progress == [(1, 3, "1"), (2, 3, "2"), (3, 3, "3")]
    assert failures == [(1, "2", "bad item")]
    assert finished == [(["ok-1", "ok-3"], 1)]
    assert fatal == []


def _processor(item: int) -> str:
    if item == 2:
        raise ValueError("bad item")
    return f"ok-{item}"
