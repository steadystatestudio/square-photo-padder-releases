from pathlib import Path

import pytest
from PIL import Image

from photocropper import processor
from photocropper.processor import ProcessingOptions, process_image


def test_failed_overwrite_preserves_original(tmp_path, monkeypatch):
    source = tmp_path / 'photo.jpg'
    Image.new('RGB', (30, 20), 'red').save(source)
    before = source.read_bytes()

    def failed_save(self, target, **kwargs):
        if hasattr(target, 'write'):
            target.write(b'partial JPEG')
        else:
            Path(target).write_bytes(b'partial JPEG')
        raise OSError('Disk full')

    monkeypatch.setattr(Image.Image, 'save', failed_save)
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert not result.success
    assert source.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['photo.jpg']


def test_non_overwrite_destination_race_preserves_other_file(tmp_path, monkeypatch):
    source = tmp_path / 'photo.png'
    Image.new('RGB', (30, 20), 'red').save(source)
    raced = tmp_path / 'photo (1).jpg'
    original_render = processor._render_square_padded_image

    def render(*args):
        raced.write_bytes(b'another program created this')
        return original_render(*args)

    monkeypatch.setattr(processor, '_render_square_padded_image', render)
    result = process_image(source)
    assert result.success, result.error
    assert raced.read_bytes() == b'another program created this'
    assert result.destination_path == tmp_path / 'photo (2).jpg'


def test_dangling_link_is_not_a_free_output_name(tmp_path):
    source = tmp_path / 'photo.png'
    Image.new('RGB', (30, 20), 'red').save(source)
    linked = tmp_path / 'photo (1).jpg'
    absent = tmp_path / 'not-created.jpg'
    try:
        linked.symlink_to(absent)
    except OSError:
        pytest.skip("This filesystem or account cannot create symbolic links")
    result = process_image(source)
    assert result.success, result.error
    assert linked.is_symlink() and not absent.exists()
    assert result.destination_path == tmp_path / 'photo (2).jpg'


def test_failed_non_overwrite_leaves_no_partial_copy(tmp_path, monkeypatch):
    source = tmp_path / 'photo.png'
    Image.new('RGB', (30, 20), 'red').save(source)
    before = source.read_bytes()

    def failed_save(self, target, **kwargs):
        target.write(b'partial')
        raise OSError('Disk full')

    monkeypatch.setattr(Image.Image, 'save', failed_save)
    assert not process_image(source).success
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_publication_failure_preserves_source_and_cleans_temporary(tmp_path, monkeypatch):
    source = tmp_path / 'photo.jpg'
    Image.new('RGB', (30, 20), 'red').save(source)
    before = source.read_bytes()

    def denied(*args):
        raise PermissionError('Folder is read only')

    monkeypatch.setattr(processor.os, 'replace', denied)
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert not result.success and 'read only' in result.error
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_persistent_destination_race_stops_cleanly(tmp_path, monkeypatch):
    source = tmp_path / 'photo.png'
    Image.new('RGB', (30, 20), 'red').save(source)
    attempts = []

    def occupied(*args):
        attempts.append(1)
        raise FileExistsError('Concurrent writer')

    monkeypatch.setattr(processor, '_publish_no_replace', occupied)
    result = process_image(source)
    assert not result.success and 'keep changing' in result.error
    assert len(attempts) == 100
    assert list(tmp_path.iterdir()) == [source]


def test_overwrite_does_not_modify_other_hardlinks(tmp_path):
    source = tmp_path / 'photo.jpg'
    Image.new('RGB', (30, 20), 'red').save(source)
    original = source.read_bytes()
    linked = tmp_path / 'other.jpg'
    try:
        linked.hardlink_to(source)
    except OSError:
        pytest.skip("This filesystem cannot create hard links")
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert result.success, result.error
    assert linked.read_bytes() == original
    with Image.open(source) as saved:
        assert saved.size == (30, 30)


def test_overwrite_non_jpeg_never_replaces_neighboring_original(tmp_path):
    source = tmp_path / 'photo.png'
    neighbor = tmp_path / 'photo.jpg'
    Image.new('RGB', (30, 20), 'red').save(source)
    Image.new('RGB', (40, 20), 'blue').save(neighbor)
    original_png, original_jpg = source.read_bytes(), neighbor.read_bytes()
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert result.success, result.error
    assert source.read_bytes() == original_png
    assert neighbor.read_bytes() == original_jpg
    assert result.destination_path == tmp_path / 'photo (1).jpg'


def test_oversized_image_does_not_abort_remaining_batch(tmp_path, monkeypatch):
    blocked = tmp_path / 'huge.jpg'
    valid = tmp_path / 'small.jpg'
    Image.new('RGB', (30, 20), 'red').save(blocked)
    Image.new('RGB', (30, 20), 'blue').save(valid)
    open_image = Image.open

    def checked_open(path, *args, **kwargs):
        if Path(path) == blocked:
            raise Image.DecompressionBombError('Image exceeds safe pixel limit')
        return open_image(path, *args, **kwargs)

    monkeypatch.setattr(Image, 'open', checked_open)
    batch = processor.process_images([blocked, valid])
    assert batch.failure_count == 1 and batch.success_count == 1
    assert 'pixel limit' in batch.results[0].error


@pytest.mark.parametrize("change", ["edit", "replace", "remove"])
def test_source_changed_during_encoding_is_not_overwritten(tmp_path, monkeypatch, change):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (30, 20), "red").save(source)
    replacement = b"another application changed this photo"
    save = Image.Image.save

    def changing_save(self, target, **kwargs):
        save(self, target, **kwargs)
        if change in {"replace", "remove"}:
            source.unlink()
        if change != "remove":
            source.write_bytes(replacement)

    monkeypatch.setattr(Image.Image, "save", changing_save)
    result = process_image(source, ProcessingOptions(overwrite=True))
    assert not result.success
    if change == "remove":
        assert not source.exists()
    else:
        assert "Source changed" in result.error
        assert source.read_bytes() == replacement
    assert not list(tmp_path.glob(".square-photo-padder-*"))
