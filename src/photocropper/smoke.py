"""Private packaged-app diagnostics, using isolated files and settings."""
from __future__ import annotations

import json
from pathlib import Path


def run(directory: str) -> int:
    """Refuse existing destinations so diagnostics cannot replace user files."""
    import traceback

    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    try:
        return _run(str(root))
    except Exception:
        (root / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


def _run(directory: str) -> int:
    from PIL import Image, ImageCms
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from .appearance import prepare_initial_appearance, prepare_window_for_show
    from .constants import APP_NAME, APP_ORGANIZATION
    from .gui import MainWindow
    from .processor import ProcessingOptions, ResizeSetting, process_image
    from .settings import _settings
    from .themes import apply_theme

    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(root / "settings"))
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    from .system_fonts import capture_system_appearance
    capture_system_appearance(app)
    app.setStyle("Fusion")
    # The Windows offscreen test platform can omit the desktop font catalog.
    # Register its installed font for diagnostic screenshots only; normal app
    # launches always use the operating system's own font selection.
    import os

    from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QFontDatabase
    if os.name == "nt" and app.platformName() == "offscreen":
        for name in ("segoeui.ttf", "seguisb.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    settings = _settings()
    prepare_initial_appearance(app, settings, theme_key="ui/appearance")
    apply_theme(app)
    source = root / "sample.png"
    Image.new("RGB", (60, 40), "red").save(source)
    before = source.read_bytes()
    window = MainWindow(appearance_settings=settings)
    prepare_window_for_show(window, window._fit_to_screen)
    window.show()
    window._open_paths([source])
    app.processEvents()
    assert window.progress_bar.progress_value() == 0
    assert window.progress_bar.progress_total() == 1
    assert window.status_label.text() == "1 photo ready. Choose Save Photo or Process All."
    assert not list(root.glob("*.jpg"))
    assert window.grab().save(str(root / "ui-ready.png"))
    from .appearance_qa import capture_appearance
    capture_appearance(app, window, root)
    batch = window.process_paths([source])
    assert batch.success_count == 1 and batch.failure_count == 0
    result = batch.results[0]
    with Image.open(result.destination_path) as output:
        assert output.size == (60, 60) and output.format == "JPEG"
    assert source.read_bytes() == before
    assert "1 succeeded" in window.status_label.text()
    assert window.progress_bar.progress_value() == window.progress_bar.progress_total() == 1
    app.processEvents()
    assert window.grab().save(str(root / "ui.png"))
    # Exercise the actual accessibility action in the frozen app, then inspect
    # exported pixels in both directions rather than trusting the highlighted size.
    large_source = root / "accessible-size.png"
    Image.new("RGB", (2200, 1100), "red").save(large_source)
    large_before = large_source.read_bytes()
    window._open_paths([large_source])
    for index, (label, side) in enumerate((("1000", 1000), ("Original", 2200)), start=1):
        button = next(button for button in window._resize_buttons if button.text() == label)
        interface = QAccessible.queryAccessibleInterface(button)
        assert interface is not None
        actions = interface.actionInterface()
        assert actions is not None
        action = QAccessibleActionInterface.toggleAction()
        assert action in actions.actionNames()
        actions.doAction(action)
        assert button.isChecked()
        window.process_btn.click()
        with Image.open(root / f"accessible-size ({index}).jpg") as output:
            assert output.size == (side, side)
        assert "1 succeeded, 0 failed" in window.status_label.text()
        assert large_source.read_bytes() == large_before
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
    watermark = root / "watermark.png"
    Image.new("RGB", (960, 960), (100, 100, 100)).save(watermark)
    watermark_before = watermark.read_bytes()
    marked = process_image(watermark, ProcessingOptions(
        resize=ResizeSetting("custom", 200), watermark_text="TEST", watermark_position="bottom-right",
    ))
    assert marked.success and watermark.read_bytes() == watermark_before
    with Image.open(marked.destination_path) as output:
        assert output.size == (200, 200)
        assert max(abs(c - 100) for x in range(200) for c in output.getpixel((x, 199))) <= 8
        assert max(abs(c - 100) for y in range(200) for c in output.getpixel((199, y))) <= 8
        with output.crop((100, 100, 200, 197)) as corner:
            assert corner.getextrema()[0][1] > 140
    (root / "result.json").write_text(json.dumps({
        "success": True, "checks": ["packaged GUI", "ready selection has zero completed outputs",
                                   "processing progress counts completed files", "square JPEG output",
                                   "accessibility Toggle exports selected dimensions in both directions",
                                   "source preserved",
                                   "neighbor collision preserved", "overwrite JPEG", "ICC and alpha compositing",
                                   "EXIF orientation", "export metadata removed",
                                   "small bottom-right watermark stays inside output"]
    }, indent=2), encoding="utf-8")
    return 0

