"""Picker font/cancel verification with exact scoped Qt preference restoration."""

import importlib
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
    QTextEdit,
    QToolTip,
    QWidget,
)

SOURCE = next((Path(__file__).parents[1] / "src").glob("*/qa_file_dialog.py")).parent
HELPER = importlib.import_module(SOURCE.name + ".qa_file_dialog")
QA = importlib.import_module(SOURCE.name + ".appearance_qa")
APPEARANCE = importlib.import_module(SOURCE.name + ".appearance")
THEMES = importlib.import_module(SOURCE.name + ".themes")


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance() or QApplication([])
    return instance


def group(settings):
    settings.sync()
    settings.beginGroup("FileDialog")
    values = {k: settings.value(k) for k in settings.allKeys()}
    settings.endGroup()
    return values


def native_store_snapshot(settings):
    """Read actual Windows values independently of QSettings' in-process cache."""
    if os.name != "nt":
        return None
    import winreg

    prefix = "\\HKEY_CURRENT_USER\\"
    name = settings.fileName()
    assert name.startswith(prefix)
    path = name[len(prefix):] + "\\FileDialog"

    def read_tree(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return None
        with key:
            subkeys, values, _ = winreg.QueryInfoKey(key)
            entries = [winreg.EnumValue(key, index) for index in range(values)]
            children = [winreg.EnumKey(key, index) for index in range(subkeys)]
            return sorted(entries), {name: read_tree(path + "\\" + name) for name in children}

    return read_tree(path)


def test_picker_snapshot_restores_exact_values_even_on_failure(tmp_path):
    settings = QSettings(str(tmp_path / "original.ini"), QSettings.IniFormat)
    settings.setValue("FileDialog/history", ["synthetic-original"])
    settings.setValue("FileDialog/existing", 7)
    settings.setValue("unrelated", "preserved")
    settings.sync()
    before = group(settings)
    with (
        pytest.raises(RuntimeError, match="simulated"),
        HELPER.preserved_file_dialog_preferences(settings),
    ):
        settings.setValue("FileDialog/history", ["synthetic-change"])
        settings.remove("FileDialog/existing")
        settings.setValue("FileDialog/new-key", True)
        settings.sync()
        raise RuntimeError("simulated picker failure")
    assert group(settings) == before and settings.value("unrelated") == "preserved"


def test_picker_snapshot_restores_missing_group(tmp_path):
    settings = QSettings(str(tmp_path / "empty.ini"), QSettings.IniFormat)
    settings.setValue("unrelated", "preserved")
    settings.sync()
    assert "FileDialog" not in settings.childGroups()
    with HELPER.preserved_file_dialog_preferences(settings):
        settings.setValue("FileDialog/history", ["synthetic-change"])
        settings.sync()
    assert "FileDialog" not in settings.childGroups() and settings.value("unrelated") == "preserved"


def test_real_picker_font_cancel_and_native_history_restoration(app, tmp_path):
    window = QWidget()
    if getattr(app, "_studio_pilot_configured", False):
        QA._settle_geometry(app, window, normal=False)
    old_font = app.font()
    old_style = app.styleSheet()
    old_tooltip = QToolTip.font()
    old_palette = QPalette(app.palette())
    had_refresh = hasattr(app, "_studio_refresh_appearance")
    old_refresh = getattr(app, "_studio_refresh_appearance", None)
    had_theme_guard = hasattr(app, "_spp_applying_theme")
    old_theme_guard = getattr(app, "_spp_applying_theme", False)
    old_colors = dict(THEMES.active_colors)
    old_settings = getattr(app, "_studio_pilot_settings", None)
    old_key = getattr(app, "_studio_appearance_theme_key", "theme")
    resolved = getattr(app, "_studio_appearance_resolved_font", None)
    old_resolved_font = QFont(resolved) if resolved is not None else None
    history = QSettings(QSettings.NativeFormat, QSettings.UserScope, "QtProject")
    history.setFallbacksEnabled(False)
    before = group(history)
    actual_store_before = native_store_snapshot(history)
    try:
        if not QFontDatabase.families():
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.IniFormat)
        settings.setValue("appearance/font_mode", "custom")
        settings.setValue("appearance/font_family", app.font().family())
        settings.setValue("appearance/font_size_pt", 18)
        APPEARANCE.configure_appearance(app, settings, theme_key="theme")
        THEMES.apply_theme(app)
        assert app.font().pointSizeF() == 18
        window.show()
        destination = tmp_path / "appearance"
        root = destination / "file-dialog-synthetic"
        root.mkdir(parents=True)
        (root / "sentinel.txt").write_bytes(b"unchanged synthetic input")
        surfaces = (
            QAbstractButton,
            QAbstractItemView,
            QComboBox,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMenu,
            QSpinBox,
            QTextEdit,
        )
        report = HELPER.inspect_file_dialog(
            app, window, destination, surfaces, lambda dialog: QA._settle_geometry(app, dialog)
        )
        assert (
            report["qt_owned"]
            and report["canceled"]
            and report["no_selection"]
            and report["qt_preferences_restored"]
            and report["synthetic_files_unchanged"]
            and len(report["text_surfaces"]) >= 8
        )
        assert app.font().pointSizeF() == 18
        if group(history) != before or native_store_snapshot(history) != actual_store_before:
            pytest.fail("Native QtProject picker preferences changed")
        assert (root / "sentinel.txt").read_bytes() == b"unchanged synthetic input"
    finally:
        window.close()
        window.deleteLater()
        APPEARANCE.configure_appearance(app, old_settings, theme_key=old_key)
        if old_resolved_font is not None:
            app._studio_appearance_resolved_font = old_resolved_font
        app.setFont(old_font)
        THEMES.apply_theme(app)
        app.processEvents()
        # Drain the old font-change callback before restoring the caller's exact
        # palette, stylesheet and callback; it otherwise re-applies the theme.
        app.processEvents()
        # Restore even a caller's non-Studio stylesheet without re-entering the
        # installed palette watcher. This is the same guard used by apply_theme.
        app._spp_applying_theme = True
        try:
            app.setPalette(old_palette)
            if app.styleSheet() != old_style:
                app.setStyleSheet(old_style)
        finally:
            if had_theme_guard:
                app._spp_applying_theme = old_theme_guard
            else:
                del app._spp_applying_theme
        THEMES.active_colors.clear()
        THEMES.active_colors.update(old_colors)
        if had_refresh:
            app._studio_refresh_appearance = old_refresh
        elif hasattr(app, "_studio_refresh_appearance"):
            del app._studio_refresh_appearance
        QToolTip.setFont(old_tooltip)
