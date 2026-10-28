from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
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


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from .smoke import run
        return run(sys.argv[2])

    # Enable GTK theme detection on Linux (must be set before QApplication)
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORMTHEME" not in os.environ:
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

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
