from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QItemSelectionModel, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QListView, QTreeView

from photocropper.dialogs import FileFolderDialog
from photocropper.themes import apply_theme


@pytest.fixture(params=[QFileDialog.ViewMode.List, QFileDialog.ViewMode.Detail])
def picker(request, tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_theme(app)
    photo = tmp_path / "cafÃ© photo.png"
    photo.touch()
    folder = tmp_path / "Photos"
    folder.mkdir()
    dialog = FileFolderDialog(directory=str(tmp_path))
    dialog.setViewMode(request.param)
    dialog.show()
    view_type = QListView if request.param == QFileDialog.ViewMode.List else QTreeView
    view_name = "listView" if request.param == QFileDialog.ViewMode.List else "treeView"
    view = dialog.findChild(view_type, view_name)
    assert view is not None
    for _ in range(100):
        app.processEvents()
        if (view.model().index(str(photo)).isValid() and view.model().index(str(folder)).isValid()
                and not view.visualRect(view.model().index(str(photo))).isEmpty()
                and not view.visualRect(view.model().index(str(folder))).isEmpty()):
            break
        QTest.qWait(10)
    yield app, dialog, view, photo, folder
    dialog.close()
    dialog.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def select(view, path, clear=True):
    index = view.model().index(str(path))
    assert index.isValid()
    flags = QItemSelectionModel.SelectionFlag.Rows | (
        QItemSelectionModel.SelectionFlag.ClearAndSelect if clear else QItemSelectionModel.SelectionFlag.Select
    )
    view.selectionModel().setCurrentIndex(index, flags)
    view.scrollTo(index)
    QTest.qWait(20)
    view.doItemsLayout()
    return view.model().index(str(path))


@pytest.mark.parametrize("gesture", ["double_click", "enter", "open"])
def test_photo_acceptance_returns_selected_path(picker, gesture):
    app, dialog, view, photo, _ = picker
    index = select(view, photo)
    accepted = QSignalSpy(dialog.accepted)
    if gesture == "double_click":
        point = view.visualRect(index).center()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    elif gesture == "enter":
        QTest.keyClick(view, Qt.Key.Key_Return)
    else:
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).click()
    app.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert accepted.count() == 1
    assert dialog.selected_paths() == [photo]


def test_open_accepts_multiple_photos_and_folders(picker):
    app, dialog, view, photo, folder = picker
    second = photo.parent / "second.jpg"
    second.touch()
    for _ in range(100):
        app.processEvents()
        if view.model().index(str(second)).isValid():
            break
        QTest.qWait(10)
    select(view, photo)
    select(view, second, clear=False)
    select(view, folder, clear=False)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert set(dialog.selected_paths()) == {photo, second, folder}


def test_folder_double_click_navigates_without_accepting(picker):
    app, dialog, view, _, folder = picker
    index = select(view, folder)
    accepted = QSignalSpy(dialog.accepted)
    point = view.visualRect(index).center()
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert Path(dialog.directory().absolutePath()) == folder
    assert accepted.count() == 0
    assert dialog.selected_paths() == []
    assert dialog.isVisible()


def test_cancel_does_not_return_highlighted_photo(picker):
    _, dialog, view, photo, _ = picker
    select(view, photo)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.selected_paths() == []


def test_add_photos_loads_a_double_clicked_photo(tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtCore import QSettings

    from photocropper.gui import MainWindow, _settings

    app = QApplication.instance() or QApplication([])
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    photo = tmp_path / "photo.png"
    Image.new("RGB", (50, 30)).save(photo)
    _settings().setValue("browse/last_directory", str(tmp_path))
    window = MainWindow()

    def choose(dialog):
        dialog.show()
        view = dialog.findChild(QListView, "listView")
        for _ in range(100):
            app.processEvents()
            if view.model().index(str(photo)).isValid():
                break
            QTest.qWait(10)
        index = select(view, photo)
        point = view.visualRect(index).center()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        return dialog.result()

    monkeypatch.setattr(FileFolderDialog, "exec", choose)
    try:
        window._browse()
        assert window._preview_paths == [photo]
        assert window._preview_path == photo
        assert _settings().value("browse/last_directory") == str(tmp_path)
        assert window.add_btn.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
