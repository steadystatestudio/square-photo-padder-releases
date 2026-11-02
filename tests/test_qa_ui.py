"""The internal interactive check mode changes only the settings destination."""
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtCore import QSettings

from photocropper import app


def test_fresh_qa_destination_isolates_user_and_system_ini_paths(tmp_path):
    target = tmp_path / "fresh"
    with patch.object(app.QSettings, "setPath") as setting_path:
        app._isolate_qa_settings(str(target))
    assert target.is_dir() and list(target.iterdir()) == []
    assert setting_path.call_args_list == [
        call(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(target / "settings")),
        call(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(target / "system-settings")),
    ]


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_qa_destination_is_never_modified(tmp_path, kind):
    target = tmp_path / "existing"
    if kind == "directory":
        target.mkdir()
        sentinel = target / "keep.txt"
    else:
        sentinel = target
    sentinel.write_bytes(b"original content")
    with patch.object(app.QSettings, "setPath") as setting_path:
        with pytest.raises(FileExistsError):
            app._isolate_qa_settings(str(target))
    setting_path.assert_not_called()
    assert sentinel.read_bytes() == b"original content"


def test_symlink_qa_destination_is_rejected_before_directory_creation(tmp_path):
    target = tmp_path / "link"
    original = Path.is_symlink
    with patch.object(Path, "is_symlink", lambda path: path == target or original(path)):
        with patch.object(app.QSettings, "setPath") as setting_path:
            with pytest.raises(ValueError, match="links"):
                app._isolate_qa_settings(str(target))
    setting_path.assert_not_called()
    assert not target.exists()


@pytest.mark.parametrize("arguments", [["--qa-ui"], ["--qa-ui", "folder", "extra"], ["extra", "--qa-ui", "folder"]])
def test_malformed_qa_cli_never_opens_the_app(monkeypatch, arguments):
    monkeypatch.setattr(app.sys, "argv", ["padder", *arguments])
    with patch.object(app, "MainWindow") as window, patch.object(app, "_isolate_qa_settings") as isolate:
        assert app.main() == 2
    window.assert_not_called()
    isolate.assert_not_called()


def test_existing_qa_cli_destination_refuses_before_app_start(tmp_path, monkeypatch):
    monkeypatch.setattr(app.sys, "argv", ["padder", "--qa-ui", str(tmp_path)])
    with patch.object(app, "MainWindow") as window:
        assert app.main() == 2
    window.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("qa_mode", [False, True])
def test_normal_window_and_event_loop_are_used_without_automatic_actions(tmp_path, monkeypatch, qa_mode):
    target = tmp_path / "fresh"
    arguments = ["padder", "--qa-ui", str(target)] if qa_mode else ["padder"]
    monkeypatch.setattr(app.sys, "argv", arguments)
    application = MagicMock()
    application.exec.return_value = 17
    with (patch.object(app, "QApplication") as application_class,
          patch.object(app, "MainWindow") as window_class,
          patch.object(app, "_isolate_qa_settings") as isolate,
          patch.object(app, "apply_theme"), patch.object(app, "install_theme_watcher"),
          patch.object(app, "_load_app_icon")):
        application_class.instance.return_value = application
        assert app.main() == 17
    assert window_class.return_value.method_calls == [("show", (), {})]
    application.exec.assert_called_once_with()
    if qa_mode:
        isolate.assert_called_once_with(str(target))
    else:
        isolate.assert_not_called()
