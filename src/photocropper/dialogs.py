"""Custom dialogs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLayout,
    QListView,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


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


class SettingsDialog(QDialog):
    """App preferences committed by Save and discarded by Cancel."""

    def __init__(
        self, parent: QWidget | None = None, tooltips_enabled: bool = True, appearance: str = "system",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self.tooltips_check = QCheckBox("Show tooltips")
        self.tooltips_check.setChecked(tooltips_enabled)
        self.appearance = QComboBox()
        for label, value in (("System", "system"), ("Dark", "dark"), ("Light", "light")):
            self.appearance.addItem(label, value)
        self.appearance.setCurrentIndex(self.appearance.findData(appearance))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Appearance"))
        layout.addWidget(self.appearance)
        layout.addWidget(self.tooltips_check)
        layout.addWidget(buttons)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
