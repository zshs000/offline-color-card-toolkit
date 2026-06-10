# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

SPEC_LOCATION = Path(SPECPATH).resolve()
ROOT = SPEC_LOCATION.parent.parent if SPEC_LOCATION.suffix == ".spec" else SPEC_LOCATION.parent
rapidocr_datas = collect_data_files("rapidocr_onnxruntime")
template_datas = [
    (str(path), "resources/templates")
    for path in (ROOT / "src/color_card_toolkit/resources/templates").glob("*.docx")
]

a = Analysis(
    [str(ROOT / "src/color_card_toolkit/main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=template_datas + rapidocr_datas,
    hiddenimports=["rapidocr_onnxruntime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="线下色卡采集工具集",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="线下色卡采集工具集",
)
