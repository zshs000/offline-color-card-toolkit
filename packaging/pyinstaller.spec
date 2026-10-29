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
# The trained YOLO files remain in the source tree as research archives. They
# are no longer runtime assets and must not be copied into the desktop bundle.
model_datas = []

a = Analysis(
    [str(ROOT / "src/color_card_toolkit/main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=template_datas + model_datas + rapidocr_datas + [(str(ROOT / "pyproject.toml"), ".")],
    hiddenimports=["rapidocr_onnxruntime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["ultralytics", "torch", "torchvision", "polars", "_polars_runtime_32", "networkx",
              "PIL.AvifImagePlugin", "PIL._avif"],
    noarchive=False,
)

# 本工具只处理静态JPEG/PNG，界面使用Widgets。去掉自动收集的视频、
# PDF和虚拟键盘依赖；保留OCR、数值库、软件OpenGL回退及中文/英文资源。
unused_qt = {
    "qt6quick.dll", "qt6qml.dll", "qt6opengl.dll", "qt6qmlmodels.dll",
    "qt6virtualkeyboard.dll", "qt6qmlmeta.dll", "qt6qmlworkerscript.dll",
    "qtvirtualkeyboardplugin.dll", "qt6pdf.dll", "qpdf.dll",
}

def keep_runtime_file(entry):
    name = entry[0].replace("\\", "/").lower()
    basename = name.rsplit("/", 1)[-1]
    if basename in unused_qt or basename.startswith("opencv_videoio_ffmpeg"):
        return False
    if "/translations/" in name and name.endswith(".qm"):
        return name.endswith(("_zh_cn.qm", "_zh_tw.qm", "_en.qm", "_en_us.qm", "_en_gb.qm"))
    return True

a.binaries = [entry for entry in a.binaries if keep_runtime_file(entry)]
a.datas = [entry for entry in a.datas if keep_runtime_file(entry)]
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
