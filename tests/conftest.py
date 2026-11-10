from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _answer_replace_confirmation(monkeypatch):
    """A modal confirmation would block an unattended run; tests of the prompt override this."""
    gui = sys.modules.get("photocropper.gui")
    if gui is not None:
        monkeypatch.setattr(gui.MainWindow, "_confirm_replace_originals", lambda self, count: True)
