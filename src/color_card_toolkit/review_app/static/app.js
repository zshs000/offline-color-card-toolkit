const STORAGE_KEY = "color-card-review-feedback-v1";

const state = {
  datasetRoot: "",
  items: [],
  currentId: null,
  filters: {
    orientation: "all",
    search: "",
    flaggedOnly: false,
  },
  feedback: loadFeedback(),
};

const el = {
  itemList: document.getElementById("itemList"),
  currentMeta: document.getElementById("currentMeta"),
  currentTitle: document.getElementById("currentTitle"),
  imageFrame: document.querySelector(".image-frame"),
  previewImage: document.getElementById("previewImage"),
  overlayLayer: document.getElementById("overlayLayer"),
  boxList: document.getElementById("boxList"),
  structuredText: document.getElementById("structuredText"),
  humanText: document.getElementById("humanText"),
  searchInput: document.getElementById("searchInput"),
  orientationFilter: document.getElementById("orientationFilter"),
  flaggedOnly: document.getElementById("flaggedOnly"),
  wholeImageBad: document.getElementById("wholeImageBad"),
  nextItem: document.getElementById("nextItem"),
  itemNote: document.getElementById("itemNote"),
  copyStructured: document.getElementById("copyStructured"),
  copyHuman: document.getElementById("copyHuman"),
  clearStorage: document.getElementById("clearStorage"),
};

init();

async function init() {
  const response = await fetch("/api/review-data");
  const payload = await response.json();
  state.datasetRoot = payload.datasetRoot;
  state.items = payload.items;
  state.currentId = state.items[0]?.itemId ?? null;
  syncMissingFeedback();
  bindEvents();
  render();
}

function bindEvents() {
  el.searchInput.addEventListener("input", () => {
    state.filters.search = el.searchInput.value.trim().toLowerCase();
    renderList();
  });

  el.orientationFilter.addEventListener("change", () => {
    state.filters.orientation = el.orientationFilter.value;
    renderList();
  });

  el.flaggedOnly.addEventListener("change", () => {
    state.filters.flaggedOnly = el.flaggedOnly.checked;
    renderList();
  });

  el.wholeImageBad.addEventListener("change", () => {
    const feedback = currentFeedback();
    feedback.wholeImageBad = el.wholeImageBad.checked;
    saveFeedback();
    renderSummary();
    renderList();
  });

  el.nextItem.addEventListener("click", () => {
    moveToNextItem();
  });

  el.itemNote.addEventListener("input", () => {
    const feedback = currentFeedback();
    feedback.note = el.itemNote.value;
    saveFeedback();
    renderSummary();
    renderList();
  });

  el.copyStructured.addEventListener("click", async () => {
    await navigator.clipboard.writeText(buildExport().structuredText || "");
  });

  el.copyHuman.addEventListener("click", async () => {
    await navigator.clipboard.writeText(buildExport().humanText || "");
  });

  el.clearStorage.addEventListener("click", () => {
    localStorage.removeItem(STORAGE_KEY);
    state.feedback = {};
    syncMissingFeedback();
    render();
  });
}

function render() {
  if (!state.currentId && state.items.length) {
    state.currentId = state.items[0].itemId;
  }
  renderList();
  renderDetail();
  renderSummary();
}

function renderList() {
  const items = filteredItems();
  el.itemList.innerHTML = "";
  for (const item of items) {
    const flagged = itemHasFeedback(item.itemId);
    const card = document.createElement("button");
    card.type = "button";
    card.className = `item-card ${item.itemId === state.currentId ? "active" : ""} ${flagged ? "flagged" : ""}`;
    card.dataset.itemId = item.itemId;
    card.innerHTML = `
      <div class="row">
        <div class="id">${escapeHtml(item.itemId)}</div>
        <span class="chip ${flagged ? "bad" : ""}">${flagged ? "已标错" : "正常"}</span>
      </div>
      <div class="meta">${escapeHtml(orientationLabel(item.orientation))} | ${escapeHtml(splitLabel(item.split))} | ${item.boxCount} 个框</div>
    `;
    card.addEventListener("click", () => {
      state.currentId = item.itemId;
      render();
    });
    el.itemList.appendChild(card);
  }
}

function renderDetail() {
  const item = currentItem();
  if (!item) {
    el.currentMeta.textContent = "";
    el.currentTitle.textContent = "没有图片";
    el.previewImage.removeAttribute("src");
    el.overlayLayer.innerHTML = "";
    el.boxList.innerHTML = "";
    el.wholeImageBad.checked = false;
    el.itemNote.value = "";
    return;
  }

  const feedback = currentFeedback();
  el.currentMeta.textContent = `${orientationLabel(item.orientation)} | ${splitLabel(item.split)} | ${item.width}x${item.height}`;
  el.currentTitle.textContent = item.itemId;
  el.imageFrame.style.aspectRatio = `${item.width} / ${item.height}`;
  el.previewImage.src = toWebPath(item.outputImage);
  el.previewImage.alt = item.itemId;
  el.wholeImageBad.checked = Boolean(feedback.wholeImageBad);
  el.itemNote.value = feedback.note ?? "";
  el.nextItem.disabled = filteredItems().length <= 1;
  renderBoxes(item, feedback);
  renderBoxList(item, feedback);
}

function renderBoxes(item, feedback) {
  el.overlayLayer.innerHTML = "";
  for (const box of item.boxes) {
    const boxState = feedback.boxes?.[box.role] ?? { bad: false, note: "" };
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `box-overlay role-${box.role} ${boxState.bad ? "flagged" : ""}`;
    btn.style.left = `${(box.centerX - box.width / 2) * 100}%`;
    btn.style.top = `${(box.centerY - box.height / 2) * 100}%`;
    btn.style.width = `${box.width * 100}%`;
    btn.style.height = `${box.height * 100}%`;
    btn.title = `${friendlyRole(box.role)}${boxState.bad ? "（已标错）" : ""}`;
    btn.innerHTML = `<span class="mark">${boxState.bad ? "!" : ""}</span><span>${escapeHtml(friendlyRole(box.role))}</span>`;
    btn.addEventListener("click", () => toggleBox(box.role));
    el.overlayLayer.appendChild(btn);
  }
}

function renderBoxList(item, feedback) {
  el.boxList.innerHTML = "";
  for (const box of item.boxes) {
    const boxState = feedback.boxes?.[box.role] ?? { bad: false, note: "" };
    const row = document.createElement("div");
    row.className = "box-row";

    const label = document.createElement("label");
    label.className = "checkbox-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(boxState.bad);

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = friendlyRole(box.role);

    label.appendChild(checkbox);
    label.appendChild(name);

    const noteInput = document.createElement("input");
    noteInput.type = "text";
    noteInput.placeholder = "写问题";
    noteInput.value = boxState.note ?? "";

    checkbox.addEventListener("change", () => setBoxBad(box.role, checkbox.checked));
    noteInput.addEventListener("input", () => setBoxNote(box.role, noteInput.value));

    row.appendChild(label);
    row.appendChild(noteInput);
    el.boxList.appendChild(row);
  }
}

function renderSummary() {
  const bundle = buildExport();
  el.structuredText.value = bundle.structuredText;
  el.humanText.value = bundle.humanText;
}

function filteredItems() {
  return state.items.filter((item) => {
    if (state.filters.orientation !== "all" && item.orientation !== state.filters.orientation) {
      return false;
    }
    if (state.filters.search && !item.itemId.toLowerCase().includes(state.filters.search)) {
      return false;
    }
    if (state.filters.flaggedOnly && !itemHasFeedback(item.itemId)) {
      return false;
    }
    return true;
  });
}

function itemHasFeedback(itemId) {
  const fb = state.feedback[itemId];
  if (!fb) {
    return false;
  }
  if (fb.wholeImageBad || (fb.note && fb.note.trim())) {
    return true;
  }
  return Object.values(fb.boxes ?? {}).some((box) => box.bad || (box.note && box.note.trim()));
}

function currentItem() {
  return state.items.find((item) => item.itemId === state.currentId) ?? null;
}

function currentFeedback() {
  const item = currentItem();
  if (!item) {
    return { wholeImageBad: false, note: "", boxes: {} };
  }
  state.feedback[item.itemId] ??= { wholeImageBad: false, note: "", boxes: {} };
  return state.feedback[item.itemId];
}

function moveToNextItem() {
  const items = filteredItems();
  if (!items.length) {
    return;
  }

  const currentIndex = items.findIndex((item) => item.itemId === state.currentId);
  const nextIndex = currentIndex >= 0 && currentIndex < items.length - 1 ? currentIndex + 1 : 0;
  state.currentId = items[nextIndex].itemId;
  render();
  scrollCurrentItemIntoView();
}

function toggleBox(role) {
  const feedback = currentFeedback();
  feedback.boxes ??= {};
  feedback.boxes[role] ??= { bad: false, note: "" };
  feedback.boxes[role].bad = !feedback.boxes[role].bad;
  saveFeedback();
  render();
}

function setBoxBad(role, bad) {
  const feedback = currentFeedback();
  feedback.boxes ??= {};
  feedback.boxes[role] ??= { bad: false, note: "" };
  feedback.boxes[role].bad = bad;
  saveFeedback();
  renderSummary();
  renderList();
  renderBoxes(currentItem(), feedback);
}

function setBoxNote(role, note) {
  const feedback = currentFeedback();
  feedback.boxes ??= {};
  feedback.boxes[role] ??= { bad: false, note: "" };
  feedback.boxes[role].note = note;
  saveFeedback();
  renderSummary();
  renderList();
}

function buildExport() {
  const items = Object.entries(state.feedback)
    .filter(([, fb]) => itemPayloadHasFeedback(fb))
    .map(([itemId, fb]) => ({ itemId, ...fb }));

  const structured = [];
  const human = [];

  for (const item of items) {
    const notes = [];

    if (item.wholeImageBad) {
      let line = `${item.itemId} | whole_image_bad`;
      if (item.note && item.note.trim()) {
        line += ` | note=${item.note.trim()}`;
        notes.push(`整张图：${item.note.trim()}`);
      } else {
        notes.push("整张图有问题");
      }
      structured.push(line);
    } else if (item.note && item.note.trim()) {
      structured.push(`${item.itemId} | item_note | note=${item.note.trim()}`);
      notes.push(`整图备注：${item.note.trim()}`);
    }

    for (const [role, box] of Object.entries(item.boxes ?? {})) {
      if (!box.bad && !(box.note && box.note.trim())) {
        continue;
      }
      let line = `${item.itemId} | ${role}`;
      if (box.note && box.note.trim()) {
        line += ` | note=${box.note.trim()}`;
        notes.push(`${friendlyRole(role)}：${box.note.trim()}`);
      } else {
        notes.push(friendlyRole(role));
      }
      structured.push(line);
    }

    if (notes.length) {
      human.push(`${item.itemId}: ${notes.join("; ")}`);
    }
  }

  return {
    structuredText: structured.join("\n"),
    humanText: human.join("\n"),
  };
}

function itemPayloadHasFeedback(feedback) {
  if (!feedback) {
    return false;
  }
  if (feedback.wholeImageBad || (feedback.note && feedback.note.trim())) {
    return true;
  }
  return Object.values(feedback.boxes ?? {}).some((box) => box.bad || (box.note && box.note.trim()));
}

function friendlyRole(role) {
  return {
    name_area: "左上角标签",
    code_area: "数字区域",
    code_area_left: "左数字区域",
    code_area_middle: "中数字区域",
    code_area_right: "右数字区域",
  }[role] ?? role;
}

function orientationLabel(value) {
  return value === "horizontal" ? "横版" : value === "vertical" ? "竖版" : value;
}

function splitLabel(value) {
  return value === "train" ? "训练集" : value === "val" ? "验证集" : value;
}

function syncMissingFeedback() {
  for (const item of state.items) {
    state.feedback[item.itemId] ??= { wholeImageBad: false, note: "", boxes: {} };
  }
}

function scrollCurrentItemIntoView() {
  const currentId = state.currentId ?? "";
  const safeId = window.CSS && typeof window.CSS.escape === "function" ? window.CSS.escape(currentId) : currentId.replaceAll('"', '\\"');
  const currentCard = el.itemList.querySelector(`[data-item-id="${safeId}"]`);
  currentCard?.scrollIntoView({ block: "nearest" });
}

function saveFeedback() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.feedback));
}

function loadFeedback() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function toWebPath(path) {
  return `/${String(path).replaceAll("\\", "/")}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
