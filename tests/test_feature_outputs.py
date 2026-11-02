"""Readiness gaps: output formats, Unicode names and top-corner watermark pixels."""
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from photocropper.processor import ProcessingOptions, generate_preview, process_image, process_images


@pytest.mark.parametrize("extension", [".jpg", ".jpeg", ".png", ".webp"])
def test_explicit_overwrite_changes_only_jpg_source(tmp_path, extension):
    path = tmp_path / ("café_海岸" + extension)
    with Image.new("RGB", (80, 40), (20, 100, 180)) as image:
        image.save(path)
    before = path.read_bytes()
    result = process_image(path, ProcessingOptions(overwrite=True))
    assert result.success, result.error
    with Image.open(result.destination_path) as output:
        assert output.size == (80, 80) and output.format == "JPEG"
    if extension == ".jpg":
        assert result.destination_path == path and path.read_bytes() != before
    else:
        assert result.destination_path == path.with_suffix(".jpg")
        assert path.read_bytes() == before


def test_unicode_mixed_batch_keeps_collision_and_continues_after_corruption(tmp_path):
    folder = tmp_path / "写真 café"
    folder.mkdir()
    good, bad = folder / "海岸.png", folder / "破損.png"
    with Image.new("RGB", (80, 40), "red") as image:
        image.save(good)
    bad.write_bytes(b"corrupt image")
    occupied = folder / "海岸 (1).jpg"
    occupied.write_bytes(b"unrelated existing file")
    originals = {path: path.read_bytes() for path in (good, bad, occupied)}
    batch = process_images([bad, good])
    assert batch.failure_count == batch.success_count == 1
    assert batch.results[0].error
    assert batch.results[1].destination_path == folder / "海岸 (2).jpg"
    assert all(path.read_bytes() == value for path, value in originals.items())


@pytest.mark.parametrize("position", ["top-left", "top-right"])
@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_top_corner_watermarks_have_visible_ink_only_in_the_selected_corner(tmp_path: Path, position, size):
    source = tmp_path / "photo.png"
    with Image.new("RGB", (800, 800), (100, 100, 100)) as image:
        image.save(source)
    options = ProcessingOptions(watermark_text="TEST", watermark_position=position, watermark_size=size)
    with generate_preview(source, ProcessingOptions(), preview_size=800) as plain:
        with generate_preview(source, options, preview_size=800) as preview:
            with ImageChops.difference(plain, preview) as difference:
                box = difference.getbbox()
                assert box is not None
                assert box[3] < 400
                assert box[2] < 400 if position == "top-left" else box[0] > 400
    result = process_image(source, options)
    assert result.success, result.error
    with Image.open(result.destination_path) as output:
        expected_corner = (0, 0, 400, 400) if position == "top-left" else (400, 0, 800, 400)
        with output.crop(expected_corner) as corner:
            assert max(corner.getextrema()[0]) > 110
        assert max(abs(channel - 100) for channel in output.getpixel((400, 700))) <= 2
