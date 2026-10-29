"""将已构建的Windows程序打包为中文NSIS安装向导。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from color_card_toolkit import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, default=ROOT / "dist/线下色卡采集工具集")
    parser.add_argument("--compiler", default=os.environ.get("COLOR_CARD_MAKENSIS") or shutil.which("makensis"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "installers")
    parser.add_argument("--validation", action="store_true", help="生成不压缩的隔离验证包，使用独立注册表和快捷方式名称")
    args = parser.parse_args()
    if not args.compiler or not Path(args.compiler).is_file():
        raise SystemExit("请安装NSIS 3，并通过 --compiler 或 COLOR_CARD_MAKENSIS 指定 makensis.exe")
    payload = args.payload.resolve()
    for name in ("线下色卡采集工具集.exe", "_internal/pyproject.toml", "_internal/PySide6/plugins/platforms/qwindows.dll"):
        if not (payload / name).is_file():
            raise SystemExit(f"程序目录缺少 {name}，请先运行 build_windows.py")
    project = (payload / "_internal/pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE).group(1)
    if version != __version__:
        raise SystemExit("程序目录版本与项目版本不一致，请重新构建")
    files = sorted(path for path in payload.rglob("*") if path.is_file())
    directories = sorted((path.relative_to(payload) for path in payload.rglob("*") if path.is_dir()),
                         key=lambda path: (-len(path.parts), str(path)))
    # 清单只包含本次发布的程序文件。升级和卸载按清单删除，不清空安装目录。
    entries = ["F|" + str(path.relative_to(payload)) for path in files]
    entries += ["D|" + str(path) for path in directories]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-Validation" if args.validation else ""
    output = (args.output_dir / f"OfflineColorCardToolkit-Setup-{version}-x64{suffix}.exe").resolve()
    total_bytes = sum(path.stat().st_size for path in files)
    with tempfile.TemporaryDirectory(prefix="color-card-installer-") as temporary:
        manifest = Path(temporary) / "installed-files.txt"
        manifest.write_bytes(("\r\n".join(entries) + "\r\n").encode("utf-16-le"))
        command = [str(args.compiler), "/INPUTCHARSET", "UTF8", "/V2",
                   f"/DPAYLOAD={payload}", f"/DOUTPUT={output}",
                   f"/DAPP_VERSION={version}", f"/DPAYLOAD_KIB={total_bytes // 1024}",
                   f"/DFILE_MANIFEST={manifest}"]
        if args.validation:
            command.append("/DVALIDATION")
        subprocess.run([*command, str(ROOT / "packaging/installer.nsi")], check=True)
    summary = {"installer": str(output), "version": version, "payload_files": len(files),
               "unpacked_mib": round(total_bytes / 2**20, 2),
               "installer_mib": round(output.stat().st_size / 2**20, 2),
               "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
