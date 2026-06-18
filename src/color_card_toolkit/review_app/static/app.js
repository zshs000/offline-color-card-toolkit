const state = {
  items: [],
  currentId: null,
  filters: {
    orientation: "all",
    search: "",
    completedOnly: false,
  },
  summary: {
    total: 0,
    completed: 0,
    pending: 0,
  },
  drawing: null,
  selectedRole: null,
  exportMessage: "",
};

const el = {
  itemList: document.getElementById("itemList"),
  summaryText: document.getElementById("summaryText"),
  searchInput: document.getElementById("searchInput"),
  orientationFilter: document.getElementById("orientationFilter"),
  completedOnly: document.getElementById("completedOnly"),
  currentMeta: document.getElementById("currentMeta"),
  currentTitle: document.getElementById("currentTitle"),
  currentOrientation: document.getElementById("currentOrientation"),
  currentCodeColumnsLabel: document.getElementById("currentCodeColumnsLabel"),
  currentCodeColumns: document.getElementById("currentCodeColumns"),
  prevItem: document.getElementById("prevItem"),
  nextItem: document.getElementById("nextItem"),
  stepHint: document.getElementById("stepHint"),
  roleTabs: document.getElementById("roleTabs"),
  imageFrame: document.getElementById("imageFrame"),
  sourceImage: document.getElementById("sourceImage"),
  boxLayer: document.getElementById("boxLayer"),
  draftBox: document.getElementById("draftBox"),
  redoRole: document.getElementById("redoRole"),
  deleteRole: document.getElementById("deleteRole"),
  clearCurrent: document.getElementById("clearCurrent"),
  boxList: document.getElementById("boxList"),
  exportYolo: document.getElementById("exportYolo"),
  exportText: document.getElementById("exportText"),
};

init();

async function init() {
  bindEvents();
  await reloadData();
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

  el.completedOnly.addEventListener("change", () => {
    state.filters.completedOnly = el.completedOnly.checked;
    renderList();
  });

  el.currentOrientation.addEventListener("change", async () => {
    const item = currentItem();
    if (!item) {
      return;
    }
    const nextOrientation = el.currentOrientation.value;
    if (nextOrientation === item.orientation) {
      return;
    }
    if (nextOrientation === "vertical" && !item.codeColumnCount) {
      item.codeColumnCount = 2;
    }
    const nextRoles = requiredRoles(nextOrientation, item.codeColumnCount);
    const keptBoxes = {};
    for (const role of nextRoles) {
      if (item.boxes[role]) {
        keptBoxes[role] = item.boxes[role];
      }
    }
    item.orientation = nextOrientation;
    item.boxes = keptBoxes;
    state.selectedRole = nextRoles.find((role) => !item.boxes[role]) ?? nextRoles[0];
    await saveCurrentItem();
    recalcSummary();
    render();
  });

  el.currentCodeColumns.addEventListener("change", async () => {
    const item = currentItem();
    if (!item || item.orientation !== "vertical") {
      return;
    }
    item.codeColumnCount = Number(el.currentCodeColumns.value) === 3 ? 3 : 2;
    const nextRoles = itemRoles(item);
    const keptBoxes = {};
    for (const role of nextRoles) {
      if (item.boxes[role]) {
        keptBoxes[role] = item.boxes[role];
      }
    }
    item.boxes = keptBoxes;
    state.selectedRole = nextMissingRole(item) ?? nextRoles[0];
    await saveCurrentItem();
    recalcSummary();
    render();
  });

  el.prevItem.addEventListener("click", () => moveBy(-1));
  el.nextItem.addEventListener("click", () => moveBy(1));

  el.redoRole.addEventListener("click", () => {
    const item = currentItem();
    if (!item || !state.selectedRole) {
      return;
    }
    delete item.boxes[state.selectedRole];
    saveCurrentItem().then(() => {
      render();
    });
  });

  el.deleteRole.addEventListener("click", () => {
    const item = currentItem();
    if (!item || !state.selectedRole || !item.boxes[state.selectedRole]) {
      return;
    }
    delete item.boxes[state.selectedRole];
    saveCurrentItem().then(() => {
      recalcSummary();
      render();
    });
  });

  el.clearCurrent.addEventListener("click", async () => {
    const item = currentItem();
    if (!item) {
      return;
    }
    item.boxes = {};
    state.selectedRole = itemRoles(item)[0];
    await saveCurrentItem();
    recalcSummary();
    render();
  });

  el.exportYolo.addEventListener("click", async () => {
    el.exportYolo.disabled = true;
    try {
      const response = await fetch("/api/export-yolo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json();
      state.exportMessage = buildExportMessage(payload);
      el.exportText.value = state.exportMessage;
    } finally {
      el.exportYolo.disabled = false;
    }
  });

  el.imageFrame.addEventListener("pointerdown", startDrawing);
  window.addEventListener("pointermove", updateDrawing);
  window.addEventListener("pointerup", finishDrawing);
  window.addEventListener("resize", renderBoxes);
}

async function reloadData() {
  const response = await fetch("/api/annotation-data");
  const payload = await response.json();
  state.items = payload.items.map(normalizeItem);
  state.summary = payload.summary;
  state.currentId = pickCurrentId();
  const item = currentItem();
  state.selectedRole = item ? nextMissingRole(item) ?? itemRoles(item)[0] : null;
  state.exportMessage = [
    `原始图片目录：${payload.rawRoot}`,
    `标注文件：${payload.annotationFile}`,
    "",
    "导出时会生成两个训练目录：",
    "1. horizontal：类别为 name_area、code_area",
    "2. vertical：类别为 name_area、code_area；左/中/右数字都会导出成 code_area",
    "",
    "点击“导出 YOLO”后，会自动写出 images/train、images/val、labels/train、labels/val、data.yaml、manifest.csv。",
  ].join("\n");
  render();
}

function normalizeItem(item) {
  const boxes = {};
  for (const box of item.boxes ?? []) {
    boxes[box.role] = {
      centerX: Number(box.centerX),
      centerY: Number(box.centerY),
      width: Number(box.width),
      height: Number(box.height),
    };
  }
  return {
    itemId: item.itemId,
    fileName: item.fileName,
    sourceImage: item.sourceImage,
    defaultOrientation: item.defaultOrientation,
    orientation: item.orientation,
    codeColumnCount: Number(item.codeColumnCount) === 3 || boxes.code_area_middle ? 3 : 2,
    width: Number(item.width),
    height: Number(item.height),
    boxes,
  };
}

function render() {
  renderSummary();
  renderList();
  renderDetail();
  el.exportText.value = state.exportMessage;
}

function renderSummary() {
  el.summaryText.textContent = `总数 ${state.summary.total}，已完成 ${state.summary.completed}，未完成 ${state.summary.pending}`;
}

function renderList() {
  const items = filteredItems();
  el.itemList.innerHTML = "";

  for (const item of items) {
    const complete = isComplete(item);
    const roles = itemRoles(item);
    const boxCount = roles.filter((role) => item.boxes[role]).length;
    const card = document.createElement("button");
    card.type = "button";
    card.className = `item-card ${item.itemId === state.currentId ? "active" : ""} ${complete ? "done" : ""}`;
    card.dataset.itemId = item.itemId;
    card.innerHTML = `
      <div class="row">
        <div class="id">${escapeHtml(item.fileName)}</div>
        <span class="chip ${complete ? "done" : "pending"}">${complete ? "已完成" : "未完成"}</span>
      </div>
      <div class="meta">${orientationLabel(item.orientation)}${item.orientation === "vertical" ? ` ${item.codeColumnCount}列数字` : ""} | ${boxCount}/${roles.length} 个框</div>
    `;
    card.addEventListener("click", () => {
      state.currentId = item.itemId;
      state.selectedRole = nextMissingRole(item) ?? itemRoles(item)[0];
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
    el.sourceImage.removeAttribute("src");
    el.roleTabs.innerHTML = "";
    el.boxList.innerHTML = "";
    el.stepHint.textContent = "";
    return;
  }

  el.currentMeta.textContent = `${orientationLabel(item.defaultOrientation)} 原始目录 | ${item.width}x${item.height}`;
  el.currentTitle.textContent = item.fileName;
  el.currentOrientation.value = item.orientation;
  el.currentCodeColumns.value = String(item.codeColumnCount);
  el.currentCodeColumnsLabel.classList.toggle("hidden", item.orientation !== "vertical");
  el.sourceImage.src = toWebPath(item.sourceImage);
  el.sourceImage.alt = item.fileName;
  const roles = itemRoles(item);
  state.selectedRole = state.selectedRole && roles.includes(state.selectedRole)
    ? state.selectedRole
    : (nextMissingRole(item) ?? roles[0]);
  el.stepHint.textContent = buildStepHint(item);
  renderRoleTabs(item);
  renderBoxes();
  renderBoxList(item);
  el.prevItem.disabled = filteredItems().length <= 1;
  el.nextItem.disabled = filteredItems().length <= 1;
  el.deleteRole.disabled = !(state.selectedRole && item.boxes[state.selectedRole]);
}

function renderRoleTabs(item) {
  el.roleTabs.innerHTML = "";
  for (const role of itemRoles(item)) {
    const button = document.createElement("button");
    button.type = "button";
    const hasBox = Boolean(item.boxes[role]);
    button.className = `role-tab ${role === state.selectedRole ? "active" : ""} ${hasBox ? "done" : ""}`;
    button.textContent = roleLabel(role);
    button.addEventListener("click", () => {
      state.selectedRole = role;
      render();
    });
    el.roleTabs.appendChild(button);
  }
}

function renderBoxes() {
  const item = currentItem();
  el.boxLayer.innerHTML = "";
  if (!item) {
    return;
  }
  const rect = getDisplayedImageRect(item);
  el.boxLayer.style.left = `${rect.left}px`;
  el.boxLayer.style.top = `${rect.top}px`;
  el.boxLayer.style.width = `${rect.width}px`;
  el.boxLayer.style.height = `${rect.height}px`;

  for (const role of itemRoles(item)) {
    const box = item.boxes[role];
    if (!box) {
      continue;
    }
    const node = document.createElement("div");
    node.className = `box-overlay role-${role} ${state.selectedRole === role ? "selected" : ""}`;
    node.style.left = `${(box.centerX - box.width / 2) * rect.width}px`;
    node.style.top = `${(box.centerY - box.height / 2) * rect.height}px`;
    node.style.width = `${box.width * rect.width}px`;
    node.style.height = `${box.height * rect.height}px`;
    node.textContent = roleLabel(role);
    el.boxLayer.appendChild(node);
  }
}

function renderBoxList(item) {
  el.boxList.innerHTML = "";
  for (const role of itemRoles(item)) {
    const row = document.createElement("div");
    row.className = `box-row ${state.selectedRole === role ? "active" : ""}`;
    const box = item.boxes[role];
    row.innerHTML = `
      <div class="head">
        <div class="name">${escapeHtml(roleLabel(role))}</div>
        <span class="chip ${box ? "done" : "pending"}">${box ? "已标" : "待标"}</span>
      </div>
      <div class="detail">${box ? formatBox(box) : "在图片上拖一个框"}</div>
    `;
    row.addEventListener("click", () => {
      state.selectedRole = role;
      render();
    });
    el.boxList.appendChild(row);
  }
}

function startDrawing(event) {
  const item = currentItem();
  if (!item || !state.selectedRole) {
    return;
  }
  const point = eventToNormalizedPoint(event, item);
  if (!point) {
    return;
  }
  state.drawing = {
    pointerId: event.pointerId,
    startX: point.x,
    startY: point.y,
    currentX: point.x,
    currentY: point.y,
  };
  el.imageFrame.setPointerCapture?.(event.pointerId);
  updateDraftBox();
}

function updateDrawing(event) {
  const item = currentItem();
  if (!state.drawing || !item) {
    return;
  }
  const point = eventToNormalizedPoint(event, item);
  if (!point) {
    return;
  }
  state.drawing.currentX = point.x;
  state.drawing.currentY = point.y;
  updateDraftBox();
}

async function finishDrawing(event) {
  const item = currentItem();
  if (!state.drawing || !item || event.pointerId !== state.drawing.pointerId) {
    return;
  }
  const { startX, startY, currentX, currentY } = state.drawing;
  state.drawing = null;
  el.draftBox.classList.add("hidden");

  const width = Math.abs(currentX - startX);
  const height = Math.abs(currentY - startY);
  if (width < 0.01 || height < 0.01) {
    return;
  }

  const box = {
    centerX: clamp((startX + currentX) / 2),
    centerY: clamp((startY + currentY) / 2),
    width: clamp(width),
    height: clamp(height),
  };
  item.boxes[state.selectedRole] = box;
  await saveCurrentItem();
  recalcSummary();
  state.selectedRole = nextMissingRole(item) ?? state.selectedRole;
  render();
}

function updateDraftBox() {
  const item = currentItem();
  if (!state.drawing || !item) {
    el.draftBox.classList.add("hidden");
    return;
  }
  const rect = getDisplayedImageRect(item);
  const left = Math.min(state.drawing.startX, state.drawing.currentX) * rect.width + rect.left;
  const top = Math.min(state.drawing.startY, state.drawing.currentY) * rect.height + rect.top;
  const width = Math.abs(state.drawing.currentX - state.drawing.startX) * rect.width;
  const height = Math.abs(state.drawing.currentY - state.drawing.startY) * rect.height;
  el.draftBox.classList.remove("hidden");
  el.draftBox.style.left = `${left}px`;
  el.draftBox.style.top = `${top}px`;
  el.draftBox.style.width = `${width}px`;
  el.draftBox.style.height = `${height}px`;
}

async function saveCurrentItem() {
  const item = currentItem();
  if (!item) {
    return;
  }
  await fetch("/api/save-annotation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      itemId: item.itemId,
      orientation: item.orientation,
      codeColumnCount: item.codeColumnCount,
      boxes: item.boxes,
    }),
  });
}

function moveBy(offset) {
  const items = filteredItems();
  if (!items.length) {
    return;
  }
  const currentIndex = items.findIndex((item) => item.itemId === state.currentId);
  const nextIndex = currentIndex < 0
    ? 0
    : (currentIndex + offset + items.length) % items.length;
  const nextItem = items[nextIndex];
  state.currentId = nextItem.itemId;
  state.selectedRole = nextMissingRole(nextItem) ?? itemRoles(nextItem)[0];
  render();
  scrollCurrentIntoView();
}

function filteredItems() {
  return state.items.filter((item) => {
    if (state.filters.orientation !== "all" && item.orientation !== state.filters.orientation) {
      return false;
    }
    if (state.filters.search && !item.fileName.toLowerCase().includes(state.filters.search)) {
      return false;
    }
    if (state.filters.completedOnly && !isComplete(item)) {
      return false;
    }
    return true;
  });
}

function currentItem() {
  return state.items.find((item) => item.itemId === state.currentId) ?? null;
}

function pickCurrentId() {
  if (state.currentId && state.items.some((item) => item.itemId === state.currentId)) {
    return state.currentId;
  }
  const firstPending = state.items.find((item) => !isComplete(item));
  return firstPending?.itemId ?? state.items[0]?.itemId ?? null;
}

function nextMissingRole(item) {
  return itemRoles(item).find((role) => !item.boxes[role]) ?? null;
}

function isComplete(item) {
  return itemRoles(item).every((role) => item.boxes[role]);
}

function itemRoles(item) {
  return requiredRoles(item.orientation, item.codeColumnCount);
}

function requiredRoles(orientation, codeColumnCount = 2) {
  if (orientation !== "vertical") {
    return ["name_area", "code_area"];
  }
  return Number(codeColumnCount) === 3
    ? ["name_area", "code_area_left", "code_area_middle", "code_area_right"]
    : ["name_area", "code_area_left", "code_area_right"];
}

function roleLabel(role) {
  return {
    name_area: "左上标签",
    code_area: "数字区域",
    code_area_left: "左数字",
    code_area_middle: "中数字",
    code_area_right: "右数字",
  }[role] ?? role;
}

function orientationLabel(orientation) {
  return orientation === "vertical" ? "竖版" : "横版";
}

function buildStepHint(item) {
  if (isComplete(item)) {
    return "这张已经标完了，可以直接下一张，也可以点上面的步骤重画。";
  }
  return `请先标：${roleLabel(state.selectedRole)}。在图片上按住鼠标拖出一个框即可。`;
}

function formatBox(box) {
  return `中心(${box.centerX.toFixed(3)}, ${box.centerY.toFixed(3)}) 宽高(${box.width.toFixed(3)}, ${box.height.toFixed(3)})`;
}

function recalcSummary() {
  state.summary.total = state.items.length;
  state.summary.completed = state.items.filter(isComplete).length;
  state.summary.pending = state.summary.total - state.summary.completed;
}

function buildExportMessage(payload) {
  return [
    `导出完成：${payload.exportRoot}`,
    `标注文件：${payload.annotationFile}`,
    "",
    `总图片 ${payload.total}，已完成 ${payload.completed}`,
    `横版 train=${payload.summary.horizontal.train} val=${payload.summary.horizontal.val}`,
    `竖版 train=${payload.summary.vertical.train} val=${payload.summary.vertical.val}`,
    "",
    "目录内容：",
    "1. horizontal/images/train val",
    "2. horizontal/labels/train val",
    "3. vertical/images/train val",
    "4. vertical/labels/train val",
    "5. 每个方向各自的 data.yaml 和 manifest.csv",
    "6. vertical 的左/中/右数字框都会导出为同一个 code_area 类别",
  ].join("\n");
}

function eventToNormalizedPoint(event, item) {
  const frameRect = el.imageFrame.getBoundingClientRect();
  const imageRect = getDisplayedImageRect(item);
  const x = event.clientX - frameRect.left - imageRect.left;
  const y = event.clientY - frameRect.top - imageRect.top;
  if (x < 0 || y < 0 || x > imageRect.width || y > imageRect.height) {
    return null;
  }
  return {
    x: clamp(x / imageRect.width),
    y: clamp(y / imageRect.height),
  };
}

function getDisplayedImageRect(item) {
  const frameRect = el.imageFrame.getBoundingClientRect();
  const frameWidth = frameRect.width;
  const frameHeight = frameRect.height;
  const imageAspect = item.width / item.height;
  const frameAspect = frameWidth / frameHeight;
  let width = frameWidth;
  let height = frameHeight;
  let left = 0;
  let top = 0;

  if (frameAspect > imageAspect) {
    height = frameHeight;
    width = height * imageAspect;
    left = (frameWidth - width) / 2;
  } else {
    width = frameWidth;
    height = width / imageAspect;
    top = (frameHeight - height) / 2;
  }

  return { left, top, width, height };
}

function scrollCurrentIntoView() {
  const currentId = state.currentId ?? "";
  const safeId = window.CSS && typeof window.CSS.escape === "function"
    ? window.CSS.escape(currentId)
    : currentId.replaceAll('"', '\\"');
  const node = el.itemList.querySelector(`[data-item-id="${safeId}"]`);
  node?.scrollIntoView({ block: "nearest" });
}

function toWebPath(path) {
  return `/${String(path).replaceAll("\\", "/")}`;
}

function clamp(value) {
  return Math.min(1, Math.max(0, value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
