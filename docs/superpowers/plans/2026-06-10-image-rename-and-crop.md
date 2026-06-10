# Image Rename And Crop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two homepage entries: one that copies scan images with OCR-derived names, and one that crops main images by centimeter size and saves them with OCR-derived names.

**Architecture:** Reuse the existing RapidOCR wrapper and add a focused core service for extracting the top-left name, producing unique filenames, copying originals, and lossless/high-quality cropping. Add two small PySide pages that collect output folder and input images, then call the service synchronously like the existing first feature.

**Tech Stack:** Python, PySide6, Pillow, RapidOCR, pytest.

---

### Task 1: Core Rename/Crop Service

**Files:**
- Create: `src/color_card_toolkit/core/image_rename.py`
- Test: `tests/test_image_rename.py`

- [ ] Write tests for top-left name extraction, duplicate output naming, original scan copy, and DPI-based crop sizing.
- [ ] Implement `extract_top_left_name`, `unique_output_path`, `rename_scan_images`, and `crop_main_images`.
- [ ] Run `.\.venv\Scripts\python -m pytest tests\test_image_rename.py`.

### Task 2: Two PySide Pages

**Files:**
- Create: `src/color_card_toolkit/ui/scan_rename_page.py`
- Create: `src/color_card_toolkit/ui/main_image_crop_page.py`
- Modify: `src/color_card_toolkit/ui/main_window.py`
- Test: `tests/test_image_workflow_pages.py`

- [ ] Write UI tests that verify default output folders and basic state clearing after successful processing.
- [ ] Add the scan rename page with output folder picker, image picker, and confirm action.
- [ ] Add the main image crop page with size selector, output folder picker, image picker, and confirm action.
- [ ] Update homepage entries to four buttons and route both new features.
- [ ] Run page tests with `QT_QPA_PLATFORM=offscreen`.

### Task 3: Docs And Regression

**Files:**
- Modify: `README.md`
- Modify: `docs/requirements/README.md`
- Modify: `docs/requirements/feature-02-main-image-crop-rename.md`

- [ ] Update documentation to describe both implemented image workflows.
- [ ] Run the full test suite.
