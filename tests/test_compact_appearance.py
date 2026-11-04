from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPushButton

from photocropper.appearance import configure_appearance
from photocropper.choice_buttons import AccentCheckBox
from photocropper.color_picker import BackgroundColorDialog
from photocropper.dialogs import SettingsDialog
from photocropper.gui import MainWindow
from photocropper.themes import apply_theme


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    for scope in (QSettings.UserScope, QSettings.SystemScope):
        QSettings.setPath(QSettings.IniFormat, scope, str(tmp_path if scope == QSettings.UserScope
                                                       else tmp_path / "system"))
    w = MainWindow()
    screen = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 3440, 1392),
                             availableGeometryChanged=app.primaryScreen().availableGeometryChanged)
    monkeypatch.setattr(w, "screen", lambda: screen)
    w.show()
    QTest.qWait(80)
    yield app, w
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_saved_large_font_reaches_preview_controls_settings_and_themes(window):
    app, w = window
    settings = w.appearance_settings
    settings.setValue("appearance/font_mode", "custom")
    settings.setValue("appearance/font_family", app.font().family())
    settings.setValue("appearance/font_size_pt", 18)
    settings.setValue("appearance/accent_mode", "custom")
    settings.setValue("appearance/accent", "#d34f91")
    for theme in ("light", "dark", "system"):
        settings.setValue("ui/appearance", theme)
        configure_appearance(app, settings, theme_key="ui/appearance")
        apply_theme(app)
        QTest.qWait(40)
        for widget in (w.add_btn, w.process_btn, w.status_label, w.overwrite_check, w.watermark_input):
            assert widget.font().pointSizeF() == 18
        assert app._studio_appearance_values["accent"] == "#d34f91"
    dialog = SettingsDialog(w)
    dialog.show()
    app.processEvents()
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog.controls.font_size.value() == 18
    assert isinstance(dialog.tooltips_check, AccentCheckBox)
    assert not any("copy appearance" in button.text().lower() for button in dialog.findChildren(QPushButton))
    dialog.reject()


def test_accent_overwrite_retains_checkbox_keyboard_and_safety_default(window):
    app, w = window
    assert isinstance(w.overwrite_check, QCheckBox)
    assert not w.overwrite_check.isChecked()
    w.overwrite_check.setFocus()
    QTest.keyClick(w.overwrite_check, Qt.Key_Space)
    assert w.overwrite_check.isChecked()
    QTest.keyClick(w.overwrite_check, Qt.Key_Space)
    assert not w.overwrite_check.isChecked()


def test_background_form_fits_and_only_scrolls_when_monitor_cannot_fit(window, monkeypatch):
    app, w = window
    dialog = BackgroundColorDialog(w, initial=(255, 255, 255))
    dialog.show()
    app.processEvents()
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog._scroll.verticalScrollBar().maximum() == 0
    assert len(dialog.findChildren(QLineEdit)) == 1
    small = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 640, 240))
    monkeypatch.setattr(dialog, "screen", lambda: small)
    dialog._fit_form()
    app.processEvents()
    assert dialog.width() <= 592 and dialog.height() <= 160
    assert dialog._scroll.verticalScrollBar().maximum() > 0
    dialog._scroll.ensureWidgetVisible(dialog.use_btn)
    app.processEvents()
    bounds = QRect(dialog.use_btn.mapTo(dialog._scroll.viewport(), QPoint()), dialog.use_btn.size())
    assert dialog._scroll.viewport().rect().intersects(bounds)
    dialog.reject()
