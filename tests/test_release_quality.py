from pathlib import Path

import pytest
from PIL import Image, ImageCms, ImageOps

from photocropper import processor
from photocropper.processor import ProcessingOptions, ResizeSetting, generate_preview, process_image, process_images


@pytest.mark.parametrize('mode', ['RGBA', 'LA', 'P', 'RGB'])
def test_transparency_composites_over_selected_background(tmp_path, mode):
    path = tmp_path / 'transparent.png'
    if mode == 'RGBA':
        image = Image.new(mode, (20, 10), (255, 0, 0, 0))
    elif mode == 'LA':
        image = Image.new(mode, (20, 10), (100, 0))
    elif mode == 'P':
        image = Image.new(mode, (20, 10), 0)
        image.info['transparency'] = 0
    else:
        image = Image.new(mode, (20, 10), (255, 0, 0))
        image.info['transparency'] = (255, 0, 0)
    image.save(path)
    options = ProcessingOptions(background_color=(30, 150, 210))
    preview = generate_preview(path, options)
    assert preview.getpixel((10, 10)) == options.background_color
    result = process_image(path, options)
    assert result.success
    with Image.open(result.destination_path) as saved:
        assert max(abs(a-b) for a, b in zip(saved.getpixel((10, 10)), options.background_color)) <= 2


def test_partial_alpha_is_blended(tmp_path):
    path = tmp_path / 'alpha.webp'
    Image.new('RGBA', (12, 8), (255, 0, 0, 128)).save(path, lossless=True)
    preview = generate_preview(path, ProcessingOptions(background_color=(0, 0, 255)))
    assert preview.getpixel((6, 6)) == (128, 0, 127)


@pytest.mark.parametrize('orientation', range(1, 9))
def test_exif_orientation_and_metadata_privacy(tmp_path, orientation):
    path = tmp_path / 'oriented.jpg'
    original = Image.new('RGB', (40, 20), 'red')
    original.paste('blue', (20, 0, 40, 20))
    exif = Image.Exif()
    exif[274] = orientation
    exif[315] = 'PRIVATE AUTHOR'
    original.save(path, exif=exif)
    with Image.open(path) as opened:
        normalized = ImageOps.exif_transpose(opened).convert('RGB')
        expected = Image.new('RGB', (40, 40), 'black')
        expected.paste(normalized, ((40-normalized.width)//2, (40-normalized.height)//2))
    preview = generate_preview(path, ProcessingOptions())
    assert preview.tobytes() == expected.tobytes()
    result = process_image(path)
    with Image.open(result.destination_path) as output:
        assert not output.getexif()


def test_valid_srgb_profile_and_alpha(tmp_path):
    path = tmp_path / 'profile.png'
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.new('RGBA', (20, 10), (255, 0, 0, 128)).save(path, icc_profile=profile)
    preview = generate_preview(path, ProcessingOptions(background_color=(0, 0, 255)))
    assert preview.getpixel((10, 10)) == (128, 0, 127)
    assert process_image(path).success


def test_bad_profile_is_per_file_and_preserves_source(tmp_path):
    path = tmp_path / 'bad.png'
    good = tmp_path / 'good.jpg'
    Image.new('RGB', (20, 10), 'red').save(path, icc_profile=b'broken profile')
    Image.new('RGB', (20, 10), 'green').save(good)
    before = path.read_bytes()
    batch = process_images([path, good])
    assert batch.failure_count == batch.success_count == 1
    assert 'sRGB' in batch.results[0].error
    assert path.read_bytes() == before


def test_allocation_failure_does_not_abort_batch(tmp_path, monkeypatch):
    paths = [tmp_path / f'{i}.jpg' for i in range(2)]
    for path in paths:
        Image.new('RGB', (20, 10), 'red').save(path)
    render = processor._render_square_padded_image
    calls = []
    def failing(image, options):
        calls.append(1)
        if len(calls) == 1:
            raise MemoryError()
        return render(image, options)
    monkeypatch.setattr(processor, '_render_square_padded_image', failing)
    batch = process_images(paths)
    assert batch.failure_count == batch.success_count == 1
    assert batch.results[0].error == 'MemoryError'


def test_panorama_resizes_before_square_allocation(monkeypatch):
    image = Image.new('RGB', (9000, 1), 'red')
    with pytest.raises(ValueError, match='Square image too large'):
        processor._render_square_padded_image(image, ProcessingOptions())
    rendered = processor._render_square_padded_image(image, ProcessingOptions(resize=ResizeSetting.preset(1000)))
    assert rendered.size == (1000, 1000)


def test_source_limit_checked_before_decode(monkeypatch):
    image = Image.new('RGB', (10, 10), 'red')
    monkeypatch.setattr(processor, 'MAX_SOURCE_PIXELS', 99)
    with pytest.raises(ValueError, match='source pixels'):
        processor._render_square_padded_image(image, ProcessingOptions())


def test_cancel_between_files_leaves_remaining_untouched(tmp_path):
    paths = [tmp_path / f'{i}.jpg' for i in range(3)]
    for path in paths:
        Image.new('RGB', (20, 10), 'red').save(path)
    completed = []
    batch = process_images(paths, progress=lambda *args: completed.append(args), cancelled=lambda: bool(completed))
    assert batch.cancelled and batch.success_count == 1
    assert not (tmp_path / '1 (1).jpg').exists()


def test_zero_width_watermark_does_not_abort(tmp_path):
    path = tmp_path / 'a.jpg'
    Image.new('RGB', (30, 20), 'red').save(path)
    result = process_image(path, ProcessingOptions(watermark_text='\u200b', watermark_position='tiled'))
    assert result.success, result.error


def test_version_consistent():
    import tomllib

    from photocropper.constants import APP_VERSION
    root = Path(__file__).resolve().parents[1]
    assert APP_VERSION == tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    assert f"'ProductVersion', '{APP_VERSION}'" in (root / 'packaging/windows/version.txt').read_text()
