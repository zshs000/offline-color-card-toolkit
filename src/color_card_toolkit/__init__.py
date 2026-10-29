"""Offline color-card collection toolkit."""

import re
import sys
from importlib.metadata import version
from pathlib import Path


def _project_version() -> str:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    project_file = root / "pyproject.toml"
    if project_file.is_file():
        project = project_file.read_text(encoding="utf-8").split("[project]", 1)[1].split("[", 1)[0]
        return re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE).group(1)
    return version("offline-color-card-toolkit")


__version__ = _project_version()

