from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from photocropper.constants import APP_NAME, APP_ORGANIZATION
from photocropper.gui import MainWindow
from photocropper.themes import apply_theme, install_theme_watcher


def _load_app_icon() -> QIcon:
    try:
        from importlib.resources import files

        icon = QIcon(str(files("photocropper").joinpath("assets/icon-256.png")))
    except Exception:
        icon = QIcon()
    if icon.isNull():
        from photocropper.icons import make_fallback_app_icon

        icon = make_fallback_app_icon()
    return icon


def _isolate_qa_settings(directory: str) -> None:
    """Launch the ordinary UI with a fresh, process-local settings destination."""
    root = Path(directory).absolute()
    for part in (root, *root.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("QA settings destination must not use links")
    root.mkdir(parents=True, exist_ok=False)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / "settings"))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(root / "system-settings"))


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from .smoke import run
        return run(sys.argv[2])
    if "--qa-ui" in sys.argv[1:]:
        if len(sys.argv) != 3 or sys.argv[1] != "--qa-ui":
            return 2
        try:
            _isolate_qa_settings(sys.argv[2])
        except (OSError, ValueError):
            return 2

    if sys.platform == "win32":
        # Give the process its own taskbar identity so the window icon is
        # used instead of the Python interpreter's.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SteadyStateStudio.SquarePhotoPadder")
        except Exception:
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    from .system_fonts import capture_system_appearance
    capture_system_appearance(app)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setStyle("Fusion")

    try:
        apply_theme(app)
    except Exception:
        pass  # Fall back to default Fusion style
    install_theme_watcher(app)
    app.setWindowIcon(_load_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()
