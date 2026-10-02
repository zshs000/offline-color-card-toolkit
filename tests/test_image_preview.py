from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from color_card_toolkit.ui.main_image_preview import MainImagePreviewServer


def test_confirmation_response_precedes_desktop_signal_and_shutdown(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    server = MainImagePreviewServer([{"id": "1"}], crop_size_cm=10)
    monkeypatch.setattr("color_card_toolkit.ui.main_image_preview.webbrowser.open", lambda *args, **kwargs: True)
    events = []
    finished = threading.Event()
    handler = server._server.RequestHandlerClass
    send_bytes = handler._send_bytes

    def record_response(self, body, content_type, *, status=200):
        send_bytes(self, body, content_type, status=status)
        events.append("response")

    def on_confirm(rows):
        events.append(rows)
        server.close()
        finished.set()

    monkeypatch.setattr(handler, "_send_bytes", record_response)
    server.confirmed.connect(on_confirm, Qt.DirectConnection)
    server.start()
    try:
        payload = [{"id": "1", "name": " Reviewed ", "include": True}]
        request = Request(
            server.url + "confirm", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=3) as response:
            assert json.load(response) == {"ok": True}
        assert finished.wait(3)
        assert events == ["response", [{"id": "1", "name": "Reviewed", "include": True}]]
    finally:
        server.close()
        app.processEvents()


def test_invalid_confirmation_does_not_trigger_desktop_save(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    server = MainImagePreviewServer([], crop_size_cm=10)
    monkeypatch.setattr("color_card_toolkit.ui.main_image_preview.webbrowser.open", lambda *args, **kwargs: True)
    confirmed = []
    server.confirmed.connect(confirmed.append, Qt.DirectConnection)
    server.start()
    try:
        request = Request(server.url + "confirm", data=b"{}", headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=3)
        assert error.value.code == 400
        assert json.load(error.value)["ok"] is False
        assert confirmed == []
    finally:
        server.close()
        app.processEvents()


def test_preview_submission_handles_close_restrictions_and_failures() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the browser submission script")
    server = MainImagePreviewServer([], crop_size_cm=10)
    try:
        page = server._render_html()
    finally:
        server.close()
    result = subprocess.run(
        [node, str(Path(__file__).with_name("test_image_preview_frontend.cjs"))],
        input=page, text=True, encoding="utf-8", capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_image_preview_renders_size_and_original_comparison() -> None:
    app = QApplication.instance() or QApplication([])
    source = Path("/tmp/original.jpg")
    crop = Path("/tmp/crop.jpg")
    server = MainImagePreviewServer(
        [
            {
                "id": "1",
                "source_name": "原图-标签完整名称.jpg",
                "source_path": str(source),
                "preview_path": str(crop),
                "recognized_name": "识别名称",
            }
        ],
        crop_size_cm=15,
    )
    try:
        page = server._render_html()
    finally:
        server.close()
        app.processEvents()

    assert "裁剪尺寸：15 × 15 cm" in page
    assert "完整原图 · 核对名称标签" in page
    assert "/original/1" in page
    assert "点击查看原图与裁剪图" in page
    assert "上一张" in page and "下一张" in page
    assert "识别名称" in page
