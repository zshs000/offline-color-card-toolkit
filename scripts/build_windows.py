"""在独立的 Windows PATH 下打包，避免收集其他软件附带的同名 DLL。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows application builds require Windows")
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distpath", type=Path, default=root / "dist")
    parser.add_argument("--workpath", type=Path, default=root / "build")
    args = parser.parse_args()

    windows = Path(os.environ["SystemRoot"])
    env = os.environ.copy()
    # Qt依赖Windows的icuuc.dll。外部PDF工具等也有同名DLL，但导出函数不同。
    # 仅约束打包子进程的搜索路径；包内依赖仍由PyInstaller的hooks定位。
    env["PATH"] = os.pathsep.join(dict.fromkeys(str(path) for path in (
        Path(sys.executable).parent,
        Path(sys.base_prefix),
        Path(sys.base_prefix) / "DLLs",
        windows / "System32",
        windows,
    )))
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(args.distpath.resolve()),
         "--workpath", str(args.workpath.resolve()),
         str(root / "packaging/pyinstaller.spec")],
        cwd=root,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
