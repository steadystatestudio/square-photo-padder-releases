"""Record the exact source and dependency versions of a testing package."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_info() -> dict:
    name = "Square-Photo-Padder" if sys.platform == "win32" else "square-photo-padder"
    return json.loads((ROOT / "dist" / name / "BUILD-INFO.json").read_text(encoding="utf-8"))


def write_manifest(packages: list[Path]) -> None:
    info = build_info()
    info["packages"] = []
    for package in packages:
        with package.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        info["packages"].append({
            "filename": package.name,
            "sha256": digest,
        })
    dist = ROOT / "dist"
    (dist / "BUILD-INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    (dist / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['filename']}\n" for item in info["packages"]), encoding="utf-8"
    )

