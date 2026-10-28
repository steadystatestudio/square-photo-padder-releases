"""Retain license notices, library sources and safe build provenance.
Adapted from Steady State Studio Contact Sheet Maker under the MIT LICENSE.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import fetch_appimagetool as appimage_inputs
from fetch_release_sources import source_index

NAME = "Square-Photo-Padder"
LICENSE_PACKAGES = (
    "Pillow", "PySide6", "PySide6_Essentials", "PySide6_Addons",
    "shiboken6", "PyInstaller", "altgraph", "packaging", "setuptools",
)

def verify_qt_subset(bundle: Path) -> None:
    """Fail closed if optional, unreviewed Qt components return to the package."""
    excluded = ("qt6pdf", "qt6virtualkeyboard", "qt6qml", "qt6quick", "qt6webengine", "qt6network")
    for path in (bundle / "_internal").rglob("*"):
        name = path.name.lower().removeprefix("lib")
        if path.is_file() and (name.startswith(excluded) or name == "opengl32sw.dll"
                               or name.startswith(("qpdf.", "qtvirtualkeyboardplugin.", "qtuiotouchplugin.", "qvnc."))):
            raise RuntimeError(f"Unreviewed optional Qt component in package: {path.name}")


def source_hashes(root: Path) -> dict[str, str]:
    """Record build inputs, without local photos, caches, absolute paths or secrets."""
    paths = [root / name for name in (
        "pyproject.toml", "packaging/build-constraints.txt", "LICENSE", "THIRD_PARTY_NOTICES.md",
    )]
    for directory in ("src", "scripts", "packaging", ".github/workflows"):
        paths.extend((root / directory).rglob("*"))
    hashes = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(root)
        if (not path.is_file() or path.is_symlink() or "__pycache__" in relative.parts
                or any(part.endswith(".egg-info") for part in relative.parts)
                or path.suffix in {".pyc", ".pyo"}):
            continue
        hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def source_revision(root: Path) -> str:
    revision = os.environ.get("BUILD_SOURCE_COMMIT", "")
    if not revision:
        try:
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "uncommitted-local-build"
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise RuntimeError("BUILD_SOURCE_COMMIT must be a complete Git commit SHA")
    return revision.lower()


def write_build_info(root: Path, bundle: Path, target_platform: str) -> None:
    from PySide6.QtCore import qVersion
    dependencies = {}
    for name in LICENSE_PACKAGES:
        dependencies[name] = metadata.version(name)
    for name in ("pefile", "pywin32-ctypes"):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    info = {
        "application": NAME,
        "repository": "steadystatestudio/square-photo-padder-releases",
        "source_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip(),
        "source_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True,
        ).strip()),
        "application_version": __import__("tomllib").loads((root / "pyproject.toml").read_text())["project"]["version"],
        "source_commit": source_revision(root),
        "python": platform.python_version(),
        "platform": target_platform,
        "os": platform.system() + " " + platform.release(),
        "machine": platform.machine(),
        "qt_runtime": qVersion(),
        "dependencies": dependencies,
        "source_sha256": source_hashes(root),
        "appimage_inputs": {
            "appimagetool": {"url": appimage_inputs.URL, "sha256": appimage_inputs.SHA256},
            "runtime": {"url": appimage_inputs.RUNTIME_URL, "sha256": appimage_inputs.RUNTIME_SHA256},
        } if target_platform == "linux" else None,
    }
    (bundle / "BUILD-INFO.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_notices(root: Path, bundle: Path, target_platform: str) -> None:
    from PySide6.QtCore import qVersion
    index = source_index(root)
    if qVersion() != index["qt_version"]:
        raise RuntimeError("Qt runtime differs from retained source pins")
    (bundle / "SOURCE-INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(root / "packaging/LIBRARY-REPLACEMENT.txt", bundle / "LIBRARY-REPLACEMENT.txt")
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "packaging/build-constraints.txt"):
        shutil.copy2(root / name, bundle / Path(name).name)
    if (root / "docs/VALIDATION.md").is_file():
        shutil.copy2(root / "docs/VALIDATION.md", bundle / "VALIDATION.md")
    licenses = bundle / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copytree(root / "packaging/licenses", licenses, dirs_exist_ok=True)
    readme = ("packaging/windows/README-WINDOWS.txt" if target_platform == "win32"
              else "packaging/linux/README-LINUX.txt")
    shutil.copy2(root / readme, bundle / Path(readme).name)
    if target_platform == "linux":
        shutil.copy2(root / "packaging/linux/APPIMAGE_RUNTIME_LICENSE.txt", licenses / "APPIMAGE_RUNTIME_LICENSE.txt")
        shutil.copy2(root / "build/LINUX-SYSTEM-DEPENDENCIES.json", bundle / "LINUX-SYSTEM-DEPENDENCIES.json")
    # Full Python license, not an unrelated OS interpreter's license.
    python_licenses = (Path(sys.base_prefix) / "LICENSE.txt", Path(sysconfig.get_path("stdlib")) / "LICENSE.txt")
    for source in python_licenses:
        if source.is_file():
            shutil.copy2(source, licenses / "Python-LICENSE.txt")
            break
    else:
        raise RuntimeError("Python license text is missing from the build interpreter")
    for name in LICENSE_PACKAGES:
        distribution = metadata.distribution(name)
        for entry in distribution.files or []:
            relative = Path(entry)
            if relative.suffix in {".py", ".pyc", ".pyo"} or "__pycache__" in relative.parts:
                continue
            if not any(word in str(relative).upper() for word in ("LICENSE", "COPYING", "NOTICE", "COPYRIGHT")):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                # Preserve relative license paths to avoid silently overwriting same-named notices.
                safe_parts = [part for part in relative.parts if part not in ("..", ".") and part != relative.anchor]
                target = licenses / name / Path(*safe_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    license_index = {}
    for path in sorted(licenses.rglob("*")):
        if path.is_file() and not path.is_symlink():
            license_index[path.relative_to(bundle).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (bundle / "LICENSE-INDEX.json").write_text(json.dumps(license_index, indent=2) + "\n", encoding="utf-8")
    native_libraries = {}
    for path in sorted((bundle / "_internal").rglob("*")):
        if path.is_file() and (path.suffix.lower() in {".dll", ".pyd", ".dylib"} or ".so" in path.name):
            with path.open("rb") as stream:
                native_libraries[path.relative_to(bundle).as_posix()] = hashlib.file_digest(
                    stream, "sha256",
                ).hexdigest()
    (bundle / "NATIVE-LIBRARIES.json").write_text(json.dumps(native_libraries, indent=2) + "\n", encoding="utf-8")
    write_build_info(root, bundle, target_platform)
