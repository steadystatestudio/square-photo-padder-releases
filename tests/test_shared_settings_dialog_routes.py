"""Real shared dialog Save/Cancel routes must preserve staged settings."""

import importlib
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QToolTip, QWidget

SOURCE = next((Path(__file__).parents[1] / "src").glob("*/appearance_controls.py")).parent
CONTROLS = importlib.import_module(SOURCE.name + ".appearance_controls")
APPEARANCE = importlib.import_module(SOURCE.name + ".appearance")
QA = importlib.import_module(SOURCE.name + ".appearance_qa")
THEMES = importlib.import_module(SOURCE.name + ".themes")


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance() or QApplication([])
    return instance


@pytest.fixture
def staged_dialog(app, tmp_path, monkeypatch):
    parent = QWidget()
    if getattr(app, "_studio_pilot_configured", False):
        QA._settle_geometry(app, parent, normal=False)
    old_font = app.font()
    old_style = app.styleSheet()
    old_palette, old_tooltip = QPalette(app.palette()), QFont(QToolTip.font())
    had_refresh = hasattr(app, "_studio_refresh_appearance")
    old_refresh = getattr(app, "_studio_refresh_appearance", None)
    had_guard = hasattr(app, "_spp_applying_theme")
    old_guard = getattr(app, "_spp_applying_theme", False)
    old_colors = dict(THEMES.active_colors)
    old_settings = getattr(app, "_studio_pilot_settings", None)
    old_key = getattr(app, "_studio_appearance_theme_key", "theme")
    resolved = getattr(app, "_studio_appearance_resolved_font", None)
    old_resolved = QFont(resolved) if resolved is not None else None
    monkeypatch.setattr(
        APPEARANCE,
        "_start_native",
        lambda app, generation: APPEARANCE._provider_finished(
            app, generation, "gtk", {"reason": "fixture-unavailable"}
        ),
    )
    monkeypatch.setattr(
        APPEARANCE,
        "_start_portal",
        lambda app, generation: APPEARANCE._provider_finished(
            app, generation, "portal", {"reason": "fixture-unavailable"}
        ),
    )
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    settings.setValue("unrelated", "retained")
    dialogs = []
    calls = []

    def create():
        dialog = CONTROLS.AppearanceSettingsDialog(settings, parent, "theme", lambda: calls.append(True))
        dialogs.append(dialog)
        dialog.show()
        QTest.qWait(30)
        return dialog

    yield settings, create, calls
    for dialog in dialogs:
        dialog.close()
        dialog.deleteLater()
    parent.close()
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    APPEARANCE.configure_appearance(app, old_settings, theme_key=old_key)
    if old_resolved is not None:
        app._studio_appearance_resolved_font = old_resolved
    app.setFont(old_font)
    THEMES.apply_theme(app)
    app.processEvents()
    app.processEvents()
    # Padder's palette watcher is synchronous. Restore caller-specific style
    # through the same guard as apply_theme rather than re-entering that watcher.
    app._spp_applying_theme = True
    try:
        app.setPalette(old_palette)
        if app.styleSheet() != old_style:
            app.setStyleSheet(old_style)
    finally:
        if had_guard:
            app._spp_applying_theme = old_guard
        else:
            del app._spp_applying_theme
    THEMES.active_colors.clear()
    THEMES.active_colors.update(old_colors)
    if had_refresh:
        app._studio_refresh_appearance = old_refresh
    elif hasattr(app, "_studio_refresh_appearance"):
        del app._studio_refresh_appearance
    QToolTip.setFont(old_tooltip)


def test_actual_save_button_persists_overrides_and_applies(staged_dialog, app):
    settings, create, calls = staged_dialog
    dialog = create()
    c = dialog.controls
    c.font_mode.setCurrentIndex(c.font_mode.findData("custom"))
    c.font_size.setValue(18)
    c.accent_mode.setCurrentIndex(c.accent_mode.findData("custom"))
    c.accent_color = QColor("#d34f91")
    c.theme.setCurrentIndex(c.theme.findData("dark"))
    dialog.buttons.button(QDialogButtonBox.Save).click()
    QTest.qWait(40)
    assert dialog.result() == QDialog.Accepted and not dialog.isVisible()
    assert (
        settings.value("appearance/font_mode") == "custom"
        and settings.value("appearance/font_size_pt", type=float) == 18
    )
    assert (
        settings.value("appearance/accent_mode") == "custom"
        and settings.value("appearance/accent") == "#d34f91"
        and settings.value("theme") == "dark"
    )
    assert settings.value("unrelated") == "retained" and calls == [True]
    assert app.font().pointSizeF() == 18 and app._studio_appearance_values["accent"] == "#d34f91"


def test_actual_cancel_button_does_not_save_or_apply(staged_dialog):
    settings, create, calls = staged_dialog
    settings.setValue("appearance/font_mode", "custom")
    settings.setValue("appearance/font_size_pt", 12)
    before = {key: settings.value(key) for key in settings.allKeys()}
    dialog = create()
    dialog.controls.font_size.setValue(23)
    dialog.controls.reset_appearance_button.click()
    dialog.buttons.button(QDialogButtonBox.Cancel).click()
    QTest.qWait(30)
    assert dialog.result() == QDialog.Rejected and not dialog.isVisible()
    assert {key: settings.value(key) for key in settings.allKeys()} == before and not calls
