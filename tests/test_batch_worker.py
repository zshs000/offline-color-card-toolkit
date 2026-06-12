from __future__ import annotations

import os
import subprocess
import sys
import textwrap

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


def test_batch_task_survives_when_page_releases_controller_on_finish() -> None:
    script = textwrap.dedent(
        """
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication, QTimer
        from color_card_toolkit.ui.batch_worker import run_batch_task

        app = QCoreApplication([])
        holder = {}

        def finished(results, failed_count):
            holder["controller"] = None
            QTimer.singleShot(200, app.quit)

        holder["controller"] = run_batch_task(
            [1, 2, 3],
            lambda item: item,
            on_progress=lambda current, total, label: None,
            on_finished=finished,
            on_failed=lambda message: app.quit(),
        )
        QTimer.singleShot(5000, app.quit)
        app.exec()
        print("exit ok")
        """
    )
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    process = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=10,
    )

    assert process.returncode == 0, process.stderr
    assert "exit ok" in process.stdout
