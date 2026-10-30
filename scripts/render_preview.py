"""Render the Studio layout with synthetic photos and isolated preferences."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from photocropper.gui import MainWindow
from photocropper.themes import apply_theme


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/screenshots").resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visual-", dir=output) as directory:
        root = Path(directory)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / "settings"))
        app = QApplication.instance() or QApplication([])
        app.setOrganizationName("Studio visual checks")
        app.setApplicationName("Square Photo Padder")
        app.setStyle("Fusion")
        photo = root / "sample-notebook.png"
        image = Image.new("RGB", (500, 700), "#e8dfd1")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((90, 70, 420, 625), 20, fill="#456b70")
        draw.rectangle((105, 70, 122, 625), fill="#294a50")
        draw.rounded_rectangle((160, 175, 365, 280), 5, fill="#f7f1e5")
        draw.text((190, 215), "FIELD NOTES", fill="#294a50", font_size=22)
        image.save(photo)
        window = MainWindow()
        window._open_paths([photo])
        window._set_background_color((255, 255, 255))
        window._stop_load_animation()
        window.progress_bar.set_progress(0, 1, "1 photo ready")
        window.show()
        for theme in ("dark", "light"):
            os.environ["SPP_THEME"] = theme
            apply_theme(app)
            for name, size in (("full", (1000, 900)), ("compact", (800, 750))):
                window.resize(*size)
                app.processEvents()
                window._refresh_preview()
                app.processEvents()
                assert window.grab().save(str(output / f"{theme}-{name}.png"))
        window.close()


if __name__ == "__main__":
    main()
