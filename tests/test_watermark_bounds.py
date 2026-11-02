"""Small-output placement preserves the complete glyphs, including the halo."""
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont

from photocropper import processor
from photocropper.processor import ProcessingOptions, ResizeSetting, process_image


@pytest.mark.parametrize("font_kind", ["platform", "fallback"])
@pytest.mark.parametrize("text", ["TEST", "jgy", "Ágj"])
@pytest.mark.parametrize("position", ["top-left", "top-right", "bottom-left", "bottom-right", "center"])
def test_small_watermark_keeps_whole_glyph_shape_and_position(monkeypatch, font_kind, text, position):
    font = processor._load_watermark_font(28) if font_kind == "platform" else ImageFont.load_default()
    monkeypatch.setattr(processor, "_load_watermark_font", lambda _size: font)
    with Image.new("RGB", (200, 200), (100, 100, 100)) as background:
        with processor._apply_watermark(background, text, "medium", position) as actual:
            with ImageChops.difference(background, actual) as difference:
                box = difference.getbbox()
            assert box is not None
            # At this output size the requested 5px inset leaves at least 3px
            # beyond the 2px halo. Check observed pixels, not placement math.
            assert box[0] >= 3 and box[1] >= 3 and box[2] <= 197 and box[3] <= 197
            if position == "center":
                assert abs(box[0] + box[2] - 200) <= 2
                assert abs(box[1] + box[3] - 200) <= 2
            else:
                assert (box[2] < 100) if position.endswith("left") else (box[0] > 100)
                assert (box[3] < 100) if position.startswith("top") else (box[1] > 100)
            # Render the same style well away from every edge. Translation must
            # preserve its whole pixel shape; clipped descenders/halos differ.
            with Image.new("RGBA", (400, 400), (0, 0, 0, 0)) as overlay:
                draw = ImageDraw.Draw(overlay)
                processor._draw_outlined_text(draw, 100, 100, text, font)
                with Image.new("RGBA", (400, 400), (100, 100, 100, 255)) as plain:
                    with Image.alpha_composite(plain, overlay).convert("RGB") as reference:
                        with Image.new("RGB", reference.size, (100, 100, 100)) as baseline:
                            with ImageChops.difference(baseline, reference) as difference:
                                reference_box = difference.getbbox()
                        with actual.crop(box) as ink, reference.crop(reference_box) as full_ink:
                            assert ink.size == full_ink.size
                            assert ink.tobytes() == full_ink.tobytes()


def test_custom_200_jpeg_has_bottom_border_and_preserves_source(tmp_path):
    path = tmp_path / "square.png"
    with Image.new("RGB", (960, 960), (100, 100, 100)) as image:
        image.save(path)
    before = path.read_bytes()
    options = ProcessingOptions(resize=ResizeSetting("custom", 200), watermark_text="TEST",
                                watermark_size="medium", watermark_position="bottom-right")
    result = process_image(path, options)
    assert result.success, result.error
    assert path.read_bytes() == before
    with Image.open(result.destination_path) as saved:
        assert saved.size == (200, 200) and saved.format == "JPEG"
        assert max(abs(channel - 100) for x in range(200) for channel in saved.getpixel((x, 199))) <= 8
        assert max(abs(channel - 100) for y in range(200) for channel in saved.getpixel((199, y))) <= 8
        with saved.crop((100, 100, 200, 197)) as corner:
            assert corner.getextrema()[0][1] > 140
