"""Regression checks for useful minimum windows and monitor changes."""
from types import SimpleNamespace

import pytest
from photocropper.gui import MainWindow
from PySide6.QtCore import QEvent, QRect, QSettings, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def sized_window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    previous_font = app.font()
    previous_style = app.styleSheet()
    app.setFont(QFont("Segoe UI", 9))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    for scope in (QSettings.UserScope, QSettings.SystemScope):
        QSettings.setPath(QSettings.IniFormat, scope, str(tmp_path if scope == QSettings.UserScope
                                                       else tmp_path / "system"))
    window = MainWindow()
    area = [QRect(0, 0, 3440, 1392)]
    screen = SimpleNamespace(availableGeometry=lambda: area[0],
                             availableGeometryChanged=app.primaryScreen().availableGeometryChanged)
    monkeypatch.setattr(window, "screen", lambda: screen)
    window.show()
    QTest.qWait(50)
    yield window, area
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.setFont(previous_font)
    app.setStyleSheet(previous_style)


def test_dragging_smaller_keeps_complete_workspace(sized_window):
    window, _ = sized_window
    window.resize(1, 1)
    QTest.qWait(80)
    assert window.width() >= 560
    assert window.height() >= 640
    scroll = getattr(window, "work_scroll", None)
    if scroll is not None:
        assert scroll.horizontalScrollBar().maximum() == 0
        assert scroll.verticalScrollBar().maximum() == 0
    assert window.size() == window.minimumSize()


def test_smaller_monitor_caps_minimum_then_restores_it(sized_window):
    window, area = sized_window
    normal = window.minimumSize()
    original_font = window.font()
    area[0] = QRect(0, 0, 800, 600)
    window.window_size_guard.update()
    QTest.qWait(80)
    assert window.frameGeometry().width() <= 800
    assert window.frameGeometry().height() <= 600
    assert window.font() == original_font
    area[0] = QRect(0, 0, 3440, 1392)
    window.window_size_guard.update()
    QTest.qWait(80)
    assert window.minimumWidth() >= normal.width()
    assert window.minimumHeight() >= normal.height()


def test_larger_font_grows_minimum_without_shrinking_text(sized_window):
    window, _ = sized_window
    before = window.minimumSize()
    from photocropper.appearance import configure_appearance
    from photocropper.themes import apply_theme
    settings = window.appearance_settings
    settings.setValue("appearance/font_mode", "custom")
    settings.setValue("appearance/font_family", window.font().family())
    settings.setValue("appearance/font_size_pt", 18)
    configure_appearance(QApplication.instance(), settings)
    apply_theme(QApplication.instance())
    QTest.qWait(80)
    assert window.font().pointSize() == 18
    assert window.minimumWidth() > before.width()
    assert window.minimumHeight() > before.height()


@pytest.mark.parametrize("state", [Qt.WindowMaximized, Qt.WindowFullScreen, Qt.WindowMinimized])
def test_legacy_fit_callbacks_leave_compositor_window_states_alone(sized_window, monkeypatch, state):
    window, _ = sized_window
    window.setWindowState(state)
    calls = []
    monkeypatch.setattr(window.window_size_guard, "update", lambda *args: calls.append("guard"))
    monkeypatch.setattr(window, "resize", lambda *args: calls.append("resize"))
    monkeypatch.setattr(window, "move", lambda *args: calls.append("move"))
    window._fit_to_screen()
    window._fit_to_available_geometry(QRect(0, 0, 800, 600))
    window._center_on_screen()
    assert calls == []
