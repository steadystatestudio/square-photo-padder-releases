"""Custom dialogs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QListView,
    QTreeView,
    QWidget,
)

from .appearance_controls import AppearanceSettingsDialog
from .choice_buttons import AccentCheckBox
from .settings import _settings


class FileFolderDialog(QFileDialog):
    """One dialog that can select image files AND folders together.

    Native dialogs can only do one or the other, so this forces the Qt
    widget dialog (which matches the app's Fusion + stylesheet look) and
    rewires the Open button to accept whatever mix is highlighted. Relies
    on QFileDialog's internal child names ("listView"/"treeView"); every
    lookup is guarded so a future Qt change degrades to plain file picking.
    """

    def __init__(self, parent=None, caption: str = "Select Images or Folders", directory: str = "") -> None:
        super().__init__(parent, caption, directory)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setFileMode(QFileDialog.FileMode.ExistingFiles)
        self.setNameFilter("Images (*.jpg *.jpeg *.png *.webp);;All files (*)")
        self._selected: list[Path] = []

        for view in (
            self.findChild(QListView, "listView"),
            self.findChild(QTreeView, "treeView"),
        ):
            if view is not None:
                view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        button_box = self.findChild(QDialogButtonBox)
        open_btn = button_box.button(QDialogButtonBox.StandardButton.Open) if button_box else None
        if open_btn is not None:
            try:
                open_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            open_btn.clicked.connect(self.accept)
            # QFileDialog disables/repurposes Open while a folder is
            # highlighted; keep it usable for mixed selections.
            self.currentChanged.connect(lambda _: open_btn.setEnabled(True))

    def accept(self) -> None:
        """Collect mixed selections for Open, Enter, and file double-clicks alike."""
        paths: list[Path] = []
        view = self.findChild(QListView, "listView")
        selection_model = view.selectionModel() if view is not None else None
        if selection_model is not None:
            for index in selection_model.selectedIndexes():
                if index.column() != 0:
                    continue
                path = Path(self.directory().filePath(index.data()))
                if path.exists():
                    paths.append(path)
        if not paths:
            paths = [Path(name) for name in self.selectedFiles() if Path(name).exists()]
        self._selected = paths
        if paths:
            self.done(QDialog.DialogCode.Accepted)

    def selected_paths(self) -> list[Path]:
        return list(self._selected)


class SettingsDialog(AppearanceSettingsDialog):
    """Fitted staged appearance and tooltip preferences."""

    def __init__(
        self, parent: QWidget | None = None, tooltips_enabled: bool = True, appearance: str = "system",
    ) -> None:
        from .themes import apply_theme
        super().__init__(_settings(), parent, theme_key="ui/appearance",
                         apply_callback=lambda: apply_theme(QApplication.instance()))
        self.appearance = self.controls.theme
        self.appearance.setCurrentIndex(max(0, self.appearance.findData(appearance)))
        self.tooltips_check = AccentCheckBox("Show tooltips")
        self.tooltips_check.setChecked(tooltips_enabled)
        self.content_layout.addWidget(self.tooltips_check)
