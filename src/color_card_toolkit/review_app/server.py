from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from color_card_toolkit.review_app.data import export_yolo_dataset, load_annotation_payload, save_item_annotation

REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).resolve().with_name("static")
DEFAULT_RAW_ROOT = REPO_ROOT / "datasets" / "raw_images"
DEFAULT_ANNOTATION_PATH = REPO_ROOT / "datasets" / "manual_annotations" / "annotations.json"
DEFAULT_EXPORT_ROOT = REPO_ROOT / "datasets" / "manual_annotations" / "exports"


class ReviewAppHandler(BaseHTTPRequestHandler):
    raw_root = DEFAULT_RAW_ROOT
    annotation_path = DEFAULT_ANNOTATION_PATH
    export_root = DEFAULT_EXPORT_ROOT

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/annotation-data":
            self._write_json(load_annotation_payload(self.raw_root, self.annotation_path, REPO_ROOT))
            return
        if path == "/":
            self._serve_file(STATIC_DIR / "index.html")
            return
        if path.startswith("/static/"):
            self._serve_static_file(path.removeprefix("/static/"))
            return
        if path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_repo_file(path.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/save-annotation", "/api/export-yolo"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body.decode("utf-8") or "{}")
        if parsed.path == "/api/save-annotation":
            save_item_annotation(
                self.annotation_path,
                item_id=str(payload["itemId"]),
                orientation=str(payload["orientation"]),
                boxes=dict(payload.get("boxes", {})),
                code_column_count=int(payload.get("codeColumnCount", 2)),
            )
            self._write_json({"ok": True})
            return
        self._write_json(export_yolo_dataset(self.raw_root, self.annotation_path, self.export_root, REPO_ROOT))

    def _serve_repo_file(self, relative_path: str) -> None:
        target = (REPO_ROOT / relative_path).resolve()
        if not target.exists() or not target.is_file() or REPO_ROOT not in target.parents and target != REPO_ROOT:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_file(target)

    def _serve_static_file(self, relative_path: str) -> None:
        target = (STATIC_DIR / relative_path).resolve()
        if not target.exists() or not target.is_file() or STATIC_DIR not in target.parents and target != STATIC_DIR:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_file(target)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime_type, _ = mimetypes.guess_type(path.name)
        content_type = mime_type or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    raw_root: Path | None = None,
    annotation_path: Path | None = None,
    export_root: Path | None = None,
) -> ThreadingHTTPServer:
    if raw_root is not None:
        ReviewAppHandler.raw_root = raw_root
    if annotation_path is not None:
        ReviewAppHandler.annotation_path = annotation_path
    if export_root is not None:
        ReviewAppHandler.export_root = export_root
    return ThreadingHTTPServer((host, port), ReviewAppHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the color card annotation app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--annotation-path", default=str(DEFAULT_ANNOTATION_PATH))
    parser.add_argument("--export-root", default=str(DEFAULT_EXPORT_ROOT))
    args = parser.parse_args(argv)
    server = serve(
        args.host,
        args.port,
        Path(args.raw_root),
        Path(args.annotation_path),
        Path(args.export_root),
    )
    print(f"Annotation app running at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
