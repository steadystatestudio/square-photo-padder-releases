"""Small photos must retain the complete watermark inside the actual output."""
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from photocropper.processor import ProcessingOptions, _apply_watermark, generate_preview, process_image


@pytest.mark.parametrize("position", ["top-left", "top-right", "center", "bottom-left", "bottom-right"])
def test_short_watermark_and_halo_fit_small_photo(position):
    with Image.new("RGB", (60, 60), (100, 100, 100)) as plain:
        with _apply_watermark(plain, "TEST", "medium", position) as marked:
            with ImageChops.difference(plain, marked) as change:
                bounds = change.getbbox()
                assert bounds is not None
                assert bounds[0] >= 1 and bounds[1] >= 1
                assert bounds[2] <= 59 and bounds[3] <= 59


def test_small_photo_preview_matches_complete_saved_watermark(tmp_path: Path):
    source = tmp_path / "small.png"
    Image.new("RGB", (60, 60), (100, 100, 100)).save(source)
    before = source.read_bytes()
    options = ProcessingOptions(watermark_text="TEST", watermark_position="bottom-right")
    result = process_image(source, options)
    assert result.success, result.error
    with generate_preview(source, options, preview_size=60) as preview:
        with Image.open(result.destination_path) as output:
            assert output.size == (60, 60)
            with ImageChops.difference(preview, output) as difference:
                assert max(ImageStat.Stat(difference).mean) < 4
            for edge in ((0, 0, 60, 1), (0, 59, 60, 60), (0, 0, 1, 60), (59, 0, 60, 60)):
                with output.crop(edge) as border:
                    assert all(abs(value - 100) <= 8 for low_high in border.getextrema() for value in low_high)
    assert source.read_bytes() == before


def test_watermark_that_cannot_fit_reports_error_without_writing(tmp_path: Path):
    source = tmp_path / "tiny.png"
    Image.new("RGB", (4, 4), (100, 100, 100)).save(source)
    before = source.read_bytes()
    result = process_image(source, ProcessingOptions(watermark_text="TEST"))
    assert not result.success
    assert "Watermark text does not fit" in result.error
    assert source.read_bytes() == before
    assert not list(tmp_path.glob("*.jpg"))
