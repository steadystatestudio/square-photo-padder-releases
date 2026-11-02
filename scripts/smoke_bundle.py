"""Run the actual frozen application with isolated settings and inspect its results."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    executable = Path(sys.argv[1]).resolve()
    environment = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("PADDER_SMOKE_PLATFORM", "offscreen"))
    with tempfile.TemporaryDirectory(prefix="padder-package-") as directory:
        root = Path(directory) / "run"
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        completed = subprocess.run([str(executable), "--smoke-test", str(root)], cwd=directory, env=environment,
                                   timeout=60, **options)
        if completed.returncode != 0:
            error = root / "error.txt"
            raise RuntimeError(error.read_text(encoding="utf-8") if error.exists()
                               else f"Packaged GUI stopped with exit code {completed.returncode}")
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        assert result["success"] and (root / "ui.png").stat().st_size > 1000
        assert (root / "ui-ready.png").stat().st_size > 1000
        before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        refused = subprocess.run([str(executable), "--qa-ui", str(root)], cwd=directory, env=environment,
                                 timeout=15, **options)
        assert refused.returncode == 2, "Existing QA UI destination must be refused before opening a window"
        assert before == {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        result["checks"].append("QA UI refuses existing directories without changes")
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if len(sys.argv) > 2:
            import shutil
            target = Path(sys.argv[2])
            target.mkdir(parents=True, exist_ok=True)
            for name in ("ui.png", "ui-ready.png", "result.json"):
                shutil.copy2(root / name, target / name)
        print("Packaged GUI, JPEG processing, source integrity and collisions passed.")


if __name__ == "__main__":
    main()

