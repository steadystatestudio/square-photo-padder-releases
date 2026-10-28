"""Build unsigned native testing packages, with checksums and source provenance."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from build_manifest import write_manifest
from packaging_notices import copy_notices, verify_qt_subset

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.platform not in {"win32", "linux"}:
        raise SystemExit("Build on Windows or Linux.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("These testing packages require an x86-64 build host.")
    os.chdir(ROOT)
    build, dist = ROOT / "build", ROOT / "dist"
    build.mkdir(exist_ok=True)
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(build / "pyinstaller-cache")
    windows = sys.platform == "win32"
    name = "Square-Photo-Padder" if windows else "square-photo-padder"
    spec = "photocropper-windows.spec" if windows else "photocropper.spec"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec], check=True)
    bundle = dist / name
    verify_qt_subset(bundle)
    copy_notices(ROOT, bundle, sys.platform)
    if windows:
        archive = Path(shutil.make_archive(str(dist / "Square-Photo-Padder-windows"), "zip", dist, name))
        write_manifest([archive])
        return
    archive = Path(shutil.make_archive(str(dist / "Square-Photo-Padder-linux-x86_64"), "gztar", dist, name))
    appdir = build / "Square-Photo-Padder.AppDir"
    if appdir.exists():
        if not appdir.resolve().is_relative_to(build.resolve()):
            raise RuntimeError("AppDir escaped the build directory.")
        shutil.rmtree(appdir)
    shutil.copytree(bundle, appdir / "usr/lib/square-photo-padder")
    shutil.copy2(ROOT / "packaging/linux/square-photo-padder.png", appdir / "square-photo-padder.png")
    shutil.copy2(ROOT / "packaging/linux/square-photo-padder.desktop", appdir / "square-photo-padder.desktop")
    (appdir / "AppRun").write_text(
        '#!/bin/sh\nHERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'exec "$HERE/usr/lib/square-photo-padder/square-photo-padder" "$@"\n', encoding="utf-8")
    (appdir / "AppRun").chmod(0o755)
    subprocess.run([sys.executable, str(ROOT / "scripts/fetch_appimagetool.py")], check=True)
    output = dist / "Square-Photo-Padder-x86_64.AppImage"
    subprocess.run([str(build / "tools/appimagetool"), "--runtime-file", str(build / "tools/runtime-x86_64"),
                    str(appdir), str(output)], check=True,
                   env=dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1"))
    write_manifest([archive, output])


if __name__ == "__main__":
    main()
