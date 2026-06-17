from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from color_card_toolkit.review_app.data import BoxFeedback, ItemFeedback, build_export_bundle, load_review_items

REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).resolve().with_name("static")
DEFAULT_DATASET_ROOT = REPO_ROOT / "datasets" / "color_card_roi"


def build_review_payload(dataset_root: Path) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    items = load_review_items(dataset_root)
    return {
        "datasetRoot": str(dataset_root.relative_to(REPO_ROOT.resolve())).replace('\\', '/'),
        "items": [
            {
                "itemId": item.item_id,
                "orientation": item.orientation,
                "split": item.split,
                "sourceImage": item.source_image,
                "outputImage": item.output_image,
                "previewImage": item.preview_image,
                "labelPath": item.label_path,
                "width": item.width,
                "height": item.height,
                "boxCount": item.box_count,
                "boxes": [
                    {
                        "role": box.role,
                        "classId": box.class_id,
                        "centerX": box.center_x,
                        "centerY": box.center_y,
                        "width": box.width,
                        "height": box.height,
                    }
                    for box in item.boxes
                ],
            }
            for item in items
        ],
    }


def build_export_payload(payload: dict[str, object]) -> dict[str, str]:
    feedback_items: list[ItemFeedback] = []
    for item in payload.get("items", []):
        boxes = [BoxFeedback(role=box["role"], note=box.get("note", "")) for box in item.get("boxFeedback", [])]
        feedback_items.append(
            ItemFeedback(
                item_id=item["itemId"],
                whole_image_bad=bool(item.get("wholeImageBad", False)),
                note=item.get("note", ""),
                box_feedback=boxes,
            )
        )
    bundle = build_export_bundle(feedback_items)
    return {"structuredText": bundle.structured_text, "humanText": bundle.human_text}


class ReviewAppHandler(BaseHTTPRequestHandler):
    dataset_root = DEFAULT_DATASET_ROOT

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/review-data":
            self._write_json(build_review_payload(self.dataset_root))
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
        if parsed.path != "/api/export":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body.decode("utf-8") or "{}")
        self._write_json(build_export_payload(payload))

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


def serve(host: str = "127.0.0.1", port: int = 8765, dataset_root: Path | None = None) -> ThreadingHTTPServer:
    if dataset_root is not None:
        ReviewAppHandler.dataset_root = dataset_root
    return ThreadingHTTPServer((host, port), ReviewAppHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the color card review app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    args = parser.parse_args(argv)
    server = serve(args.host, args.port, Path(args.dataset_root))
    print(f"Review app running at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
