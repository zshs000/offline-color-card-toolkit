# SPU Label Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the fixed-template “SPU名称生成不干胶模板” workflow.

**Architecture:** Add a core module that reads the first sheet of an `.xlsx` file from a user-selected row/column downward in one column, then writes values into an embedded 24x6 Word table template with page duplication. Add a PySide page matching the provided layout and route the existing homepage entry to it.

**Tech Stack:** Python, PySide6, openpyxl, python-docx, pytest.

---

### Task 1: Core Conversion

**Files:**
- Create: `src/color_card_toolkit/core/spu_label_generator.py`
- Modify: `src/color_card_toolkit/core/resources.py`
- Modify: `pyproject.toml`
- Test: `tests/test_spu_label_generator.py`

- [ ] Read first worksheet values from the selected row/column downward until the first blank.
- [ ] Write values into the first 24x6 table of the fixed Word template.
- [ ] Duplicate only the first table for additional pages and ignore trailing blank pages/paragraphs.

### Task 2: UI And Routing

**Files:**
- Create: `src/color_card_toolkit/ui/spu_label_page.py`
- Modify: `src/color_card_toolkit/ui/main_window.py`
- Test: `tests/test_spu_label_page.py`

- [ ] Build the page with Excel picker, row/column inputs, fixed template display, output name, output folder, and confirm button.
- [ ] Route homepage `SPU名称生成不干胶模板` to the new page.

### Task 3: Packaging And Docs

**Files:**
- Modify: `packaging/pyinstaller.spec`
- Modify: `README.md`
- Modify: `docs/requirements/feature-03-spu-label-template.md`
- Modify: `docs/requirements/README.md`

- [ ] Package all Word templates in `resources/templates`.
- [ ] Document the fixed-template, first-sheet, one-column read behavior.
