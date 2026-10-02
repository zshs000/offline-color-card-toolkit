from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


RETIRED_PACKAGES = {"ultralytics", "torch", "torchvision", "polars", "_polars_runtime_32"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the Windows desktop distribution before publishing.")
    parser.add_argument("--bundle", type=Path, default=Path("dist/线下色卡采集工具集"))
    parser.add_argument("--pyz", type=Path)
    parser.add_argument("--max-mib", type=float, default=400)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    executable = bundle / "线下色卡采集工具集.exe"
    if not executable.is_file():
        raise SystemExit(f"Missing application: {executable}")

    files = [path for path in bundle.rglob("*") if path.is_file()]
    size_mib = sum(path.stat().st_size for path in files) / 1024**2
    print(f"Bundle: {len(files)} files, {size_mib:.2f} MiB (limit {args.max_mib:g} MiB)", flush=True)
    if size_mib > args.max_mib:
        raise SystemExit("Bundle exceeds the size budget")
    for path in files:
        relative = path.relative_to(bundle)
        if path.suffix.lower() == ".pt" or RETIRED_PACKAGES.intersection(relative.parts):
            raise SystemExit(f"Retired inference asset in bundle: {relative}")

    if args.pyz is not None:
        from PyInstaller.archive.readers import ZlibArchiveReader

        archive = ZlibArchiveReader(str(args.pyz))
        forbidden = sorted(name for name in archive.toc if name.split(".")[0] in RETIRED_PACKAGES)
        if forbidden:
            raise SystemExit(f"Retired inference modules in PYZ: {forbidden}")

    for template in ("转平贴底纸模板.docx", "8144-不干胶贴模板.docx"):
        if not (bundle / "_internal/resources/templates" / template).is_file():
            raise SystemExit(f"Missing template: {template}")

    if args.smoke:
        if os.name != "nt":
            raise SystemExit("Windows executable smoke checks require Windows")
        for mode in ("template", "ocr"):
            subprocess.run(
                [str(executable)],
                cwd=bundle,
                env={**os.environ, "COLOR_CARD_TOOLKIT_SMOKE": mode},
                stdin=subprocess.DEVNULL,
                check=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            print(f"{mode} smoke check passed", flush=True)


if __name__ == "__main__":
    main()
