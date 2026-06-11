# Image Batch Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move image OCR/processing workflows off the UI thread with a shared batch worker.

**Architecture:** Add a small PySide `QThread` worker that processes items sequentially, emits progress and result signals, and continues after per-item failures. Wire the three image workflows to it: stack-to-flat OCR, scan rename, and main image crop. Each page remains responsible for its own UI and single-image processing behavior.

**Tech Stack:** Python, PySide6, pytest.

---

### Task 1: Shared Batch Worker

**Files:**
- Create: `src/color_card_toolkit/ui/batch_worker.py`
- Test: `tests/test_batch_worker.py`

- [x] Implement sequential processing with `progress`, `item_failed`, `finished`, and `failed` signals.
- [x] Return a controller object that keeps the worker and thread alive until completion.
- [x] Unit test direct worker execution for progress, per-item failures, and result collection.

### Task 2: Stack-To-Flat Recognition

**Files:**
- Modify: `src/color_card_toolkit/ui/stack_to_flat_page.py`
- Test: `tests/test_stack_to_flat_page.py`

- [x] Create RapidOCR inside the background task.
- [x] Update progress text while each image is processed.
- [x] Populate table on completion and keep the existing manual fallback behavior for failed images.

### Task 3: Rename/Crop Pages

**Files:**
- Modify: `src/color_card_toolkit/ui/scan_rename_page.py`
- Modify: `src/color_card_toolkit/ui/main_image_crop_page.py`
- Test: `tests/test_image_workflow_pages.py`

- [x] Run per-image rename/crop through the shared worker.
- [x] Disable confirm buttons while processing and re-enable them on completion.
- [x] Show completion with successful and failed counts.

### Task 4: Verification

- [x] Run `pytest`.
- [x] Run `git diff --check`.
