from __future__ import annotations

import html
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from PySide6.QtCore import QObject, Signal


class MainImagePreviewServer(QObject):
    """Small loopback-only review page for main-image recognition results."""

    confirmed = Signal(object)

    def __init__(
        self,
        items: list[dict[str, Any]],
        parent: QObject | None = None,
        *,
        crop_size_cm: int,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._crop_size_cm = crop_size_cm
        self._item_by_id = {str(item["id"]): item for item in items}
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="main-image-preview-server",
            daemon=True,
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/"

    def start(self) -> None:
        self._thread.start()
        webbrowser.open(self.url, new=2)

    def close(self) -> None:
        if self._thread.is_alive():
            self._server.shutdown()
        self._server.server_close()

    def _make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send_bytes(owner._render_html().encode("utf-8"), "text/html; charset=utf-8")
                    return
                image_routes = {"/image/": "preview_path", "/original/": "source_path"}
                for prefix, path_key in image_routes.items():
                    if not parsed.path.startswith(prefix):
                        continue
                    item_id = unquote(parsed.path.removeprefix(prefix))
                    item = owner._item_by_id.get(item_id)
                    if item is None or not item.get(path_key):
                        self.send_error(404)
                        return
                    image_path = Path(str(item[path_key]))
                    if not image_path.is_file():
                        self.send_error(404)
                        return
                    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
                    self._send_bytes(image_path.read_bytes(), content_type)
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path != "/confirm":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, list):
                        raise ValueError("确认数据必须是列表")
                    cleaned: list[dict[str, Any]] = []
                    for entry in payload:
                        if not isinstance(entry, dict):
                            continue
                        item_id = str(entry.get("id") or "")
                        if item_id not in owner._item_by_id:
                            continue
                        name = str(entry.get("name") or "").strip()
                        cleaned.append(
                            {
                                "id": item_id,
                                "name": name,
                                "include": bool(entry.get("include", True)),
                            }
                        )
                    owner.confirmed.emit(cleaned)
                    body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8")
                except Exception as exc:
                    body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=400)

            def log_message(self, format: str, *args: object) -> None:
                return

            def _send_bytes(self, body: bytes, content_type: str, *, status: int = 200) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _render_html(self) -> str:
        size = html.escape(f"{self._crop_size_cm} × {self._crop_size_cm} cm")
        cards = []
        for item in self._items:
            item_id = html.escape(str(item["id"]), quote=True)
            image_id = html.escape(quote(str(item["id"]), safe=""), quote=True)
            source_name = html.escape(str(item["source_name"]), quote=True)
            name = html.escape(str(item.get("recognized_name") or ""), quote=True)
            cards.append(
                f"""
                <article class="card" data-id="{item_id}">
                  <button class="image-wrap" data-original="/original/{image_id}" type="button" aria-label="放大核对 {source_name}">
                    <img src="/image/{image_id}" alt="{source_name}" loading="lazy">
                    <span class="image-hint">点击查看原图与裁剪图</span>
                  </button>
                  <div class="source">{source_name}</div>
                  <label>识别名称
                    <textarea class="name" data-id="{item_id}" rows="1" autocomplete="off">{name}</textarea>
                  </label>
                  <label class="skip"><input class="include" data-id="{item_id}" type="checkbox" checked> 保存这张</label>
                </article>
                """
            )
        return (
            _PREVIEW_PAGE.replace("{{crop_size}}", size)
            .replace("{{count}}", str(len(self._items)))
            .replace("{{cards}}", "".join(cards))
        )


_PREVIEW_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>主图识别结果复核 · {{crop_size}}</title>
<style>
:root { color-scheme:light; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:#f4f7fb; color:#172033; }
* { box-sizing:border-box; }
body { margin:0; }
body.reviewing { overflow:hidden; }
.page-header { position:sticky; top:0; z-index:2; padding:18px 28px; background:rgba(255,255,255,.97); border-bottom:1px solid #dce4ef; display:flex; align-items:center; gap:18px; flex-wrap:wrap; }
h1 { margin:0; font-size:22px; }
.heading { display:flex; flex-wrap:wrap; align-items:center; gap:12px; }
.size-badge { padding:7px 12px; border-radius:8px; color:#1664ae; background:#e8f2ff; font-size:15px; font-weight:700; white-space:nowrap; }
.hint { color:#68758a; font-size:13px; line-height:1.7; margin-top:7px; }
.page-header .actions { margin-left:auto; }
button { border:0; border-radius:8px; padding:11px 18px; font:inherit; font-size:14px; cursor:pointer; background:#1976d2; color:white; }
button:disabled { opacity:.5; cursor:default; }
button:focus-visible, textarea:focus-visible { outline:3px solid #78b5f3; outline-offset:2px; }
.secondary { color:#44516a; background:#eef2f7; }
main { padding:24px 28px 40px; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; max-width:1500px; margin:auto; }
.card { background:white; border:1px solid #dce4ef; border-radius:12px; padding:12px; box-shadow:0 4px 14px rgba(31,55,88,.06); min-width:0; }
.image-wrap { position:relative; width:100%; padding:0; aspect-ratio:1/1; background:#edf1f6; border-radius:8px; overflow:hidden; display:flex; align-items:center; justify-content:center; cursor:zoom-in; }
.image-wrap img { width:100%; height:100%; object-fit:contain; }
.image-hint { position:absolute; bottom:10px; left:50%; transform:translateX(-50%); white-space:nowrap; font-size:12px; padding:6px 10px; border-radius:6px; color:white; background:rgba(23,32,51,.72); }
.source { margin:11px 2px 8px; font-weight:600; font-size:13px; color:#44516a; overflow-wrap:anywhere; }
label { display:block; font-size:13px; color:#59677e; }
textarea { display:block; width:100%; margin-top:6px; padding:9px 10px; border:1px solid #c8d2e1; border-radius:7px; font:inherit; font-size:14px; color:#172033; line-height:1.6; resize:vertical; overflow:hidden; min-height:44px; overflow-wrap:anywhere; }
.skip { margin-top:9px; color:#66758d; }
.skip input { vertical-align:-2px; margin-right:6px; }
#status { position:fixed; z-index:5; left:50%; bottom:22px; transform:translateX(-50%); padding:10px 16px; border-radius:999px; background:#172033; color:white; display:none; box-shadow:0 5px 20px rgba(0,0,0,.22); }
dialog { width:min(1450px,96vw); height:94dvh; max-width:none; max-height:94dvh; margin:auto; padding:0; border:1px solid #dce4ef; border-radius:14px; background:white; color:#172033; box-shadow:0 20px 70px rgba(0,0,0,.3); }
dialog::backdrop { background:rgba(17,27,46,.68); }
.review-layout { display:flex; flex-direction:column; height:100%; }
.review-header { padding:16px 20px; display:flex; align-items:center; gap:16px; border-bottom:1px solid #dce4ef; flex-wrap:wrap; }
.review-title { flex:1; min-width:160px; }
.review-title strong { font-size:18px; }
#review-source { color:#68758a; font-size:12px; margin-top:5px; overflow-wrap:anywhere; }
.review-nav { display:flex; align-items:center; gap:8px; }
#review-position { font-size:13px; color:#68758a; min-width:50px; text-align:center; }
.compare { padding:16px 20px; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; flex:1; min-height:0; }
.pane { min-width:0; min-height:0; display:flex; flex-direction:column; border:1px solid #dce4ef; border-radius:10px; overflow:hidden; }
.pane-header { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:10px 12px; flex-wrap:wrap; background:#f8fafd; border-bottom:1px solid #dce4ef; }
.pane-title { font-size:13px; font-weight:600; }
.zoom-controls { display:flex; align-items:center; gap:5px; }
.zoom-controls button { padding:5px 9px; font-size:12px; background:#eaf0f8; color:#44516a; }
.zoom-readout { color:#68758a; font-size:12px; min-width:35px; text-align:center; }
.image-stage { flex:1; min-height:0; overflow:auto; background:#edf1f6; }
.image-canvas { min-width:100%; min-height:100%; width:max-content; display:grid; place-items:center; }
.detail-image { display:block; cursor:zoom-in; max-width:none; max-height:none; }
.detail-image.zoomed { cursor:zoom-out; }
.image-error { padding:20px; color:#a23a3a; }
.review-footer { padding:14px 20px 18px; border-top:1px solid #dce4ef; }
.name-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.name-heading .skip { margin:0; white-space:nowrap; }
.review-tip { color:#68758a; font-size:12px; margin:8px 0 0; }
@media (max-width:900px) { .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .review-header { padding:12px; gap:8px; } .compare { padding:12px; gap:10px; } .review-header .size-badge { font-size:12px; } }
@media (max-width:600px) { .page-header { padding:14px; } main { padding:14px; } .grid { grid-template-columns:1fr; } .page-header .actions { margin-left:0; } dialog { width:98vw; } .compare { overflow:auto; grid-template-columns:1fr; } .pane { min-height:300px; } .review-footer { padding:12px; } .review-nav button { padding:8px; } }
</style></head>
<body>
<header class="page-header">
  <div><div class="heading"><h1>主图识别结果复核</h1><span class="size-badge">裁剪尺寸：{{crop_size}}</span></div>
  <div class="hint">共 {{count}} 张 · 点击图片，放大对照完整原图与裁剪结果；名称可直接修改，取消勾选则跳过保存。</div></div>
  <div class="actions"><button id="confirm" type="button">确认保存</button></div>
</header>
<main><div class="grid">{{cards}}</div></main>
<dialog id="review-dialog" aria-labelledby="review-title">
  <div class="review-layout">
    <div class="review-header">
      <div class="review-title"><strong id="review-title">原图与裁剪结果核对</strong><div id="review-source"></div></div>
      <span class="size-badge">裁剪尺寸：{{crop_size}}</span>
      <div class="review-nav"><button id="previous" class="secondary" type="button">上一张</button><span id="review-position"></span><button id="next" class="secondary" type="button">下一张</button><button id="close-review" class="secondary" type="button">完成核对</button></div>
    </div>
    <div class="compare">
      <section class="pane" data-view="original">
        <div class="pane-header"><span class="pane-title">完整原图 · 核对名称标签</span><div class="zoom-controls"><button data-zoom="out" aria-label="缩小原图" type="button">−</button><span class="zoom-readout">1×</span><button data-zoom="in" aria-label="放大原图" type="button">＋</button><button data-zoom="fit" type="button">适应窗口</button></div></div>
        <div class="image-stage"><div class="image-canvas"><img id="original-image" class="detail-image" alt="完整原始扫描图"><span class="image-error" hidden>原图无法加载，请检查源文件是否仍在原位置。</span></div></div>
      </section>
      <section class="pane" data-view="crop">
        <div class="pane-header"><span class="pane-title">裁剪结果 · {{crop_size}}</span><div class="zoom-controls"><button data-zoom="out" aria-label="缩小裁剪图" type="button">−</button><span class="zoom-readout">1×</span><button data-zoom="in" aria-label="放大裁剪图" type="button">＋</button><button data-zoom="fit" type="button">适应窗口</button></div></div>
        <div class="image-stage"><div class="image-canvas"><img id="crop-image" class="detail-image" alt="裁剪结果"><span class="image-error" hidden>裁剪图无法加载。</span></div></div>
      </section>
    </div>
    <div class="review-footer">
      <div class="name-heading"><label for="review-name">识别名称 · 可修改，自动同步到列表</label><label class="skip"><input id="review-include" type="checkbox">保存这张</label></div>
      <textarea id="review-name" rows="1" autocomplete="off"></textarea>
      <p class="review-tip">点击大图可继续放大，滚动查看细节；使用 ＋ / − 调整倍率，Esc 关闭。全部核对后回到列表点击“确认保存”。</p>
    </div>
  </div>
</dialog>
<div id="status" role="status"></div>
<script>
const cards = [...document.querySelectorAll('.card')];
const dialog = document.getElementById('review-dialog');
const reviewName = document.getElementById('review-name');
const reviewInclude = document.getElementById('review-include');
const statusEl = document.getElementById('status');
let currentIndex = 0;

function resizeName(field) {
  field.style.height = 'auto';
  field.style.height = Math.max(44, field.scrollHeight + 2) + 'px';
}
document.querySelectorAll('textarea').forEach(field => {
  resizeName(field);
  field.addEventListener('input', () => resizeName(field));
});

const views = [...document.querySelectorAll('.pane')].map(pane => {
  const view = {pane, stage:pane.querySelector('.image-stage'), image:pane.querySelector('img'), zoom:1};
  view.image.addEventListener('load', () => {
    view.image.hidden = false;
    pane.querySelector('.image-error').hidden = true;
    renderZoom(view);
  });
  view.image.addEventListener('error', () => {
    view.image.hidden = true;
    pane.querySelector('.image-error').hidden = false;
  });
  view.image.addEventListener('click', () => setZoom(view, view.zoom === 1 ? 3 : 1));
  pane.querySelectorAll('[data-zoom]').forEach(button => button.addEventListener('click', () => {
    const action = button.dataset.zoom;
    setZoom(view, action === 'fit' ? 1 : view.zoom * (action === 'in' ? 1.5 : 1 / 1.5));
  }));
  new ResizeObserver(() => renderZoom(view)).observe(view.stage);
  return view;
});

function renderZoom(view) {
  if (!view.image.naturalWidth || !view.stage.clientWidth || !view.stage.clientHeight) return;
  const fit = Math.min(view.stage.clientWidth / view.image.naturalWidth, view.stage.clientHeight / view.image.naturalHeight, 1);
  view.image.style.width = Math.max(1, Math.floor(view.image.naturalWidth * fit * view.zoom)) + 'px';
  view.image.style.height = Math.max(1, Math.floor(view.image.naturalHeight * fit * view.zoom)) + 'px';
  view.image.classList.toggle('zoomed', view.zoom > 1);
  view.pane.querySelector('.zoom-readout').textContent = Number(view.zoom.toFixed(1)) + '×';
}
function setZoom(view, zoom) {
  view.zoom = Math.max(1, Math.min(8, zoom));
  renderZoom(view);
  if (view.zoom === 1) {view.stage.scrollLeft = 0; view.stage.scrollTop = 0;}
}

function openReview(index) {
  currentIndex = index;
  const card = cards[index];
  document.getElementById('review-source').textContent = card.querySelector('.source').textContent;
  document.getElementById('review-position').textContent = (index + 1) + ' / ' + cards.length;
  document.getElementById('previous').disabled = index === 0;
  document.getElementById('next').disabled = index === cards.length - 1;
  reviewName.value = card.querySelector('.name').value;
  reviewInclude.checked = card.querySelector('.include').checked;
  if (!dialog.open) {dialog.showModal(); document.body.classList.add('reviewing');}
  resizeName(reviewName);
  views.forEach(view => {
    view.zoom = 1;
    view.stage.scrollLeft = 0; view.stage.scrollTop = 0;
    view.image.hidden = false;
    view.pane.querySelector('.image-error').hidden = true;
    view.image.src = view.pane.dataset.view === 'original' ? card.querySelector('.image-wrap').dataset.original : card.querySelector('img').getAttribute('src');
    renderZoom(view);
  });
}
cards.forEach((card, index) => card.querySelector('.image-wrap').addEventListener('click', () => openReview(index)));
reviewName.addEventListener('input', () => {
  const field = cards[currentIndex].querySelector('.name');
  field.value = reviewName.value;
  resizeName(field);
});
reviewInclude.addEventListener('change', () => {cards[currentIndex].querySelector('.include').checked = reviewInclude.checked;});
document.getElementById('previous').addEventListener('click', () => openReview(currentIndex - 1));
document.getElementById('next').addEventListener('click', () => openReview(currentIndex + 1));
document.getElementById('close-review').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => document.body.classList.remove('reviewing'));
dialog.addEventListener('click', event => {if (event.target === dialog) dialog.close();});

function showStatus(text) {statusEl.textContent = text; statusEl.style.display = 'block';}
document.getElementById('confirm').addEventListener('click', async () => {
  const button = document.getElementById('confirm');
  button.disabled = true; showStatus('正在提交确认…');
  const rows = cards.map(card => ({id:card.dataset.id, name:card.querySelector('.name').value.trim(), include:card.querySelector('.include').checked}));
  try {
    const response = await fetch('/confirm', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(rows)});
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || '提交失败');
    showStatus('已提交，正在回到桌面软件…');
  } catch (error) {button.disabled = false; showStatus('提交失败：' + error.message);}
});
</script></body></html>"""
