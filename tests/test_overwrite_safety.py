"""Overwrite replaces originals: it must be confirmed, consistent and keep permissions."""
import os
import stat
from pathlib import Path

import pytest
from PIL import Image

from photocropper.processor import ProcessingOptions, output_path_for, process_image, replaces_source


def keeps_permissions(folder):
    """FAT and exFAT mounts have no permission bits to check."""
    sample = folder / "permission-probe"
    sample.write_bytes(b"")
    sample.chmod(0o600)
    kept = stat.S_IMODE(sample.stat().st_mode) == 0o600
    sample.unlink()
    return kept


def photo(path: Path, size=(40, 20)) -> Path:
    Image.new("RGB", size, "red").save(path, "JPEG")
    return path


@pytest.mark.parametrize("name", ["IMG_001.JPG", "IMG_001.jpg", "IMG_001.Jpg"])
def test_overwrite_replaces_a_jpg_source_whatever_its_letter_case(tmp_path, name):
    source = photo(tmp_path / name)
    assert replaces_source(source) and output_path_for(source, overwrite=True) == source
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert result.success, result.error
    assert [path.name for path in tmp_path.iterdir()] == [name]
    with Image.open(source) as image:
        assert image.width == image.height


@pytest.mark.parametrize("name", ["scan.jpeg", "scan.png"])
def test_overwrite_keeps_other_originals_and_saves_a_copy(tmp_path, name):
    source = tmp_path / name
    Image.new("RGB", (40, 20), "red").save(source)
    before = source.read_bytes()
    assert not replaces_source(source)
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert result.success, result.error
    assert source.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([name, "scan.jpg"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_copies_get_ordinary_permissions_and_replacements_keep_the_originals(tmp_path):
    if not keeps_permissions(tmp_path):
        pytest.skip("filesystem has no permission bits")
    previous = os.umask(0o022)
    try:
        source = photo(tmp_path / "a.jpg")
        copy = process_image(source, ProcessingOptions())
        assert stat.S_IMODE(copy.destination_path.stat().st_mode) == 0o644
        source.chmod(0o664)
        replaced = process_image(source, ProcessingOptions(overwrite=True))
        assert replaced.success and stat.S_IMODE(source.stat().st_mode) == 0o664
    finally:
        os.umask(previous)


def test_declining_the_confirmation_changes_nothing(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from photocropper import gui

    app = QApplication.instance() or QApplication([])
    asked = []
    monkeypatch.setattr(gui.MainWindow, "_confirm_replace_originals",
                        lambda self, count: asked.append(count) or False)
    source, other = photo(tmp_path / "a.JPG"), tmp_path / "b.png"
    Image.new("RGB", (40, 20), "blue").save(other)
    before = source.read_bytes()
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    window = gui.MainWindow()
    try:
        window.overwrite_check.setChecked(True)
        batch = window.process_paths([source, other])
        assert asked == [1] and not batch.results
        assert source.read_bytes() == before
        assert sorted(path.name for path in tmp_path.iterdir() if path.is_file()) == ["a.JPG", "b.png"]
        asked.clear()
        window.overwrite_check.setChecked(False)
        window.process_paths([source])
        assert not asked and source.read_bytes() == before
    finally:
        window.close()
        app.processEvents()
