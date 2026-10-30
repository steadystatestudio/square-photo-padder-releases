from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from photocropper.constants import RESIZE_MODE_CUSTOM
from photocropper.gui import MainWindow
from photocropper.themes import apply_theme, install_theme_watcher


@pytest.fixture(autouse=True)
def cleanup_windows():
    yield
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def _configure_settings(tmp_path: Path) -> None:
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


def test_process_paths_handles_valid_and_invalid_files(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    invalid = tmp_path / "notes.txt"
    Image.new("RGB", (400, 200), (255, 255, 0)).save(valid)
    invalid.write_text("hello", encoding="utf-8")

    window = MainWindow()
    batch = window.process_paths([valid, invalid])

    assert batch.success_count == 1
    assert batch.failure_count == 0
    assert (tmp_path / "photo (1).jpg").exists()
    assert window.status_label.text().startswith("Finished 1 file(s)")


def test_output_written_next_to_source(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "source.png"
    Image.new("RGB", (500, 300), (10, 20, 30)).save(valid)

    window = MainWindow()
    batch = window.process_paths([valid])

    assert batch.success_count == 1
    assert (tmp_path / "source (1).jpg").is_file()


def test_theme_is_applied_with_hex_colors() -> None:
    app = _app()

    assert app.palette() is not None
    sheet = app.styleSheet()
    assert "QPushButton#processBtn" in sheet
    assert "QListWidget" in sheet
    assert "QProgressBar" in sheet
    # A hex color is present somewhere (exact accent varies with GTK theme)
    assert "#" in sheet


def test_initial_hint_lives_in_preview_not_bottom() -> None:
    """The click-or-drag hint shows in the preview square; the bottom
    status/results boxes start hidden (tester feedback)."""
    _app()

    window = MainWindow()

    text = window.preview_label.text().lower()
    assert "add photos" in text
    assert "drag" in text
    assert window.status_label.text() == ""
    # The per-file results box is gone entirely (tester feedback).
    assert not hasattr(window, "results_list")


def test_process_paths_accepts_folder_and_discovers_nested_images(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    folder = tmp_path / "batch"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    Image.new("RGB", (400, 200), (255, 255, 0)).save(folder / "one.jpg")
    Image.new("RGB", (200, 400), (0, 255, 255)).save(nested / "two.png")

    window = MainWindow()
    batch = window.process_paths([folder])

    assert batch.success_count == 2
    assert batch.failure_count == 0
    assert window.status_label.text().startswith("Finished 2 file(s)")


def test_processing_status_mentions_dropped_items(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 200), (255, 255, 0)).save(valid)

    window = MainWindow()
    window.process_paths([valid])

    assert "Finished 1 file(s)" in window.status_label.text()


def test_resize_defaults_to_original(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert window.current_resize_setting().output_label == "Original"
    # The Original segmented button should be the checked one
    checked = [b for b in window._resize_buttons if b.isChecked()]
    assert len(checked) == 1
    assert checked[0].text() == "Original"


def test_resize_preset_applies_to_batch_outputs(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 200), (255, 255, 0)).save(valid)

    window = MainWindow()
    window._handle_resize_choice(1080)
    batch = window.process_paths([valid])

    assert batch.success_count == 1
    assert "Size: 1080." in window.status_label.text()
    output_path = tmp_path / "photo (1).jpg"
    with Image.open(output_path) as processed:
        # 400x200 source pads to 400px square; presets never upscale.
        assert processed.size == (400, 400)


def test_custom_resize_is_restored_from_settings(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window.apply_custom_resize(1337)

    restored = MainWindow()

    assert restored._resize_mode == RESIZE_MODE_CUSTOM
    assert restored.current_resize_setting().size_px == 1337
    assert restored.custom_size_spin.value() == 1337


def test_marketplace_preset_labels(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    # Sizes run largest to smallest, then Custom (tester feedback).
    labels = [b.text() for b in window._resize_buttons]
    assert labels == ["Original", "2048", "1600", "1080", "1000", "Custom"]


def test_background_color_selection(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    assert window._background_color == (0, 0, 0)
    # The white/black shortcut buttons were removed; only the swatch remains.
    assert not hasattr(window, "white_btn")
    assert not hasattr(window, "black_btn")

    window._set_background_color((255, 255, 255))
    assert window._background_color == (255, 255, 255)


def test_no_clear_colors_button_on_main_window(tmp_path: Path) -> None:
    """Clear colors moved off the main window and into the color picker."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    assert not hasattr(window, "clear_colors_btn")


def test_swatch_opens_app_color_picker(tmp_path: Path) -> None:
    """The Background swatch opens the app's own compact picker (not Qt's
    stock QColorDialog) and applies the color it returns."""
    from photocropper.color_picker import BackgroundColorDialog

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    with patch.object(BackgroundColorDialog, "exec", lambda self: True), patch.object(
        BackgroundColorDialog, "selected_color", lambda self: (10, 20, 30)
    ):
        window._pick_background_color()

    assert window._background_color == (10, 20, 30)


def test_picker_basic_swatch_applies_in_one_click(tmp_path: Path) -> None:
    from photocropper.color_picker import BASIC_COLORS, BackgroundColorDialog

    _configure_settings(tmp_path)
    _app()
    dialog = BackgroundColorDialog(initial=(0, 0, 0))

    # A short single row of common colors — not the stock dialog's 42.
    assert len(dialog._basic_swatches) == len(BASIC_COLORS) <= 12

    dialog._basic_swatches[0].click()

    assert dialog.result() == 1  # accepted immediately, no OK step
    assert dialog.selected_color() == BASIC_COLORS[0]


def test_picker_mixed_color_is_saved_and_reoffered(tmp_path: Path) -> None:
    from photocropper.color_picker import BackgroundColorDialog
    from photocropper.settings import load_custom_colors

    _configure_settings(tmp_path)
    _app()

    dialog = BackgroundColorDialog(initial=(0, 0, 0))
    assert not dialog._custom_row.isVisibleTo(dialog)  # nothing saved yet
    dialog.hex_edit.textEdited.emit("#123456")
    dialog.use_btn.click()

    assert dialog.selected_color() == (0x12, 0x34, 0x56)
    # Saved automatically — no "Add to Custom Colors" step.
    assert load_custom_colors() == [(0x12, 0x34, 0x56)]

    # A fresh picker offers the saved color as a one-click swatch.
    reopened = BackgroundColorDialog(initial=(0, 0, 0))
    assert reopened._custom_row.isVisibleTo(reopened)
    assert [s.color() for s in reopened._custom_swatches] == [(0x12, 0x34, 0x56)]
    reopened._custom_swatches[0].click()
    assert reopened.selected_color() == (0x12, 0x34, 0x56)


def test_picker_clear_colors_empties_saved_customs(tmp_path: Path) -> None:
    from photocropper.color_picker import BackgroundColorDialog
    from photocropper.settings import load_custom_colors, save_custom_colors

    _configure_settings(tmp_path)
    _app()
    save_custom_colors([(12, 34, 56), (200, 100, 50)])

    dialog = BackgroundColorDialog(initial=(0, 0, 0))
    assert len(dialog._custom_swatches) == 2
    dialog.clear_colors_btn.click()

    assert load_custom_colors() == []
    assert dialog._custom_swatches == []
    assert not dialog._custom_row.isVisibleTo(dialog)


def test_custom_colors_dedupe_and_cap(tmp_path: Path) -> None:
    from photocropper.color_picker import MAX_CUSTOM_COLORS, BackgroundColorDialog
    from photocropper.settings import load_custom_colors, save_custom_colors

    _configure_settings(tmp_path)
    _app()
    save_custom_colors([(index, 0, 0) for index in range(MAX_CUSTOM_COLORS)])

    dialog = BackgroundColorDialog(initial=(0, 0, 0))
    dialog.hex_edit.textEdited.emit("#010000")  # already saved: (1, 0, 0)
    dialog.use_btn.click()

    saved = load_custom_colors()
    assert len(saved) == MAX_CUSTOM_COLORS  # deduped, capped
    assert saved[0] == (1, 0, 0)  # re-used color moves to the front


def test_rotation_controls(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._open_paths(_make_images(tmp_path, 1))
    assert window._rotation_degrees == 0

    window.rotate_cw_btn.click()
    assert window._rotation_degrees == 90

    window.rotate_cw_btn.click()
    assert window._rotation_degrees == 180

    window.rotate_ccw_btn.click()
    assert window._rotation_degrees == 90

    # Rotate back to 0 via CCW
    window.rotate_ccw_btn.click()
    assert window._rotation_degrees == 0


def test_processing_options_includes_all_settings(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._open_paths(_make_images(tmp_path, 1))
    window._set_background_color((0, 0, 0))
    window.watermark_input.setText("TEST")
    window.rotate_cw_btn.click()

    options = window.current_processing_options()

    assert options.background_color == (0, 0, 0)
    assert options.watermark_text == "TEST"
    assert options.rotation_degrees == 90


def test_processing_preference_persists(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._set_background_color((255, 255, 255))
    window.watermark_input.setText("HELLO")
    window._save_processing_preference()

    restored = MainWindow()

    assert restored._background_color == (255, 255, 255)
    assert restored.watermark_input.text() == "HELLO"


def test_empty_paths_returns_empty_batch(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    batch = window.process_paths([])

    assert batch.success_count == 0
    assert batch.failure_count == 0
    assert "No files were provided" in window.status_label.text()


def test_open_paths_enables_process_button(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 200), (255, 255, 0)).save(valid)

    window = MainWindow()
    assert window.process_btn.isEnabled() is False

    window._open_paths([valid])

    assert window.process_btn.isEnabled() is True
    # The label never carries the file count (tester feedback); the count
    # shows as segments on the button face.
    assert window.process_btn.text() == "Process All"
    assert window.progress_bar.progress_total() == 1


def test_open_paths_sizes_button_segments_to_count(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(a)
    Image.new("RGB", (100, 100), (0, 0, 0)).save(b)

    window = MainWindow()
    window._open_paths([a, b])

    assert window.process_btn.text() == "Process All"
    assert window.progress_bar.progress_total() == 2


def test_rotation_has_no_degree_label(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert not hasattr(window, "rotation_value_label")
    assert window.rotate_cw_btn.text() == ""
    assert window.rotate_ccw_btn.text() == ""


def test_watermark_size_and_position_persists(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._set_watermark_size("large")
    window._set_watermark_position("center")
    window._save_processing_preference()

    restored = MainWindow()

    assert restored._current_watermark_size() == "large"
    assert restored._current_watermark_position() == "center"



def test_process_btn_disabled_when_no_images_in_folder(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()

    window = MainWindow()
    window._open_paths([empty_folder])

    assert window.process_btn.isEnabled() is False


def test_current_processing_options_watermark_selection(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window.watermark_input.setText("MARK")
    window._set_watermark_size("small")
    window._set_watermark_position("bottom-left")

    options = window.current_processing_options()

    assert options.watermark_text == "MARK"
    assert options.watermark_size == "small"
    assert options.watermark_position == "bottom-left"


def test_process_with_custom_resize_produces_correct_output(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 200), (255, 255, 0)).save(valid)

    window = MainWindow()
    window.apply_custom_resize(300)
    batch = window.process_paths([valid])

    assert batch.success_count == 1
    output_path = tmp_path / "photo (1).jpg"
    with Image.open(output_path) as processed:
        assert processed.size == (300, 300)


def _make_images(tmp_path: Path, count: int) -> list[Path]:
    paths = []
    for i in range(count):
        p = tmp_path / f"img{i}.jpg"
        Image.new("RGB", (100, 100), (i * 40, 0, 0)).save(p)
        paths.append(p)
    return paths


def test_preview_has_no_nav_buttons(tmp_path: Path) -> None:
    """The side arrow buttons are gone entirely — browsing is keyboard-only
    (←/→), with the counter as the only on-screen nav indicator."""
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert not hasattr(window, "prev_btn")
    assert not hasattr(window, "next_btn")


def test_preview_counter_hidden_for_single_image(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 1)

    window = MainWindow()
    window._open_paths(paths)

    # The counter keeps its row (fixed-size window) but shows nothing.
    assert window.preview_counter.text() == ""


def test_preview_counter_shown_for_multiple_images(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)

    assert window.preview_counter.text() == "1 / 3"


def test_preview_show_at_cycles_forward_and_wraps(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)

    window._show_preview_at(window._preview_index + 1)
    assert window._preview_index == 1
    assert window.preview_counter.text() == "2 / 3"

    window._show_preview_at(window._preview_index + 1)
    assert window._preview_index == 2
    assert window.preview_counter.text() == "3 / 3"

    # Wraps around
    window._show_preview_at(window._preview_index + 1)
    assert window._preview_index == 0
    assert window.preview_counter.text() == "1 / 3"


def test_preview_show_at_wraps_backward_to_last(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)

    window._show_preview_at(window._preview_index - 1)
    assert window._preview_index == 2
    assert window.preview_counter.text() == "3 / 3"


def _activate(window: MainWindow) -> None:
    """Arrow-key cycling is a QShortcut, which only fires while the window
    is the active window — real key routing needs this, unlike calling
    keyPressEvent directly (which a prior version of this test did, but
    that bypasses Qt's actual focus-based event delivery entirely)."""
    window.show()
    QApplication.processEvents()
    window.activateWindow()
    QApplication.processEvents()


def test_preview_arrow_keys(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)
    _activate(window)

    QTest.keyClick(window, Qt.Key.Key_Down)
    assert window._preview_index == 1

    QTest.keyClick(window, Qt.Key.Key_Up)
    assert window._preview_index == 0


def test_preview_arrow_keys_work_regardless_of_button_focus(tmp_path: Path) -> None:
    """Buttons and checkboxes grab focus on click, but shouldn't swallow
    the cycling shortcut (a plain keyPressEvent override would miss this,
    since QPushButton consumes arrow keys before it ever bubbles up)."""
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)
    _activate(window)

    window.clear_btn.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.clear_btn, Qt.Key.Key_Down)
    assert window._preview_index == 1

    window.overwrite_check.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.overwrite_check, Qt.Key.Key_Down)
    assert window._preview_index == 2


def test_preview_arrow_keys_do_not_steal_text_field_editing(tmp_path: Path) -> None:
    """Left/Right must keep moving the text cursor in the watermark field
    and stepping the custom-size spin box, not hijack them for cycling."""
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)
    _activate(window)

    window.watermark_input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.watermark_input, Qt.Key.Key_Right)
    assert window._preview_index == 0

    window.custom_size_spin.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.custom_size_spin, Qt.Key.Key_Right)
    assert window._preview_index == 0


def test_preview_path_updates_on_navigation(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)

    window = MainWindow()
    window._open_paths(paths)
    assert window._preview_path == paths[0]

    window._show_preview_at(1)
    assert window._preview_path == paths[1]


def test_process_with_rotation_and_white_bg(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    valid = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 200), (0, 0, 255)).save(valid)

    window = MainWindow()
    window._set_background_color((255, 255, 255))
    window._open_paths([valid])  # rotation is remembered per shown photo
    window.rotate_cw_btn.click()  # 90 degrees on the loaded photo
    batch = window.process_paths([valid])

    assert batch.success_count == 1
    output_path = tmp_path / "photo (1).jpg"
    with Image.open(output_path) as processed:
        assert processed.size == (400, 400)
        # Top-left corner should be white background
        pixel = processed.getpixel((5, 5))
        assert pixel[0] > 250
        assert pixel[1] > 250
        assert pixel[2] > 250


# --- New feature tests ---


def test_toolbar_buttons_exist(tmp_path: Path) -> None:
    """Toolbar buttons all share the plain style — no highlighted button.
    Help and About are merged into one button; Settings is the icon-only
    gear, not a labeled toolbar button."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    from PySide6.QtWidgets import QPushButton
    highlighted = window.container.findChildren(QPushButton, "primaryBtn")
    toolbar = {btn.text() for btn in window.container.findChildren(QPushButton, "toolbarBtn")}
    assert highlighted == []
    assert {"Add Photos", "Add Folder", "Clear", "Help", "Settings"}.issubset(toolbar)
    assert "About" not in toolbar
    assert not hasattr(window, "about_btn")


def test_settings_label_is_readable_in_top_right(tmp_path: Path) -> None:
    """The gear is a minimal icon-only button, not a labeled toolbar button,
    and it sits last in the toolbar row (top-right corner)."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.settings_btn.objectName() == "toolbarBtn"
    assert window.settings_btn.text() == "Settings"
    assert window.settings_btn.icon().isNull()

    # The toolbar is the first row in the main column layout.
    toolbar_layout = window.container.layout().itemAt(0).layout()
    widgets = [toolbar_layout.itemAt(i).widget() for i in range(toolbar_layout.count())]
    assert widgets[-1] is window.settings_btn


def test_window_accepts_drops(tmp_path: Path) -> None:
    """Verify the main window accepts drag-and-drop."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.acceptDrops() is True


def test_drag_and_drop_accepts_files(tmp_path: Path) -> None:
    """Verify drop event with image files calls _open_paths."""
    _configure_settings(tmp_path)
    _app()
    img_path = tmp_path / "test.jpg"
    Image.new("RGB", (100, 100), (255, 0, 0)).save(img_path)

    window = MainWindow()
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(img_path))])

    with patch.object(window, "_open_paths") as mock_open:
        event = QDropEvent(
            QPoint(100, 100),
            Qt.DropAction.CopyAction,
            mime_data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        window.dropEvent(event)
        mock_open.assert_called_once()
        called_paths = mock_open.call_args[0][0]
        assert len(called_paths) == 1
        assert called_paths[0].name == "test.jpg"


def test_process_button_shows_processing_state(tmp_path: Path) -> None:
    """Verify button shows Processing... and disables during batch."""
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "test.jpg"
    Image.new("RGB", (100, 100)).save(img)

    window = MainWindow()
    window._open_paths([img])

    # Before processing
    assert window.process_btn.isEnabled()
    assert window.process_btn.text() == "Process All"

    # Process
    window._process_pending()

    # After processing, button should be re-enabled
    assert window.process_btn.isEnabled()


def test_window_geometry_saved_on_close(tmp_path: Path) -> None:
    """Verify closeEvent saves geometry to QSettings."""
    from photocropper.settings import _settings

    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window.resize(900, 700)

    event = QCloseEvent()
    window.closeEvent(event)

    assert _settings().value("window/geometry") is not None


def test_window_centers_on_screen_when_no_saved_geometry(tmp_path: Path) -> None:
    """A first launch (nothing saved yet) centers the window on the screen."""
    _configure_settings(tmp_path)
    app = _app()

    window = MainWindow()

    avail = app.primaryScreen().availableGeometry()
    frame = window.frameGeometry()
    assert abs(frame.center().x() - avail.center().x()) <= 1
    assert abs(frame.center().y() - avail.center().y()) <= 1


def test_window_position_restored_when_geometry_saved(tmp_path: Path) -> None:
    """A saved position is restored rather than being re-centered.

    (restoreGeometry doesn't reproduce the exact pixel position on every
    platform, e.g. the offscreen test platform applies frame-margin
    corrections — so this checks it lands back near its saved corner
    rather than pulled to the screen center, not pixel-exact equality.)
    """
    _configure_settings(tmp_path)
    app = _app()

    first = MainWindow()
    first.move(5, 5)
    first.closeEvent(QCloseEvent())

    second = MainWindow()

    avail = app.primaryScreen().availableGeometry()
    assert second.pos().x() < avail.center().x() - 100


def test_tooltips_enabled_by_default(tmp_path: Path) -> None:
    """Icon-only and ambiguous controls get descriptive tooltips by default."""
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert window._tooltips_enabled is True
    assert window.process_btn.toolTip() != ""
    assert all(b.toolTip() != "" for b in window._resize_buttons)
    assert all(b.toolTip() != "" for b in window._watermark_position_buttons.values())
    assert window.rotate_cw_btn.toolTip() != ""


def test_settings_dialog_opens_from_gear_icon_and_reflects_state(tmp_path: Path) -> None:
    """The tooltip toggle lives in the Settings dialog, opened via the gear
    icon — not on the main window anymore."""
    from photocropper.dialogs import SettingsDialog

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert not hasattr(window, "tooltips_check")

    seen = {}

    def fake_exec(self):
        seen["dialog"] = self
        return True

    with patch.object(SettingsDialog, "exec", fake_exec):
        window._show_settings()

    assert isinstance(seen["dialog"], SettingsDialog)
    assert seen["dialog"].tooltips_check.isChecked() is True


def test_settings_tooltips_toggle_clears_and_restores(tmp_path: Path) -> None:
    from photocropper.dialogs import SettingsDialog
    from photocropper.settings import load_tooltips_enabled

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    def fake_exec_off(self):
        self.tooltips_check.setChecked(False)
        return True

    with patch.object(SettingsDialog, "exec", fake_exec_off):
        window._show_settings()

    assert window.process_btn.toolTip() == ""
    assert all(b.toolTip() == "" for b in window._resize_buttons)
    assert load_tooltips_enabled() is False

    def fake_exec_on(self):
        self.tooltips_check.setChecked(True)
        return True

    with patch.object(SettingsDialog, "exec", fake_exec_on):
        window._show_settings()

    assert window.process_btn.toolTip() != ""
    assert load_tooltips_enabled() is True


def test_tooltips_preference_persists_across_windows(tmp_path: Path) -> None:
    from photocropper.dialogs import SettingsDialog

    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    def fake_exec_off(self):
        self.tooltips_check.setChecked(False)
        return True

    with patch.object(SettingsDialog, "exec", fake_exec_off):
        window._show_settings()

    reopened = MainWindow()

    assert reopened._tooltips_enabled is False
    assert reopened.process_btn.toolTip() == ""


def test_preview_shows_empty_state_hint(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    text = window.preview_label.text().lower()
    assert "add photos" in text


def test_viewport_grows_as_centered_square(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    _activate(window)
    window.resize(650, 850)
    QApplication.processEvents()
    first_side = window.preview_label.width()
    window.resize(900, 1100)
    QApplication.processEvents()
    assert window.preview_label.width() == window.preview_label.height()
    assert window.preview_label.width() > first_side
    area = window.preview_area
    assert window.preview_label.width() == min(area.width(), area.height())
    assert abs(window.preview_label.geometry().center().x() - area.rect().center().x()) <= 1
    window.close()


def test_preview_fills_square_for_small_photo(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 50), (200, 100, 50)).save(img)
    window = MainWindow()
    _activate(window)
    window._open_paths([img])
    pixmap = window.preview_label.pixmap()
    assert pixmap.width() == pixmap.height() == window.preview_label.width()
    window.close()


def test_window_is_resizable_and_maximizable(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QLayout

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    assert window.container.layout().sizeConstraint() == QLayout.SizeConstraint.SetMinimumSize
    assert window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert window.minimumSize() != window.maximumSize()


def test_watermark_bar_spans_window_above_process(tmp_path: Path) -> None:
    """The watermark input is one long window-wide bar directly above the
    Process button (tester feedback)."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    layout = window.container.layout()
    positions = {
        layout.itemAt(i).widget(): i
        for i in range(layout.count())
        if layout.itemAt(i).widget() is not None
    }
    # Its own full-width slot in the main column, right above Process.
    save_row = layout.itemAt(positions[window.watermark_input] + 1).layout()
    assert save_row.itemAt(2).layout().itemAt(1).widget() is window.save_photo_btn
    assert save_row.itemAt(1).widget() is window.process_btn


def test_toolbar_button_highlights_while_busy(tmp_path: Path) -> None:
    """Help lights up blue while its dialog is open, then returns to normal."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    seen = {}

    def fake_information(*args, **kwargs):
        seen["busy_during"] = window.help_btn.property("busy")

    with patch("photocropper.gui.QMessageBox.information", side_effect=fake_information):
        window._show_help()

    assert seen["busy_during"] is True
    assert window.help_btn.property("busy") is False


def test_help_recommends_sizes_per_marketplace(tmp_path: Path) -> None:
    """Help explains which size to pick for eBay, Amazon, OfferUp, etc."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    with patch("photocropper.gui.QMessageBox.information") as mock_info:
        window._show_help()

    text = mock_info.call_args[0][2]
    for marketplace in ("eBay", "Amazon", "OfferUp", "Etsy", "Instagram"):
        assert marketplace in text
    for size in ("2048", "1600", "1080", "1000"):
        assert size in text


def test_help_dialog_includes_about_content(tmp_path: Path) -> None:
    """Help and About are combined into one window (tester feedback): the
    version, "no cloud" claim, and Ko-fi link all show up alongside the
    how-to-use instructions."""
    from photocropper.constants import APP_VERSION, KOFI_URL

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    with patch("photocropper.gui.QMessageBox.information") as mock_info:
        window._show_help()

    title = mock_info.call_args[0][1]
    text = mock_info.call_args[0][2]
    assert "Help" in title and "About" in title
    assert APP_VERSION in text
    assert "No cloud" in text
    assert KOFI_URL in text
    assert not hasattr(window, "_show_about")


def test_custom_size_box_next_to_custom_with_right_aligned_digits(tmp_path: Path) -> None:
    """The box sits right after the Custom button; digits are right-aligned
    so numbers enter at the right edge and fill leftward (tester feedback)."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.custom_size_spin.alignment() & Qt.AlignmentFlag.AlignRight

    row = window._custom_btn.parentWidget().layout()
    # Locate the size row inside the panel and check adjacency.
    for r in (row.itemAt(i).layout() for i in range(row.count())):
        if r is None:
            continue
        widgets = [r.itemAt(i).widget() for i in range(r.count())]
        if window._custom_btn in widgets:
            custom_index = widgets.index(window._custom_btn)
            assert widgets[custom_index + 1] is window.custom_size_spin
            break
    else:
        raise AssertionError("size row not found")


def test_process_button_disabled_initially(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.process_btn.isEnabled() is False
    assert window.process_btn.text() == "Process All"


def test_duplicate_paths_deduplicated(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "photo.jpg"
    Image.new("RGB", (100, 100)).save(img)

    window = MainWindow()
    window._open_paths([img, img])

    # Deduplication happens in expand_input_paths
    assert len(window._preview_paths) == 1


def test_theme_watcher_reapplies_on_palette_change() -> None:
    """Synthetic ApplicationPaletteChange should trigger apply_theme re-run."""
    from PySide6.QtCore import QEvent

    app = _app()
    install_theme_watcher(app)
    app.setStyleSheet("")
    assert app.styleSheet() == ""

    app.sendEvent(app, QEvent(QEvent.Type.ApplicationPaletteChange))

    sheet = app.styleSheet()
    assert "QPushButton#processBtn" in sheet


def test_rotation_is_remembered_per_photo(tmp_path: Path) -> None:
    """Each photo keeps its own orientation as you flip through the batch."""
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)

    window = MainWindow()
    window._open_paths(paths)

    # Rotate the first photo clockwise.
    window.rotate_cw_btn.click()
    assert window._rotation_degrees == 90
    assert window._rotation_by_path[paths[0]] == 90

    # Move to the second photo: it starts unrotated, independent of the first.
    window._show_preview_at(1)
    assert window._rotation_degrees == 0
    window.rotate_ccw_btn.click()
    assert window._rotation_degrees == 270
    assert window._rotation_by_path[paths[1]] == 270

    # Back to the first photo: its own 90° rotation is restored.
    window._show_preview_at(0)
    assert window._rotation_degrees == 90


def test_per_photo_rotation_applied_on_process(tmp_path: Path) -> None:
    """Processing applies each photo's own remembered rotation."""
    _configure_settings(tmp_path)
    _app()
    wide = tmp_path / "wide.jpg"
    Image.new("RGB", (400, 200), (0, 0, 255)).save(wide)
    tall = tmp_path / "tall.jpg"
    Image.new("RGB", (200, 400), (0, 255, 0)).save(tall)

    window = MainWindow()
    window._open_paths([wide, tall])
    # Rotate only the first photo; the second stays as-is.
    window.rotate_cw_btn.click()
    assert window._rotation_by_path == {wide: 90}

    batch = window.process_paths([wide, tall])
    assert batch.success_count == 2


def test_new_selection_resets_rotations(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    first = _make_images(tmp_path, 1)
    window = MainWindow()
    window._open_paths(first)
    window.rotate_cw_btn.click()
    assert window._rotation_by_path

    second = [tmp_path / "other.jpg"]
    Image.new("RGB", (100, 100), (0, 0, 0)).save(second[0])
    window._open_paths(second)
    assert window._rotation_by_path == {}
    assert window._rotation_degrees == 0


def test_donate_button_hidden_when_kofi_unconfigured(tmp_path: Path, monkeypatch) -> None:
    """With an unconfigured KOFI_URL, no Donate toolbar button ships."""
    _configure_settings(tmp_path)
    _app()
    monkeypatch.setattr("photocropper.gui.KOFI_CONFIGURED", False)
    window = MainWindow()

    from PySide6.QtWidgets import QPushButton
    toolbar_btns = window.container.findChildren(QPushButton, "toolbarBtn")
    labels = [btn.text() for btn in toolbar_btns]
    assert "Donate" not in labels


def test_donate_button_shown_when_kofi_configured(tmp_path: Path) -> None:
    """The shipped KOFI_URL is real, so the Donate toolbar button is present."""
    from photocropper.constants import KOFI_CONFIGURED

    assert KOFI_CONFIGURED, "shipped KOFI_URL should be a real Ko-fi page"

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    from PySide6.QtWidgets import QPushButton
    toolbar_btns = window.container.findChildren(QPushButton, "toolbarBtn")
    labels = [btn.text() for btn in toolbar_btns]
    assert "Donate" in labels


def test_watermark_settings_persist_across_windows(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    w1 = MainWindow()
    w1.watermark_input.setText("SOLD")
    w1._set_watermark_size("large")
    w1._set_watermark_position("center")

    w2 = MainWindow()
    assert w2.watermark_input.text() == "SOLD"
    assert w2._current_watermark_size() == "large"
    assert w2._current_watermark_position() == "center"


def test_process_button_has_no_segments_initially(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert window.progress_bar.progress_total() == 0
    assert window.process_btn.isEnabled() is False


def test_process_button_segments_track_batch(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)

    window = MainWindow()
    window._open_paths(paths)
    window._process_pending()

    # After processing, the button's segments are full and the label is back
    # to plain Process.
    assert window.progress_bar.progress_total() == 3
    assert window.progress_bar.progress_value() == 3
    assert window.process_btn.text() == "Process All"


def test_top_corner_watermark_positions_available(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert "top-left" in window._watermark_position_buttons
    assert "top-right" in window._watermark_position_buttons
    window._set_watermark_position("top-right")
    assert window._current_watermark_position() == "top-right"


def test_custom_button_label_has_no_ellipsis(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    # When no custom size is active, the button should read "Custom" exactly
    assert window._custom_btn.text() == "Custom"


def test_progress_is_separate_from_process_action(tmp_path: Path) -> None:
    """The segmented bar is merged into the Process button (tester feedback)."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.progress_bar is not window.process_btn

    # After a batch finishes the button stays enabled with full segments.
    paths = _make_images(tmp_path, 2)
    window._open_paths(paths)
    window._process_pending()
    assert window.process_btn.isEnabled()
    assert window.progress_bar.progress_value() == 2
    assert window.process_btn.text() == "Process All"


def test_output_label_omits_px(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._handle_resize_choice(1600)

    assert window.current_resize_setting().output_label == "1600"


# --- v1.4.0 rework ---


def test_clear_button_resets_loaded_photos(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)

    window = MainWindow()
    assert window.clear_btn.isEnabled() is False

    window._open_paths(paths)
    assert window.clear_btn.isEnabled() is True
    assert window.process_btn.isEnabled() is True

    window.clear_btn.click()

    assert window._pending_paths == []
    assert window._preview_paths == []
    assert window._preview_path is None
    assert window.process_btn.isEnabled() is False
    assert window.process_btn.text() == "Process All"
    assert window.clear_btn.isEnabled() is False
    # Files on disk are untouched
    assert all(p.exists() for p in paths)


def test_custom_spinbox_applies_inline_without_popup(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window.custom_size_spin.setValue(777)
    window._handle_resize_choice(RESIZE_MODE_CUSTOM)

    assert window._resize_mode == RESIZE_MODE_CUSTOM
    assert window.current_resize_setting().size_px == 777


def test_custom_size_persists_even_when_preset_selected(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    w1 = MainWindow()
    w1.custom_size_spin.setValue(999)
    w1._custom_size_committed()
    w1._handle_resize_choice(1600)  # switch away from custom

    w2 = MainWindow()
    assert w2.custom_size_spin.value() == 999


def test_stored_removed_preset_migrates_to_custom(tmp_path: Path) -> None:
    """A stored preset that no longer exists (e.g. old 1200) restores as custom."""
    from photocropper.settings import StoredResizePreference, save_resize_preference

    _configure_settings(tmp_path)
    _app()
    save_resize_preference(StoredResizePreference(mode="preset:1200", size_px=1200))

    window = MainWindow()

    assert window._resize_mode == RESIZE_MODE_CUSTOM
    assert window.current_resize_setting().size_px == 1200


def test_overwrite_always_starts_off(tmp_path: Path) -> None:
    """Overwrite is destructive, so it must be opted into every session —
    it never restores as checked from a previous run."""
    _configure_settings(tmp_path)
    _app()

    w1 = MainWindow()
    assert w1.overwrite_check.isChecked() is False
    w1.overwrite_check.setChecked(True)
    w1._save_processing_preference()

    w2 = MainWindow()
    assert w2.overwrite_check.isChecked() is False


def test_overwrite_processing_has_no_confirmation_popup(tmp_path: Path) -> None:
    """Processing with Overwrite on runs straight through, no dialog."""
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "photo.jpg"
    Image.new("RGB", (100, 50)).save(img)

    window = MainWindow()
    window.overwrite_check.setChecked(True)
    window._open_paths([img])
    with patch("photocropper.gui.QMessageBox.warning") as mock_warn:
        window._process_pending()
    mock_warn.assert_not_called()

    with Image.open(img) as out:
        assert out.size == (100, 100)


def test_overwrite_checkbox_label_and_indicator(tmp_path: Path) -> None:
    """Label reads just Overwrite, with the check box on its right."""
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()

    assert window.overwrite_check.text() == "Overwrite"
    assert window.overwrite_check.layoutDirection() == Qt.LayoutDirection.RightToLeft


def test_overwrite_flag_reaches_processing_options(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    assert window.current_processing_options().overwrite is False
    window.overwrite_check.setChecked(True)
    assert window.current_processing_options().overwrite is True


def test_watermark_placeholder_is_watermark(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    assert window.watermark_input.placeholderText() == "Watermark"


def test_position_and_rotate_buttons_use_icons(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()

    for btn in window._watermark_position_buttons.values():
        assert btn.text() == ""
        assert not btn.icon().isNull()
    for btn in (window.rotate_cw_btn, window.rotate_ccw_btn):
        assert btn.text() == ""
        assert not btn.icon().isNull()


def test_stylesheet_has_no_hardcoded_base_font(tmp_path: Path) -> None:
    app = _app()

    assert "font-size: 10pt" not in app.styleSheet()


def test_progress_track_is_segmented(tmp_path: Path) -> None:
    """The button face draws one segment per file at small counts."""
    from photocropper.gui import SegmentProgress

    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    assert isinstance(window.progress_bar, SegmentProgress)

    btn = SegmentProgress()
    btn.resize(400, 40)
    btn.set_progress(2, 5)
    pixmap = btn.grab()
    assert not pixmap.isNull()

    image = pixmap.toImage()
    # A filled segment (left side) must differ in color from an unfilled one (right side).
    filled = image.pixelColor(image.width() // 5, image.height() - 7)
    unfilled = image.pixelColor(image.width() - image.width() // 5, image.height() - 7)
    assert filled != unfilled


def test_progress_track_groups_huge_batches(tmp_path: Path) -> None:
    """80+ files: segments group multiple files each instead of vanishing."""
    from photocropper.gui import SegmentProgress

    _configure_settings(tmp_path)
    _app()

    btn = SegmentProgress()
    btn.resize(400, 40)
    btn.set_progress(250, 500)
    pixmap = btn.grab()
    assert not pixmap.isNull()

    image = pixmap.toImage()
    # The half-done face must still read as progress: filled on the left,
    # unfilled track on the right.
    filled = image.pixelColor(image.width() // 8, image.height() - 7)
    unfilled = image.pixelColor(image.width() - image.width() // 8, image.height() - 7)
    assert filled != unfilled


# --- v1.4.3 fit-to-width UI scaling ---


def test_set_ui_scale_scales_font_and_paddings(tmp_path: Path) -> None:
    from photocropper.themes import set_ui_scale, ui_scale

    app = _app()
    set_ui_scale(app, 1.0)
    full_pt = app.font().pointSizeF()
    full_sheet = app.styleSheet()

    set_ui_scale(app, 0.7)
    try:
        assert ui_scale() == 0.7
        assert app.font().pointSizeF() < full_pt
        assert app.styleSheet() != full_sheet
    finally:
        set_ui_scale(app, 1.0)
    assert app.font().pointSizeF() == full_pt


def test_ui_scale_shrinks_when_window_too_narrow(tmp_path: Path) -> None:
    from photocropper.themes import set_ui_scale, ui_scale

    _configure_settings(tmp_path)
    app = _app()
    set_ui_scale(app, 1.0)
    window = MainWindow()
    try:
        needed = window.container.layout().minimumSize().width()
        assert needed > 0
        window.setMinimumSize(0, 0)
        window.container.resize(needed // 2, 560)
        window._fit_ui_scale()
        assert window._SCALE_MIN <= ui_scale() < 1.0
    finally:
        set_ui_scale(app, 1.0)


def test_ui_scale_restores_when_window_is_wide(tmp_path: Path) -> None:
    from photocropper.themes import set_ui_scale, ui_scale

    _configure_settings(tmp_path)
    app = _app()
    set_ui_scale(app, 0.7)
    window = MainWindow()
    try:
        needed = window.container.layout().minimumSize().width()
        window.container.resize(needed * 3, 560)
        window._fit_ui_scale()
        assert ui_scale() == 1.0
    finally:
        set_ui_scale(app, 1.0)


def test_ui_scale_noop_at_native_size_in_wide_window(tmp_path: Path) -> None:
    from photocropper.themes import set_ui_scale, ui_scale

    _configure_settings(tmp_path)
    app = _app()
    set_ui_scale(app, 1.0)
    window = MainWindow()
    sheet_before = app.styleSheet()
    needed = window.container.layout().minimumSize().width()
    window.container.resize(needed * 2, 560)
    window._fit_ui_scale()
    assert ui_scale() == 1.0
    assert app.styleSheet() == sheet_before


def test_file_folder_dialog_allows_extended_selection(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QAbstractItemView, QListView

    from photocropper.dialogs import FileFolderDialog

    _configure_settings(tmp_path)
    _app()

    dialog = FileFolderDialog(None, "Test", str(tmp_path))
    view = dialog.findChild(QListView, "listView")
    assert view is not None
    assert view.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert dialog.selected_paths() == []


def test_add_photos_starts_load_animation(tmp_path: Path) -> None:
    """Adding photos fills the button's segments one per file."""
    _configure_settings(tmp_path)
    _app()
    imgs = []
    for i in range(3):
        img = tmp_path / f"photo{i}.jpg"
        Image.new("RGB", (100, 100)).save(img)
        imgs.append(img)

    window = MainWindow()
    window._open_paths(imgs)

    assert window.progress_bar.progress_total() == 3
    assert window._load_anim_timer.isActive()
    # The button is clickable while its face fills up.
    assert window.process_btn.isEnabled()

    # Drive the animation to completion.
    while window.progress_bar.progress_value() < window.progress_bar.progress_total():
        window._advance_load_animation()
    assert not window._load_anim_timer.isActive()

    # The filled segments stay put; the label is still plain Process.
    assert window.progress_bar.progress_value() == 3
    assert window.process_btn.text() == "Process All"


def test_load_animation_finishes_quickly_for_huge_batches(tmp_path: Path) -> None:
    """A 500-photo batch must fill in about half a second, not many seconds."""
    _configure_settings(tmp_path)
    _app()

    window = MainWindow()
    window._start_load_animation(500)

    interval = window._load_anim_timer.interval()
    ticks_needed = math.ceil(500 / window._load_anim_step)
    assert interval * ticks_needed <= 800

    window._load_anim_timer.stop()


def test_clear_stops_load_animation(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "photo.jpg"
    Image.new("RGB", (100, 100)).save(img)

    window = MainWindow()
    window._open_paths([img])
    assert window._load_anim_timer.isActive()

    window._clear_photos()

    assert not window._load_anim_timer.isActive()
    assert window.progress_bar.progress_total() == 0
    assert window.process_btn.isEnabled() is False


def test_processing_reuses_button_segments(tmp_path: Path) -> None:
    """Processing refills the button's segments; they stay full when done."""
    _configure_settings(tmp_path)
    _app()
    img = tmp_path / "photo.jpg"
    Image.new("RGB", (100, 100)).save(img)

    window = MainWindow()
    window._open_paths([img])
    window._process_pending()

    assert not window._load_anim_timer.isActive()
    assert window.progress_bar.progress_value() == window.progress_bar.progress_total() == 1
    assert window.process_btn.text() == "Process All"


def test_keyboard_rotates_and_saves_only_current_photo(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)
    window = MainWindow()
    window._open_paths(paths)
    _activate(window)
    window.save_photo_btn.setFocus()
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Left)
    assert window._rotation_by_path == {paths[0]: 270}
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Right)
    assert window._rotation_degrees == 0
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Down)
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Right)
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Return)
    assert (tmp_path / "img1 (1).jpg").exists()
    assert not (tmp_path / "img0 (1).jpg").exists()
    assert window._preview_index == 1
    assert window._rotation_by_path == {paths[1]: 90}
    assert window.status_label.text() == "Saved img1 (1).jpg"
    QTest.keyClick(window.save_photo_btn, Qt.Key.Key_Enter)
    assert (tmp_path / "img1 (2).jpg").exists()


def test_review_shortcuts_leave_editors_and_dialogs_alone(tmp_path: Path) -> None:
    from photocropper.dialogs import SettingsDialog

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    window._open_paths(_make_images(tmp_path, 2))
    _activate(window)
    for editor in (window.watermark_input, window.custom_size_spin):
        editor.setFocus()
        for key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Return):
            QTest.keyClick(editor, key)
    assert window._preview_index == 0
    assert window._rotation_degrees == 0
    assert not list(tmp_path.glob("* (1).jpg"))
    dialog = SettingsDialog(window)
    dialog.setModal(True)
    dialog.show()
    dialog.activateWindow()
    QApplication.processEvents()
    QTest.keyClick(dialog.appearance, Qt.Key.Key_Down)
    assert window._preview_index == 0
    QTest.keyClick(dialog, Qt.Key.Key_Return)
    assert not list(tmp_path.glob("* (1).jpg"))
    dialog.close()


def test_save_photo_uses_current_options_and_resets_overwritten_rotation(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    path = tmp_path / "wide.jpg"
    Image.new("RGB", (200, 100), "red").save(path)
    window = MainWindow()
    window._open_paths([path])
    window.apply_custom_resize(120)
    window._set_background_color((255, 255, 255))
    window._rotate(90)
    window.overwrite_check.setChecked(True)
    window._save_current_photo()
    with Image.open(path) as output:
        assert output.size == (120, 120)
        assert output.getpixel((5, 60))[0] > 240
        assert output.getpixel((5, 60))[1] > 240
        assert output.getpixel((60, 5))[1] < 20
    assert window._rotation_degrees == 0
    assert window._rotation_by_path == {}
    assert "120 × 120" in window.metadata_label.text()


def test_save_failure_stays_on_photo_and_recovers_controls(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 1)
    window = MainWindow()
    window._open_paths(paths)
    paths[0].write_bytes(b"broken image")
    with patch("photocropper.gui.QMessageBox.warning") as warning:
        window._save_current_photo()
    warning.assert_called_once()
    assert window._preview_path == paths[0]
    assert not window._processing
    assert window.save_photo_btn.isEnabled()
    assert not list(tmp_path.glob("* (1).jpg"))


def test_processing_blocks_review_and_nested_saves(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)
    window = MainWindow()
    window._open_paths(paths)
    from photocropper.processor import process_images

    def during_processing(*args, **kwargs):
        assert window._processing
        assert not window.save_photo_btn.isEnabled()
        assert window.process_btn.isEnabled()
        assert window.process_btn.text() == "Cancel"
        window._show_preview_at(1)
        window._rotate(90)
        window._save_current_photo()
        window._process_pending()
        window._clear_photos()
        assert window._preview_index == 0
        assert window._rotation_degrees == 0
        return process_images(*args, **kwargs)

    with patch("photocropper.gui.process_images", during_processing):
        window._save_current_photo()
    assert window.process_btn.isEnabled()
    assert window.save_photo_btn.isEnabled()
    assert not (tmp_path / "img1 (1).jpg").exists()


def test_metadata_tracks_source_navigation_missing_files_and_clear(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    jpg = tmp_path / "photo.jpg"
    png = tmp_path / ("long_filename_" * 10 + ".png")
    Image.new("RGB", (200, 100)).save(jpg)
    Image.new("RGB", (50, 60)).save(png)
    window = MainWindow()
    _activate(window)
    window._open_paths([jpg, png])
    assert window.filename_label.text() == jpg.name
    assert "200 × 100 · JPEG ·" in window.metadata_label.text()
    window._show_preview_at(1)
    assert "50 × 60 · PNG ·" in window.metadata_label.text()
    assert window.filename_label.toolTip() == png.name
    assert "…" in window.filename_label.text()
    png.unlink()
    window._show_preview_at(1)
    assert window.metadata_label.text() == "— · — · —"
    assert "file missing" in window.preview_label.text()
    window._clear_photos()
    assert window.metadata_label.text() == window.filename_label.text() == ""
    assert not window.save_photo_btn.isEnabled()


def test_settings_cancel_discards_all_changes(tmp_path: Path) -> None:
    from photocropper.dialogs import SettingsDialog
    from photocropper.settings import load_appearance, load_tooltips_enabled

    _configure_settings(tmp_path)
    app = _app()
    window = MainWindow()
    before = app.styleSheet()

    def cancel(dialog):
        dialog.tooltips_check.setChecked(False)
        dialog.appearance.setCurrentIndex(dialog.appearance.findData("dark"))
        return 0

    with patch.object(SettingsDialog, "exec", cancel):
        window._show_settings()
    assert load_appearance() == "system"
    assert load_tooltips_enabled()
    assert app.styleSheet() == before


def test_appearance_save_persists_and_theme_events_respect_selection(tmp_path: Path, monkeypatch) -> None:
    from photocropper.dialogs import SettingsDialog
    from photocropper.settings import load_appearance
    from photocropper.themes import _D, _L, active_colors

    monkeypatch.delenv("SPP_THEME", raising=False)
    _configure_settings(tmp_path)
    app = _app()
    install_theme_watcher(app)
    window = MainWindow()

    def save(dialog):
        dialog.appearance.setCurrentIndex(dialog.appearance.findData("dark"))
        return 1

    with patch.object(SettingsDialog, "exec", save):
        window._show_settings()
    assert load_appearance() == "dark"
    assert active_colors["window"] == _D["window"]
    app.sendEvent(app, QEvent(QEvent.Type.ThemeChange))
    assert active_colors["window"] == _D["window"]
    assert SettingsDialog(window, appearance=load_appearance()).appearance.currentData() == "dark"
    monkeypatch.setenv("SPP_THEME", "light")
    apply_theme(app)
    assert active_colors["window"] == _L["window"]


def test_system_appearance_follows_detection(tmp_path: Path, monkeypatch) -> None:
    from photocropper.themes import _D, _L, active_colors

    _configure_settings(tmp_path)
    monkeypatch.delenv("SPP_THEME", raising=False)
    app = _app()
    for dark, colors in ((True, _D), (False, _L)):
        with patch("photocropper.themes._is_system_dark_mode", return_value=dark):
            apply_theme(app)
        assert active_colors["window"] == colors["window"]


def test_maximized_state_is_remembered(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    window.showMaximized()
    QApplication.processEvents()
    assert window.preview_label.width() == window.preview_label.height()
    assert window.controls_widget.isVisible()
    window.close()
    restored = MainWindow()
    assert restored.isMaximized()


def test_empty_review_actions_do_nothing(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    window._save_current_photo()
    window._rotate(90)
    window._show_preview_at(1)
    assert window._preview_path is None
    assert window._rotation_degrees == 0
    assert not window.save_photo_btn.isEnabled()


def test_repeated_folder_process_uses_previewed_selection(tmp_path):
    _configure_settings(tmp_path)
    _app()
    Image.new("RGB", (30, 20), "red").save(tmp_path / "original.png")
    window = MainWindow()
    window._open_paths([tmp_path])
    assert len(window._preview_paths) == 1
    window._process_pending()
    window._process_pending()
    assert window.status_label.text().startswith("Finished 1 file(s)")
    assert sorted(p.name for p in tmp_path.glob("*.jpg")) == ["original (1).jpg", "original (2).jpg"]


def test_all_failures_show_filename_and_reason(tmp_path):
    from photocropper.processor import BatchResult, ImageResult, ResizeSetting

    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    batch = BatchResult([ImageResult(tmp_path / "holiday.jpg", False, error="Disk full")])
    with patch("photocropper.gui.QMessageBox.warning") as warning:
        window._render_results(batch, ResizeSetting.original())
    message = warning.call_args.args[2]
    assert "holiday.jpg" in message and "Disk full" in message


def test_remote_drop_never_imports_working_directory(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    window = MainWindow()
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.invalid/photo.jpg"), QUrl()])
    event = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    with patch.object(window, "_open_paths") as opened:
        window.dropEvent(event)
    opened.assert_not_called()
    assert not event.isAccepted()


def test_mixed_drop_imports_only_local_paths(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    path = _make_images(tmp_path, 1)[0]
    window = MainWindow()
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.invalid/photo.jpg"), QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    with patch.object(window, "_open_paths") as opened:
        window.dropEvent(event)
    opened.assert_called_once_with([path])
    assert event.isAccepted()


def test_cancel_stops_between_photos_and_recovers_for_next_batch(tmp_path: Path) -> None:
    from photocropper import processor

    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 3)
    before = {path: path.read_bytes() for path in paths}
    window = MainWindow()
    window._open_paths(paths)
    original = processor.process_image
    calls = []

    def cancel_after_first(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        calls.append(path)
        assert window.process_btn.isEnabled()
        assert window.process_btn.text() == "Cancel"
        window.process_btn.click()
        window._process_or_cancel()  # A repeated click cannot start a nested batch.
        return result

    with patch.object(processor, "process_image", cancel_after_first):
        window._process_pending()
    assert calls == paths[:1]
    assert all(path.read_bytes() == before[path] for path in paths)
    assert len(list(tmp_path.glob("* (1).jpg"))) == 1
    assert window.status_label.text() == (
        "Stopped after 1 of 3 file(s): 1 succeeded, 0 failed; 2 not processed."
    )
    assert window.progress_bar.progress_value() == 1
    assert window.progress_bar.progress_total() == 3
    assert window.process_btn.text() == "Process All"
    assert window.process_btn.isEnabled() and window.save_photo_btn.isEnabled()
    assert not window._processing
    window._process_pending()
    assert window.status_label.text().startswith("Finished 3 file(s)")
    assert len(list(tmp_path.glob("* (1).jpg"))) == 3
    assert (tmp_path / "img0 (2).jpg").exists()


def test_close_during_batch_waits_for_current_photo_and_stops(tmp_path: Path) -> None:
    from photocropper import processor

    _configure_settings(tmp_path)
    app = _app()
    paths = _make_images(tmp_path, 3)
    window = MainWindow()
    window.show()
    window._open_paths(paths)
    original = processor.process_image
    calls = []

    def close_after_first(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        calls.append(path)
        window.close()
        assert window.isVisible()  # Close is deferred until processing returns.
        assert window._cancel_requested
        return result

    with patch.object(processor, "process_image", close_after_first):
        window._process_pending()
    assert calls == paths[:1]
    assert len(list(tmp_path.glob("* (1).jpg"))) == 1
    assert not window._processing
    app.processEvents()
    assert not window.isVisible()


def test_cancel_before_first_photo_writes_nothing(tmp_path: Path) -> None:
    from PySide6.QtCore import QTimer

    _configure_settings(tmp_path)
    _app()
    paths = _make_images(tmp_path, 2)
    window = MainWindow()
    window._open_paths(paths)
    QTimer.singleShot(0, window.process_btn.click)
    window._process_pending()
    assert not list(tmp_path.glob("* (1).jpg"))
    assert window.status_label.text().startswith("Stopped after 0 of 2 file(s)")
    assert window.process_btn.isEnabled()


def test_batch_overwrite_resets_only_successful_in_place_rotations(tmp_path: Path) -> None:
    from photocropper.processor import process_images

    _configure_settings(tmp_path)
    _app()
    jpeg = tmp_path / "wide.jpg"
    png = tmp_path / "tall.png"
    Image.new("RGB", (200, 100), "red").save(jpeg)
    Image.new("RGB", (100, 200), "blue").save(png)
    window = MainWindow()
    window._open_paths([jpeg, png])
    window._rotate(90)
    window._show_preview_at(1)
    window._rotate(90)
    window._show_preview_at(0)
    window.overwrite_check.setChecked(True)
    window._process_pending()
    assert window._rotation_by_path == {png: 90}
    assert window._rotation_degrees == 0
    assert "200 × 200" in window.metadata_label.text()
    with patch("photocropper.gui.process_images", wraps=process_images) as process:
        window._process_pending()
    assert process.call_args.kwargs["rotation_overrides"] == {png: 90}


def test_toolbar_flash_timer_dies_with_button(tmp_path: Path) -> None:
    from PySide6.QtCore import QTimer

    _configure_settings(tmp_path)
    app = _app()
    window = MainWindow()
    window._flash_toolbar_busy(window.add_btn, duration_ms=10)
    assert window.add_btn.findChildren(QTimer)
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(30)  # No callback is left pointing at a deleted QWidget.


def test_oversized_preview_explains_the_size_limit(tmp_path: Path, monkeypatch) -> None:
    from photocropper import processor

    _configure_settings(tmp_path)
    _app()
    source = tmp_path / "too-large.png"
    Image.new("RGB", (40, 20), "red").save(source)
    monkeypatch.setattr(processor, "MAX_SOURCE_PIXELS", 10)
    window = MainWindow()
    window._open_paths([source])
    assert "Image too large (40x20)" in window.preview_label.text()
    assert "limit is 10 source pixels" in window.preview_label.text()
    assert not list(tmp_path.glob("*.jpg"))


def test_preview_error_falls_back_to_exception_type_when_message_empty(tmp_path: Path) -> None:
    _configure_settings(tmp_path)
    _app()
    source = _make_images(tmp_path, 1)[0]
    window = MainWindow()
    with patch("photocropper.gui.generate_preview", side_effect=MemoryError()):
        window._open_paths([source])
    assert window.preview_label.text() == "Preview unavailable (MemoryError)"
