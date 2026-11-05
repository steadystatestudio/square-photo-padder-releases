"""Queued custom-color layout work belongs to the dialog's native lifetime."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from photocropper import color_picker


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app, monkeypatch):
    monkeypatch.setattr(color_picker, "load_custom_colors", lambda: [(10, 20, 30)])
    saved = []
    monkeypatch.setattr(color_picker, "save_custom_colors", lambda colors: saved.append(list(colors)))
    callbacks = []

    class ObservedDialog(color_picker.BackgroundColorDialog):
        def _fit_form(self):
            callbacks.append(isValid(self))
            if isValid(self):
                super()._fit_form()

    window = ObservedDialog()
    app.processEvents()
    assert callbacks and all(callbacks), "Initial fitting must actually execute"
    yield window, callbacks, saved
    if isValid(window):
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.parametrize("operation", ["rebuild", "clear"])
def test_queued_custom_color_refit_cannot_outlive_dialog(app, dialog, operation):
    window, callbacks, saved = dialog
    before = len(callbacks)
    if operation == "clear":
        window._clear_custom_colors()
        assert saved == [[]]
    else:
        window._rebuild_custom_row()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(window), "The regression must delete the native dialog before draining its queued work"
    app.processEvents()
    QTest.qWait(20)
    assert callbacks[before:] == [], "A queued fit must be cancelled with the dialog, not called on a dead wrapper"


def test_live_custom_color_rebuilds_still_refit_and_coalesce(app, dialog):
    window, callbacks, saved = dialog
    before = len(callbacks)
    window._clear_custom_colors()
    window._rebuild_custom_row()
    window._rebuild_custom_row()
    assert saved == [[]] and window._custom_swatches == [] and window._custom_row.isHidden()
    app.processEvents()
    assert callbacks[before:] == [True], "Live rebuilds must still fit once with current content"
    assert window.width() > 0 and window.height() > 0
