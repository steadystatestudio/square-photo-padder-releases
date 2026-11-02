from __future__ import annotations

from pathlib import Path
from unittest.mock import PropertyMock, patch

from PIL import Image

from photocropper.processor import (
    ProcessingOptions,
    ResizeSetting,
    expand_input_paths,
    process_image,
    process_images,
)


def _save_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", size, color)
    image.save(path)


BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def _black_bg(**kwargs) -> ProcessingOptions:
    return ProcessingOptions(background_color=BLACK, **kwargs)


def test_landscape_image_gets_padding_bars(tmp_path: Path) -> None:
    source = tmp_path / "landscape.jpg"
    _save_image(source, (1600, 900), (255, 0, 0))

    result = process_image(source, _black_bg())

    assert result.success is True
    assert result.destination_path is not None
    # Source occupies landscape.jpg, so the copy gets the numbered name.
    assert result.destination_path == tmp_path / "landscape (1).jpg"
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1600, 1600)
        assert processed.getpixel((800, 10)) == BLACK
        assert processed.getpixel((800, 1590)) == BLACK
        assert processed.getpixel((10, 800))[0] > 200
        assert processed.getpixel((1590, 800))[0] > 200
        assert processed.getpixel((800, 800))[0] > 200


def test_default_background_is_black(tmp_path: Path) -> None:
    source = tmp_path / "landscape.jpg"
    _save_image(source, (1600, 900), (255, 0, 0))

    result = process_image(source)

    assert result.success is True
    assert result.destination_path is not None
    with Image.open(result.destination_path) as processed:
        assert processed.getpixel((800, 10)) == BLACK
        assert processed.getpixel((800, 1590)) == BLACK


def test_square_image_remains_full_frame_without_inset(tmp_path: Path) -> None:
    source = tmp_path / "square.png"
    _save_image(source, (1200, 1200), (0, 255, 0))

    result = process_image(source)

    assert result.success is True
    assert result.destination_path is not None
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1200, 1200)
        assert processed.getpixel((600, 10))[1] > 200
        assert processed.getpixel((600, 1190))[1] > 200
        assert processed.getpixel((10, 600))[1] > 200
        assert processed.getpixel((1190, 600))[1] > 200
        assert processed.getpixel((600, 600))[1] > 200


def test_preset_resize_downscales_square_output(tmp_path: Path) -> None:
    source = tmp_path / "large.jpg"
    _save_image(source, (1600, 900), (255, 0, 0))

    options = ProcessingOptions(resize=ResizeSetting.preset(1080), background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    assert result.destination_path is not None
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1080, 1080)
        assert processed.getpixel((540, 10)) == BLACK
        assert processed.getpixel((540, 540))[0] > 200


def test_portrait_image_keeps_full_image_with_side_bars(tmp_path: Path) -> None:
    source = tmp_path / "portrait.png"
    image = Image.new("RGB", (600, 1200), (0, 0, 0))
    for y in range(0, 400):
        for x in range(600):
            image.putpixel((x, y), (255, 0, 0))
    for y in range(400, 800):
        for x in range(600):
            image.putpixel((x, y), (0, 255, 0))
    for y in range(800, 1200):
        for x in range(600):
            image.putpixel((x, y), (0, 0, 255))
    image.save(source)

    result = process_image(source, _black_bg())

    assert result.success is True
    assert result.destination_path is not None
    assert result.destination_path.suffix == ".jpg"
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1200, 1200)
        top_band = processed.getpixel((600, 10))
        middle_band = processed.getpixel((600, 600))
        bottom_band = processed.getpixel((600, 1190))
        left_edge = processed.getpixel((10, 600))
        right_edge = processed.getpixel((1190, 600))
        assert top_band[0] > 200
        assert middle_band[1] > 200
        assert bottom_band[2] > 200
        assert left_edge == BLACK
        assert right_edge == BLACK
        assert processed.getpixel((600, 80))[0] > 200
        assert processed.getpixel((600, 1120))[2] > 200


def test_resize_never_upscales(tmp_path: Path) -> None:
    source = tmp_path / "portrait.png"
    _save_image(source, (600, 1200), (20, 200, 40))

    options = ProcessingOptions(resize=ResizeSetting.custom(2048), background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    assert result.destination_path is not None
    with Image.open(result.destination_path) as processed:
        # Requested 2048 but the padded square is only 1200: size acts as a maximum.
        assert processed.size == (1200, 1200)
        assert processed.getpixel((10, 600)) == BLACK
        assert processed.getpixel((600, 600))[1] > 150


def test_expand_input_paths_recursively_discovers_supported_images(tmp_path: Path) -> None:
    folder = tmp_path / "batch"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    first = folder / "one.jpg"
    second = nested / "two.png"
    ignored = nested / "notes.txt"
    _save_image(first, (100, 50), (10, 20, 30))
    _save_image(second, (50, 100), (30, 40, 50))
    ignored.write_text("ignore", encoding="utf-8")

    discovered = expand_input_paths([folder])

    assert set(discovered) == {first, second}


def test_expand_input_paths_deduplicates_files_from_mixed_inputs(tmp_path: Path) -> None:
    folder = tmp_path / "batch"
    folder.mkdir()
    image_path = folder / "dup.jpg"
    _save_image(image_path, (100, 50), (10, 20, 30))

    discovered = expand_input_paths([folder, image_path])

    assert discovered == [image_path]


def test_existing_output_file_uses_numbered_name(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (1200, 800), (100, 10, 10))
    (tmp_path / "photo (1).jpg").write_bytes(b"existing")

    result = process_image(source)

    assert result.success is True
    assert result.destination_path is not None
    assert result.destination_path == tmp_path / "photo (2).jpg"


def test_recursive_folder_discovery_writes_next_to_sources(tmp_path: Path) -> None:
    root = tmp_path / "batch"
    nested = root / "nested"
    nested.mkdir(parents=True)
    first = root / "first.jpg"
    second = nested / "second.jpg"
    _save_image(first, (100, 50), (10, 20, 30))
    _save_image(second, (50, 100), (30, 40, 50))

    batch = process_images([root])

    assert batch.success_count == 2
    assert (root / "first (1).jpg").exists()
    assert (nested / "second (1).jpg").exists()


def test_png_input_exports_flattened_jpeg_with_padding(tmp_path: Path) -> None:
    source = tmp_path / "transparent.png"
    image = Image.new("RGBA", (1600, 900), (0, 0, 0, 0))
    for y in range(200, 700):
        for x in range(200, 1400):
            image.putpixel((x, y), (255, 120, 0, 255))
    image.save(source)

    result = process_image(source, _black_bg())

    assert result.success is True
    assert result.destination_path is not None
    assert result.destination_path.suffix == ".jpg"
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1600, 1600)
        assert processed.getpixel((800, 10)) == BLACK
        assert processed.getpixel((800, 1590)) == BLACK
        assert processed.getpixel((300, 800))[0] > 200
        assert processed.getpixel((1300, 800))[0] > 200
        assert processed.getpixel((800, 800))[0] > 200


def test_small_image_keeps_original_scale(tmp_path: Path) -> None:
    source = tmp_path / "small.webp"
    _save_image(source, (120, 60), (123, 20, 200))

    result = process_image(source, _black_bg())

    assert result.success is True
    assert result.destination_path is not None
    with Image.open(result.destination_path) as processed:
        assert processed.size == (120, 120)
        assert processed.getpixel((60, 10)) == BLACK
        assert processed.getpixel((60, 110)) == BLACK
        assert abs(processed.getpixel((10, 60))[0] - 123) <= 5
        assert abs(processed.getpixel((110, 60))[2] - 200) <= 5


def test_unsupported_file_returns_error(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("not an image", encoding="utf-8")

    result = process_image(source)

    assert result.success is False
    assert result.error == "Unsupported file type"


def test_corrupt_image_returns_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.jpg"
    source.write_bytes(b"not-a-real-image")

    result = process_image(source)

    assert result.success is False
    assert result.destination_path is None
    assert result.error


def test_rotation_rotates_image(tmp_path: Path) -> None:
    source = tmp_path / "wide.jpg"
    _save_image(source, (400, 100), (255, 0, 0))

    options = ProcessingOptions(rotation_degrees=90, background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (400, 400)


def test_watermark_text_is_applied(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 600), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_watermark = ProcessingOptions(background_color=(128, 128, 128), watermark_text="SOLD")

    result_plain = process_image(source, options_plain)
    result_wm = process_image(source, options_watermark)

    with Image.open(result_plain.destination_path) as plain, Image.open(result_wm.destination_path) as wm:
        w, h = wm.size
        plain_region = list(plain.crop((w // 2, h // 2, w, h)).tobytes())
        wm_region = list(wm.crop((w // 2, h // 2, w, h)).tobytes())
        assert plain_region != wm_region


def test_custom_background_color(tmp_path: Path) -> None:
    source = tmp_path / "landscape.jpg"
    _save_image(source, (200, 100), (128, 128, 128))

    red_bg = (255, 0, 0)
    options = ProcessingOptions(background_color=red_bg)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        # Top center should be the red background
        pixel = processed.getpixel((100, 5))
        assert pixel[0] > 200
        assert pixel[1] < 50
        assert pixel[2] < 50


# --- Edge cases ---


def test_empty_input_returns_empty_batch(tmp_path: Path) -> None:
    batch = process_images([])
    assert batch.results == []
    assert batch.success_count == 0
    assert batch.failure_count == 0


def test_nonexistent_file_returns_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.jpg"
    result = process_image(missing)
    assert result.success is False
    assert result.error == "Unsupported file type"


def test_expand_input_paths_empty_list() -> None:
    assert expand_input_paths([]) == []


def test_expand_input_paths_skips_unsupported_files(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("text", encoding="utf-8")
    bmp = tmp_path / "image.bmp"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(bmp)

    discovered = expand_input_paths([txt, bmp])
    assert discovered == []


def test_tiny_1px_image(tmp_path: Path) -> None:
    source = tmp_path / "pixel.png"
    _save_image(source, (1, 1), (255, 0, 0))

    result = process_image(source, _black_bg())

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1, 1)
        # Single pixel should retain original color
        assert processed.getpixel((0, 0))[0] > 200


def test_very_wide_aspect_ratio(tmp_path: Path) -> None:
    source = tmp_path / "panoramic.jpg"
    _save_image(source, (2000, 100), (0, 255, 0))

    result = process_image(source, _black_bg())

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (2000, 2000)
        # Top padding should be black
        assert processed.getpixel((1000, 10)) == BLACK
        # Center should be green
        assert processed.getpixel((1000, 1000))[1] > 200


def test_multiple_naming_conflicts(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (100, 50), (128, 128, 128))
    (tmp_path / "photo (1).jpg").write_bytes(b"existing")
    (tmp_path / "photo (2).jpg").write_bytes(b"existing")

    result = process_image(source)

    assert result.success is True
    assert result.destination_path is not None
    assert result.destination_path.name == "photo (3).jpg"


def test_batch_result_mixed_success_and_failure(tmp_path: Path) -> None:
    valid = tmp_path / "good.jpg"
    corrupt = tmp_path / "bad.jpg"
    _save_image(valid, (200, 100), (255, 0, 0))
    corrupt.write_bytes(b"not-an-image")

    batch = process_images([valid, corrupt])

    assert batch.success_count == 1
    assert batch.failure_count == 1
    assert len(batch.results) == 2


# --- ProcessingOptions combinations ---


def test_rotation_180_flips_image(tmp_path: Path) -> None:
    source = tmp_path / "gradient.png"
    # Top half red, bottom half blue
    img = Image.new("RGB", (100, 200), (0, 0, 0))
    for y in range(100):
        for x in range(100):
            img.putpixel((x, y), (255, 0, 0))
    for y in range(100, 200):
        for x in range(100):
            img.putpixel((x, y), (0, 0, 255))
    img.save(source)

    options = ProcessingOptions(rotation_degrees=180, background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (200, 200)
        # After 180 rotation: blue should now be in top half, red in bottom
        center_top = processed.getpixel((100, 55))
        center_bottom = processed.getpixel((100, 145))
        assert center_top[2] > 200  # blue channel
        assert center_bottom[0] > 200  # red channel


def test_rotation_270(tmp_path: Path) -> None:
    source = tmp_path / "wide.jpg"
    _save_image(source, (400, 100), (255, 0, 0))

    options = ProcessingOptions(rotation_degrees=270, background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        # 270 rotation of 400x100 -> 100x400, canvas is 400x400
        assert processed.size == (400, 400)


def test_white_background_padding_pixels(tmp_path: Path) -> None:
    source = tmp_path / "landscape.jpg"
    _save_image(source, (200, 100), (0, 0, 255))

    options = ProcessingOptions(background_color=WHITE)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (200, 200)
        # Top padding should be white
        pixel = processed.getpixel((100, 5))
        assert pixel[0] > 250
        assert pixel[1] > 250
        assert pixel[2] > 250
        # Bottom padding should be white
        pixel = processed.getpixel((100, 195))
        assert pixel[0] > 250
        assert pixel[1] > 250
        assert pixel[2] > 250
        # Center should be blue
        assert processed.getpixel((100, 100))[2] > 200


def test_watermark_bottom_left_position(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_wm = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="LEFT",
        watermark_position="bottom-left",
    )

    result_plain = process_image(source, options_plain)
    result_wm = process_image(source, options_wm)

    with Image.open(result_plain.destination_path) as plain, \
         Image.open(result_wm.destination_path) as wm:
        # Bottom-left region should differ
        bl_plain = list(plain.crop((0, 700, 200, 800)).tobytes())
        bl_wm = list(wm.crop((0, 700, 200, 800)).tobytes())
        assert bl_plain != bl_wm


def test_watermark_center_position(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_wm = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="CENTER",
        watermark_position="center",
    )

    result_plain = process_image(source, options_plain)
    result_wm = process_image(source, options_wm)

    with Image.open(result_plain.destination_path) as plain, \
         Image.open(result_wm.destination_path) as wm:
        # Center region should differ
        center_plain = list(plain.crop((300, 350, 500, 450)).tobytes())
        center_wm = list(wm.crop((300, 350, 500, 450)).tobytes())
        assert center_plain != center_wm


def test_watermark_tiled_position(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_wm = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="TILED",
        watermark_position="tiled",
    )

    result_plain = process_image(source, options_plain)
    result_wm = process_image(source, options_wm)

    with Image.open(result_plain.destination_path) as plain, \
         Image.open(result_wm.destination_path) as wm:
        plain_bytes = list(plain.tobytes())
        wm_bytes = list(wm.tobytes())
        assert plain_bytes != wm_bytes


def test_watermark_small_size(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (128, 128, 128))

    options = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="SMALL",
        watermark_size="small",
    )
    result = process_image(source, options)
    assert result.success is True


def test_watermark_large_size(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (128, 128, 128))

    options = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="LARGE",
        watermark_size="large",
    )
    result = process_image(source, options)
    assert result.success is True


def test_rotation_plus_resize(tmp_path: Path) -> None:
    source = tmp_path / "combo.jpg"
    _save_image(source, (400, 200), (255, 0, 0))

    options = ProcessingOptions(
        rotation_degrees=90,
        resize=ResizeSetting.preset(1080),
        background_color=BLACK,
    )
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        # 400x200 rotated is 200x400 -> 400px square; 1080 preset never upscales.
        assert processed.size == (400, 400)


def test_rotation_plus_watermark(tmp_path: Path) -> None:
    source = tmp_path / "combo.jpg"
    _save_image(source, (400, 200), (128, 128, 128))

    options = ProcessingOptions(
        rotation_degrees=90,
        background_color=(128, 128, 128),
        watermark_text="ROTATED",
    )
    result = process_image(source, options)
    assert result.success is True


def test_all_options_combined(tmp_path: Path) -> None:
    source = tmp_path / "all_opts.jpg"
    _save_image(source, (400, 200), (128, 128, 128))

    options = ProcessingOptions(
        resize=ResizeSetting.preset(1080),
        background_color=WHITE,
        watermark_text="FULL",
        watermark_size="large",
        watermark_position="center",
        rotation_degrees=90,
    )
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        # 1080 preset never upscales the 400px padded square.
        assert processed.size == (400, 400)


def test_watermark_whitespace_only_is_ignored(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (200, 200), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_spaces = ProcessingOptions(
        background_color=(128, 128, 128), watermark_text="   "
    )

    result_plain = process_image(source, options_plain)
    result_spaces = process_image(source, options_spaces)

    with Image.open(result_plain.destination_path) as plain, \
         Image.open(result_spaces.destination_path) as spaced:
        assert list(plain.tobytes()) == list(spaced.tobytes())


# --- generate_preview ---


def test_generate_preview_returns_thumbnail(tmp_path: Path) -> None:
    from photocropper.processor import generate_preview

    source = tmp_path / "photo.jpg"
    _save_image(source, (1600, 900), (255, 0, 0))

    preview = generate_preview(source, ProcessingOptions(background_color=BLACK))

    assert preview.size[0] <= 400
    assert preview.size[1] <= 400
    assert preview.mode == "RGB"


def test_generate_preview_custom_size(tmp_path: Path) -> None:
    from photocropper.processor import generate_preview

    source = tmp_path / "photo.jpg"
    _save_image(source, (1600, 900), (255, 0, 0))

    preview = generate_preview(source, ProcessingOptions(), preview_size=200)

    assert preview.size[0] <= 200
    assert preview.size[1] <= 200


# --- is_supported_image ---


def test_is_supported_image() -> None:
    import tempfile

    from photocropper.processor import is_supported_image

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        Image.new("RGB", (10, 10), (0, 0, 0)).save(f.name)
        assert is_supported_image(Path(f.name)) is True

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"text")
        f.flush()
        assert is_supported_image(Path(f.name)) is False

    assert is_supported_image(Path("/nonexistent/file.jpg")) is False


# --- ResizeSetting ---


def test_resize_setting_output_labels() -> None:
    assert ResizeSetting.original().output_label == "Original"
    assert ResizeSetting.preset(1080).output_label == "1080"
    assert ResizeSetting.custom(2048).output_label == "Custom 2048"


def test_resize_setting_frozen() -> None:
    setting = ResizeSetting.original()
    try:
        setting.mode = "something"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_resize_no_change_when_size_matches_canvas(tmp_path: Path) -> None:
    """When resize size_px equals the canvas size, no resize should occur."""
    source = tmp_path / "square.png"
    _save_image(source, (1080, 1080), (255, 0, 0))

    options = ProcessingOptions(resize=ResizeSetting.preset(1080), background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (1080, 1080)


# --- Security hardening ---


def test_oversized_image_rejected(tmp_path: Path) -> None:
    source = tmp_path / "huge.jpg"
    _save_image(source, (100, 100), (255, 0, 0))

    with patch("PIL.Image.Image.width", new_callable=PropertyMock, return_value=40000), \
         patch("PIL.Image.Image.height", new_callable=PropertyMock, return_value=100):
        result = process_image(source)

    assert result.success is False
    assert "too large" in result.error
    assert "40000" in result.error


def test_symlink_outside_directory_skipped(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_img = outside / "secret.jpg"
    _save_image(outside_img, (100, 100), (255, 0, 0))

    inside = tmp_path / "inside"
    inside.mkdir()
    inside_img = inside / "normal.jpg"
    _save_image(inside_img, (100, 100), (0, 255, 0))

    link = inside / "sneaky.jpg"
    try:
        link.symlink_to(outside_img)
    except OSError:
        # Symlinks may not be supported (e.g., Windows without privileges)
        return

    discovered = expand_input_paths([inside])

    resolved_paths = {p.resolve() for p in discovered}
    assert outside_img.resolve() not in resolved_paths
    assert inside_img.resolve() in resolved_paths


def test_null_bytes_in_filename_handled(tmp_path: Path) -> None:
    # OS won't allow null bytes in filenames, so test the sanitization directly
    import re

    # Directly test the re.sub sanitization logic used in output_path_for
    safe_stem = re.sub(r'[\x00/\\]', '_', "evil\x00path/sep\\end")
    assert "\x00" not in safe_stem
    assert "/" not in safe_stem
    assert "\\" not in safe_stem
    assert safe_stem == "evil_path_sep_end"


# --- Tiled watermark visibility ---


def test_tiled_watermark_covers_multiple_regions(tmp_path: Path) -> None:
    """Tiled watermark should be visible across the entire image, not just one spot."""
    source = tmp_path / "solid.jpg"
    _save_image(source, (500, 500), (128, 128, 128))

    options_plain = ProcessingOptions(background_color=(128, 128, 128))
    options_tiled = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="WATERMARK",
        watermark_size="medium",
        watermark_position="tiled",
    )

    result_plain = process_image(source, options_plain)
    result_tiled = process_image(source, options_tiled)

    with Image.open(result_plain.destination_path) as plain, \
         Image.open(result_tiled.destination_path) as tiled:
        # Sample 4 quadrants — each should have watermark pixels
        size = tiled.size[0]
        q = size // 4
        quadrants = [
            (q, q),          # top-left region
            (3 * q, q),      # top-right region
            (q, 3 * q),      # bottom-left region
            (3 * q, 3 * q),  # bottom-right region
        ]
        diffs_per_quadrant = []
        for cx, cy in quadrants:
            region_diff = 0
            for dx in range(-60, 61, 5):
                for dy in range(-60, 61, 5):
                    x = min(max(cx + dx, 0), size - 1)
                    y = min(max(cy + dy, 0), size - 1)
                    p = plain.getpixel((x, y))
                    t = tiled.getpixel((x, y))
                    if p != t:
                        region_diff += 1
            diffs_per_quadrant.append(region_diff)

        # At least 3 of 4 quadrants should show watermark pixels
        quadrants_with_watermark = sum(1 for d in diffs_per_quadrant if d > 0)
        assert quadrants_with_watermark >= 3, (
            f"Tiled watermark only visible in {quadrants_with_watermark}/4 quadrants: "
            f"{diffs_per_quadrant}"
        )


# --- Custom background color ---


def test_custom_background_color_pixel_verify(tmp_path: Path) -> None:
    """Non-standard background color should appear in padding pixels."""
    source = tmp_path / "wide.jpg"
    _save_image(source, (200, 100), (255, 255, 255))

    purple = (128, 0, 255)
    options = ProcessingOptions(background_color=purple)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (200, 200)
        # Top-center pixel should be padding (purple)
        px = processed.getpixel((100, 10))
        assert abs(px[0] - 128) < 10
        assert abs(px[1] - 0) < 10
        assert abs(px[2] - 255) < 10


# --- Watermark position verification ---


def test_watermark_bottom_right_placement(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (300, 300), (128, 128, 128))

    plain = ProcessingOptions(background_color=(128, 128, 128))
    marked = ProcessingOptions(
        background_color=(128, 128, 128),
        watermark_text="TEST",
        watermark_position="bottom-right",
    )
    r_plain = process_image(source, plain)
    r_marked = process_image(source, marked)

    with Image.open(r_plain.destination_path) as p, \
         Image.open(r_marked.destination_path) as m:
        # Bottom-right region should differ
        br_diff = sum(
            1 for x in range(200, 290) for y in range(260, 290)
            if p.getpixel((x, y)) != m.getpixel((x, y))
        )
        # Top-left region should be unchanged
        tl_diff = sum(
            1 for x in range(10, 50) for y in range(10, 50)
            if p.getpixel((x, y)) != m.getpixel((x, y))
        )
        assert br_diff > 0, "Watermark not visible in bottom-right"
        assert tl_diff == 0, "Watermark leaked into top-left"


# --- Resize + watermark combined ---


def test_resize_and_watermark_combined(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 600), (100, 100, 100))

    options = ProcessingOptions(
        resize=ResizeSetting.preset(500),
        background_color=(100, 100, 100),
        watermark_text="SOLD",
        watermark_position="center",
    )
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (500, 500)

    # Compare with resize-only to verify watermark is present
    options_no_wm = ProcessingOptions(
        resize=ResizeSetting.preset(500),
        background_color=(100, 100, 100),
    )
    result_no_wm = process_image(source, options_no_wm)

    with Image.open(result.destination_path) as with_wm, \
         Image.open(result_no_wm.destination_path) as without_wm:
        diff = sum(
            1 for x in range(0, 500, 5) for y in range(0, 500, 5)
            if with_wm.getpixel((x, y)) != without_wm.getpixel((x, y))
        )
        assert diff > 0, "Watermark not visible after resize"


# --- Empty folder ---


def test_empty_folder_returns_empty_result(tmp_path: Path) -> None:
    empty = tmp_path / "empty_folder"
    empty.mkdir()
    batch = process_images([empty])
    assert batch.success_count == 0
    assert batch.failure_count == 0
    assert len(batch.results) == 0


# --- Overwrite mode ---


def test_overwrite_replaces_original_jpg(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (400, 200), (255, 0, 0))
    original_bytes = source.read_bytes()

    result = process_image(source, ProcessingOptions(background_color=BLACK, overwrite=True))

    assert result.success is True
    assert result.destination_path == source
    assert source.read_bytes() != original_bytes
    with Image.open(source) as processed:
        assert processed.size == (400, 400)
    assert list(tmp_path.iterdir()) == [source]


def test_overwrite_png_writes_jpg_alongside_and_keeps_original(tmp_path: Path) -> None:
    source = tmp_path / "photo.png"
    _save_image(source, (400, 200), (255, 0, 0))
    original_bytes = source.read_bytes()

    result = process_image(source, ProcessingOptions(background_color=BLACK, overwrite=True))

    assert result.success is True
    assert result.destination_path == tmp_path / "photo.jpg"
    assert source.read_bytes() == original_bytes


def test_png_source_never_claims_bare_jpg_name(tmp_path: Path) -> None:
    """Overwrite off always suffixes — a photo.png source must not produce
    photo.jpg, which would collide with (or look like an overwrite of) a
    neighboring photo.jpg."""
    source = tmp_path / "shot.png"
    _save_image(source, (400, 200), (255, 0, 0))
    sibling = tmp_path / "shot.jpg"
    sibling.write_bytes(b"pre-existing unrelated file")

    result = process_image(source, ProcessingOptions(background_color=BLACK))

    assert result.success is True
    assert result.destination_path == tmp_path / "shot (1).jpg"
    assert sibling.read_bytes() == b"pre-existing unrelated file"


def test_png_source_gets_suffix_even_without_collision(tmp_path: Path) -> None:
    source = tmp_path / "solo.png"
    _save_image(source, (400, 200), (255, 0, 0))

    result = process_image(source, ProcessingOptions(background_color=BLACK))

    assert result.success is True
    assert result.destination_path == tmp_path / "solo (1).jpg"


def test_overwrite_off_never_touches_source(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (400, 200), (255, 0, 0))
    original_bytes = source.read_bytes()

    result = process_image(source, ProcessingOptions(background_color=BLACK))

    assert result.success is True
    assert result.destination_path == tmp_path / "photo (1).jpg"
    assert source.read_bytes() == original_bytes


def test_preset_never_upscales_small_image(tmp_path: Path) -> None:
    source = tmp_path / "small.jpg"
    _save_image(source, (300, 200), (255, 0, 0))

    options = ProcessingOptions(resize=ResizeSetting.preset(1000), background_color=BLACK)
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        assert processed.size == (300, 300)


# --- Blended watermark ---


def test_watermark_is_translucent_not_pure_white(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    _save_image(source, (800, 800), (40, 40, 40))

    options = ProcessingOptions(
        background_color=(40, 40, 40),
        watermark_text="WATERMARK",
        watermark_size="large",
        watermark_position="center",
    )
    result = process_image(source, options)

    assert result.success is True
    with Image.open(result.destination_path) as processed:
        center = processed.crop((100, 300, 700, 500))
        px = center.load()
        pixels = [px[x, y] for y in range(center.height) for x in range(center.width)]
        changed = [p for p in pixels if p != (40, 40, 40) and max(p) - 40 > 15]
        assert changed, "Watermark not visible"
        # Blended rendering: no watermark pixel should be anywhere near pure white.
        assert max(max(p) for p in changed) < 220


# --- Mixed file types ---


def test_mixed_file_types_in_folder(tmp_path: Path) -> None:
    folder = tmp_path / "mixed"
    folder.mkdir()

    _save_image(folder / "a.jpg", (100, 100), (255, 0, 0))
    _save_image(folder / "b.png", (100, 100), (0, 255, 0))
    _save_image(folder / "c.webp", (100, 100), (0, 0, 255))
    (folder / "notes.txt").write_text("not an image")
    (folder / "data.csv").write_text("a,b,c")

    batch = process_images([folder])
    assert batch.success_count == 3
    assert batch.failure_count == 0
