# 叠贴转平贴模板生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first feature of “线下色卡采集工具集”: select color-card images, recognize names and color codes offline, confirm/edit results, then generate one Word file from the built-in flat-template document.

**Architecture:** Use a small PySide6 desktop app with focused service modules. The UI collects files and lets users confirm OCR results; pure Python services handle OCR normalization, grouping, validation, and Word generation so they can be tested without launching the UI.

**Tech Stack:** Python, PySide6, RapidOCR first, optional PaddleOCR fallback, python-docx, Pillow/OpenCV, pytest, PyInstaller.

---

## File Structure

- `pyproject.toml`: project metadata and dependencies.
- `README.md`: local development and run instructions.
- `src/color_card_toolkit/main.py`: app entry point.
- `src/color_card_toolkit/ui/main_window.py`: homepage with three feature entries; features 2 and 3 show “暂未开放”.
- `src/color_card_toolkit/ui/stack_to_flat_page.py`: feature 1 page for template display, output settings, image selection, OCR, confirmation, and generation.
- `src/color_card_toolkit/core/models.py`: shared dataclasses for OCR blocks, image recognition results, grouped color cards, and generation warnings.
- `src/color_card_toolkit/core/ocr_engine.py`: OCR engine interface plus RapidOCR adapter.
- `src/color_card_toolkit/core/color_code_parser.py`: filter OCR text blocks, detect horizontal/vertical color-code queues, sort color codes, and report suspected missing numbers.
- `src/color_card_toolkit/core/grouping.py`: parse group names, extract sequence numbers, merge image results, validate group continuity.
- `src/color_card_toolkit/core/word_generator.py`: copy the built-in `.docx` table template, fill headers and 24 color-code cells per page, save output.
- `src/color_card_toolkit/resources/templates/转平贴底纸模板.docx`: built-in Word template copied from `docs/转平贴底纸模板.docx`.
- `tests/`: focused tests for parser, grouping, and Word generation.

---

### Task 1: Create Python Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/color_card_toolkit/__init__.py`
- Create: `src/color_card_toolkit/main.py`
- Create: `src/color_card_toolkit/ui/main_window.py`
- Create: `src/color_card_toolkit/ui/stack_to_flat_page.py`
- Create: `src/color_card_toolkit/core/models.py`
- Create: `tests/`

- [ ] Create the Python package structure under `src/color_card_toolkit`.
- [ ] Add dependencies for PySide6, python-docx, Pillow/OpenCV, RapidOCR, and pytest.
- [ ] Add a minimal `main.py` that starts a PySide6 application.
- [ ] Add a simple main window titled “线下色卡采集工具集”.
- [ ] Run `python -m pytest` and confirm the empty test suite or initial smoke tests run without import errors.

### Task 2: Build the Desktop UI Shell

**Files:**
- Modify: `src/color_card_toolkit/ui/main_window.py`
- Modify: `src/color_card_toolkit/ui/stack_to_flat_page.py`

- [ ] Build the homepage with three large entries matching the prototype:
  - `叠贴转平贴模板生成`
  - `主图截图及名称更改`
  - `SPU名称生成不干胶模板`
- [ ] Wire only the first entry to the feature page.
- [ ] Make the second and third entries display “暂未开放”.
- [ ] Build the first feature page with:
  - built-in template display and open-view button
  - output Word name input
  - output folder picker
  - image picker for `.jpg/.jpeg/.png`
  - start recognition button
  - recognition result table
  - generate Word button

### Task 3: Add OCR Engine Boundary

**Files:**
- Create: `src/color_card_toolkit/core/ocr_engine.py`
- Modify: `src/color_card_toolkit/core/models.py`
- Test: `tests/test_ocr_engine_contract.py`

- [ ] Define an `OcrBlock` model containing text, confidence, and box coordinates.
- [ ] Define an `OcrEngine` interface with `recognize(image_path) -> list[OcrBlock]`.
- [ ] Implement `RapidOcrEngine` as the default offline OCR adapter.
- [ ] Add a fake OCR engine for tests so parser and grouping logic can be tested without OCR model files.
- [ ] Run OCR once on real sample images when samples are available, then tune only the parsing rules, not the UI.

### Task 4: Implement Color-Code Parsing Rules

**Files:**
- Create: `src/color_card_toolkit/core/color_code_parser.py`
- Test: `tests/test_color_code_parser.py`

- [ ] Filter out obvious non-color-code text such as `Width`, `Thickness`, `INSTOCK`, `现货版`, and long isolated model numbers like `2014`.
- [ ] Detect horizontal color-code rows by clustering OCR blocks with close y coordinates and enough short code-like texts.
- [ ] Sort horizontal codes from left to right.
- [ ] Detect vertical color-code columns by clustering OCR blocks with close x coordinates.
- [ ] Sort vertical codes as left column top-to-bottom, then right column top-to-bottom.
- [ ] Report suspected missing numeric codes without blocking generation.
- [ ] Cover examples in tests:
  - horizontal `01 02 03 04 05 06 08`
  - vertical `47-69` and `70-92`
  - interference text `2014` and `Width:52" Thickness:0.9mm`

### Task 5: Implement Grouping and Continuity Validation

**Files:**
- Create: `src/color_card_toolkit/core/grouping.py`
- Test: `tests/test_grouping.py`

- [ ] Parse names like `PU88(1)`, `PU88（2）`, `PU-6159`, and Chinese names with optional trailing sequence numbers.
- [ ] Treat names without trailing sequence numbers as single-image groups with sequence `1`.
- [ ] Group selected images by base name.
- [ ] Sort each group by sequence number.
- [ ] Reject the entire group if sequence numbers do not start at `1` or are not continuous.
- [ ] Merge color codes from valid groups in sequence order.
- [ ] Return skipped-group warnings such as `PU88（缺少第2张）`.

### Task 6: Generate Word from Built-In Template

**Files:**
- Copy: `docs/转平贴底纸模板.docx` to `src/color_card_toolkit/resources/templates/转平贴底纸模板.docx`
- Create: `src/color_card_toolkit/core/word_generator.py`
- Test: `tests/test_word_generator.py`

- [ ] Load the built-in Word template without modifying the original file.
- [ ] Copy the single template table for every required output page.
- [ ] Fill the first row header as `{base_name} ({page_number})`.
- [ ] Fill 24 color-code cells per page in 6-column by 4-row order.
- [ ] Leave the large blank cells untouched.
- [ ] Insert additional pages until all merged color codes are written.
- [ ] Save one output `.docx` containing all valid groups.

### Task 7: Connect UI to Services

**Files:**
- Modify: `src/color_card_toolkit/ui/stack_to_flat_page.py`
- Modify: `src/color_card_toolkit/core/models.py`

- [ ] On “开始识别”, run OCR for each selected image.
- [ ] Show image file name, raw group name, base group name, sequence number, color-code list, missing-code warning, and participation checkbox.
- [ ] Allow users to edit group name, sequence number, and color-code list before generation.
- [ ] On “生成 Word”, build corrected recognition results from the table.
- [ ] Run grouping validation and show skipped-group warnings.
- [ ] Generate the final Word file and show the output path.

### Task 8: Package and Verify First Feature

**Files:**
- Create: `packaging/pyinstaller.spec`
- Create or modify: `README.md`

- [ ] Add local run command documentation.
- [ ] Add PyInstaller packaging command for Windows.
- [ ] Include the built-in Word template in packaged resources.
- [ ] Verify the desktop app opens with title “线下色卡采集工具集”.
- [ ] Verify feature 2 and feature 3 are visible but not active.
- [ ] Verify feature 1 can generate a `.docx` using mocked or real OCR data.
- [ ] Record any OCR sample failures as rule-tuning notes rather than changing the confirmed business rules.

---

## Verification Checklist

- [ ] `python -m pytest` passes.
- [ ] App launches locally.
- [ ] Built-in template is readable from packaged resources.
- [ ] Horizontal color-code sample sorts correctly.
- [ ] Vertical color-code sample sorts correctly.
- [ ] `2014` and specification text do not enter the color-code list.
- [ ] Discontinuous groups are skipped entirely.
- [ ] One output Word file is generated for all valid groups.

