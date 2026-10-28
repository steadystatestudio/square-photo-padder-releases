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
        root = Path(directory)
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        subprocess.run([str(executable), "--smoke-test", str(root)], cwd=root, env=environment,
                       timeout=60, check=True, **options)
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        assert result["success"] and (root / "ui.png").stat().st_size > 1000
        if len(sys.argv) > 2:
            import shutil
            target = Path(sys.argv[2])
            target.mkdir(parents=True, exist_ok=True)
            for name in ("ui.png", "result.json"):
                shutil.copy2(root / name, target / name)
        print("Packaged GUI, JPEG processing, source integrity and collisions passed.")


if __name__ == "__main__":
    main()

