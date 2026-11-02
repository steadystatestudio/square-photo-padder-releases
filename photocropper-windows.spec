# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

ROOT = Path(SPECPATH)
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "scripts"))
from linux_dependencies import omit_system_libraries

datas = [
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "packaging" / "windows" / "README-WINDOWS.txt"), "."),
    (str(SRC / "photocropper" / "assets"), "photocropper/assets"),
]

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageOps",
    "PIL.ImageCms",
]

a = Analysis(
    ["src/photocropper/__main__.py"],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging/hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtNetwork",
              "PySide6.QtPdf", "PySide6.QtQml", "PySide6.QtQuick", "readline", "tkinter", "pytest"],
    noarchive=False,
)
if sys.platform == "linux":
    omit_system_libraries(a, ROOT / "build/LINUX-SYSTEM-DEPENDENCIES.json")
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Square-Photo-Padder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "windows" / "app.ico"),
    version=str(ROOT / "packaging" / "windows" / "version.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Square-Photo-Padder",
)
