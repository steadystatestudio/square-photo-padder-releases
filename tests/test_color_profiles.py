"""Reference color conversion through preview and actual JPEG publication."""
import io
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from photocropper.processor import ProcessingOptions, generate_preview, process_image, process_images

PROFILES = Path(__file__).parent / "fixtures" / "icc"


@pytest.mark.parametrize("mode,pixel,filename,profile_name", [
    ("CMYK", (70, 40, 10, 0), "cmyk.jpg", "CGATS001Compat-v2-micro.icc"),
    ("RGB", (180, 100, 90), "wide-gamut.png", "DisplayP3-v4.icc"),
])
def test_tagged_color_matches_reference_in_preview_and_saved_jpeg(tmp_path, mode, pixel, filename, profile_name):
    path = tmp_path / filename
    profile = (PROFILES / profile_name).read_bytes()
    with Image.new(mode, (80, 40), pixel) as source:
        source.save(path, icc_profile=profile)
    before = path.read_bytes()
    with Image.open(path) as source:
        with ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                       ImageCms.createProfile("sRGB"), outputMode="RGB") as reference:
            expected = reference.getpixel((40, 20))
        with source.convert("RGB") as naive:
            assert max(abs(a - b) for a, b in zip(expected, naive.getpixel((40, 20)))) >= 5
    options = ProcessingOptions(background_color=(20, 60, 100))
    with generate_preview(path, options) as preview:
        assert preview.getpixel((40, 40)) == expected
        assert preview.getpixel((40, 2)) == options.background_color
    result = process_image(path, options)
    assert result.success, result.error
    with Image.open(result.destination_path) as saved:
        assert saved.size == (80, 80)
        assert max(abs(a - b) for a, b in zip(saved.getpixel((40, 40)), expected)) <= 2
        assert not saved.getexif()
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode,pixel,profile_name", [
    ("RGBA", (180, 100, 90, 128), "DisplayP3-v4.icc"),
    ("LA", (80, 128), "sGrey-v4.icc"),
])
def test_profiled_alpha_is_preserved_after_conversion(tmp_path, mode, pixel, profile_name):
    path = tmp_path / "alpha.png"
    profile = (PROFILES / profile_name).read_bytes()
    background = (20, 60, 100)
    with Image.new(mode, (60, 40), pixel) as source:
        source.save(path, icc_profile=profile)
        with source.convert("L" if mode == "LA" else "RGB") as color:
            with ImageCms.profileToProfile(color, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                           ImageCms.createProfile("sRGB"), outputMode="RGB") as managed:
                with Image.new("RGB", managed.size, background) as composite, source.getchannel("A") as alpha:
                    composite.paste(managed, mask=alpha)
                    expected = composite.getpixel((30, 20))
    options = ProcessingOptions(background_color=background)
    with generate_preview(path, options) as preview:
        assert preview.getpixel((30, 30)) == expected
    result = process_image(path, options)
    assert result.success, result.error
    with Image.open(result.destination_path) as saved:
        assert max(abs(a - b) for a, b in zip(saved.getpixel((30, 30)), expected)) <= 2


def test_mismatched_profile_fails_one_file_without_changing_inputs(tmp_path):
    bad, good = tmp_path / "bad.png", tmp_path / "good.jpg"
    with Image.new("RGB", (60, 40), "red") as image:
        image.save(bad, icc_profile=(PROFILES / "CGATS001Compat-v2-micro.icc").read_bytes())
        image.save(good)
    originals = {path: path.read_bytes() for path in (bad, good)}
    batch = process_images([bad, good])
    assert batch.failure_count == batch.success_count == 1
    assert "color profile" in batch.results[0].error
    assert not (tmp_path / "bad (1).jpg").exists()
    assert (tmp_path / "good (1).jpg").is_file()
    assert all(path.read_bytes() == value for path, value in originals.items())
