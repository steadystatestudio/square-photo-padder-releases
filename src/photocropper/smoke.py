"""Private packaged-app diagnostics, using isolated files and settings."""
from __future__ import annotations

import json
from pathlib import Path


def run(directory: str) -> int:
    from PIL import Image, ImageCms
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from .constants import APP_NAME, APP_ORGANIZATION
    from .gui import MainWindow
    from .processor import ProcessingOptions, process_image
    from .themes import apply_theme

    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(root / "settings"))
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setStyle("Fusion")
    apply_theme(app)
    source = root / "sample.png"
    Image.new("RGB", (60, 40), "red").save(source)
    before = source.read_bytes()
    window = MainWindow()
    window.show()
    window._open_paths([source])
    batch = window.process_paths([source])
    assert batch.success_count == 1 and batch.failure_count == 0
    result = batch.results[0]
    with Image.open(result.destination_path) as output:
        assert output.size == (60, 60) and output.format == "JPEG"
    assert source.read_bytes() == before
    assert "1 succeeded" in window.status_label.text()
    app.processEvents()
    assert window.grab().save(str(root / "ui.png"))
    window.close()
    neighbor = root / "sample.jpg"
    neighbor.write_bytes(b"keep existing neighbor")
    collision = process_image(source, ProcessingOptions(overwrite=True))
    assert collision.success and neighbor.read_bytes() == b"keep existing neighbor"
    jpeg = root / "original.jpg"
    Image.new("RGB", (60, 40), "blue").save(jpeg)
    overwrite = process_image(jpeg, ProcessingOptions(overwrite=True))
    assert overwrite.success and overwrite.destination_path == jpeg
    with Image.open(jpeg) as output:
        assert output.size == (60, 60)
    transparent = root / "transparent.png"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.new("RGBA", (30, 20), (255, 0, 0, 128)).save(transparent, icc_profile=profile)
    alpha_result = process_image(transparent, ProcessingOptions(background_color=(0, 0, 255)))
    assert alpha_result.success
    with Image.open(alpha_result.destination_path) as output:
        actual = output.getpixel((15, 15))
        assert all(abs(a-b) <= 3 for a, b in zip(actual, (128, 0, 127)))
        assert not output.getexif()
    oriented = root / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "synthetic private metadata"
    Image.new("RGB", (60, 20), "red").save(oriented, exif=exif)
    oriented_result = process_image(oriented)
    assert oriented_result.success
    with Image.open(oriented_result.destination_path) as output:
        assert output.getpixel((30, 2))[0] > 240
        assert output.getpixel((2, 30))[0] < 10
        assert not output.getexif()
    (root / "result.json").write_text(json.dumps({
        "success": True, "checks": ["packaged GUI", "square JPEG output", "source preserved",
                                   "neighbor collision preserved", "overwrite JPEG", "ICC and alpha compositing",
                                   "EXIF orientation", "export metadata removed"]
    }, indent=2), encoding="utf-8")
    return 0

