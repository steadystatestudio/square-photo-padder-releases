from __future__ import annotations

import ctypes
import io
import logging
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from photocropper.constants import (
    DEFAULT_BACKGROUND_COLOR,
    JPEG_QUALITY,
    MAX_CANVAS_PIXELS,
    MAX_IMAGE_DIMENSION,
    MAX_SOURCE_PIXELS,
    MAX_WORKING_BYTES,
    OUTPUT_EXTENSION,
    RESIZE_MODE_CUSTOM,
    RESIZE_MODE_ORIGINAL,
    SUPPORTED_EXTENSIONS,
    WATERMARK_SIZE_DIVISORS,
)


@dataclass(slots=True, frozen=True)
class ImageResult:
    source_path: Path
    success: bool
    destination_path: Path | None = None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class BatchResult:
    results: list[ImageResult]
    cancelled: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)


@dataclass(slots=True, frozen=True)
class ResizeSetting:
    mode: str
    size_px: int | None = None

    @classmethod
    def original(cls) -> "ResizeSetting":
        return cls(mode=RESIZE_MODE_ORIGINAL, size_px=None)

    @classmethod
    def preset(cls, size_px: int) -> "ResizeSetting":
        return cls(mode=f"preset:{size_px}", size_px=size_px)

    @classmethod
    def custom(cls, size_px: int) -> "ResizeSetting":
        return cls(mode=RESIZE_MODE_CUSTOM, size_px=size_px)

    @property
    def output_label(self) -> str:
        if self.size_px is None:
            return "Original"
        if self.mode == RESIZE_MODE_CUSTOM:
            return f"Custom {self.size_px}"
        return f"{self.size_px}"


@dataclass(slots=True, frozen=True)
class ProcessingOptions:
    resize: ResizeSetting = field(default_factory=ResizeSetting.original)
    background_color: tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR
    watermark_text: str = ""
    watermark_size: str = "medium"
    watermark_position: str = "bottom-right"
    rotation_degrees: int = 0
    overwrite: bool = False


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


ProgressCallback = Callable[[int, int, Path], None]


def process_images(
    paths: list[Path],
    options: ProcessingOptions | None = None,
    progress: ProgressCallback | None = None,
    rotation_overrides: dict[Path, int] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> BatchResult:
    """Process every image under `paths`.

    `rotation_overrides` maps a specific input path to its own rotation in
    degrees, overriding `options.rotation_degrees` for that image only — this
    is how each photo keeps its own orientation across a batch.
    """
    active_options = options or ProcessingOptions()
    expanded_paths = expand_input_paths(paths)
    total = len(expanded_paths)
    results: list[ImageResult] = []
    for index, path in enumerate(expanded_paths):
        if cancelled is not None and cancelled():
            return BatchResult(results=results, cancelled=True)
        per_image = active_options
        if rotation_overrides is not None and path in rotation_overrides:
            per_image = replace(active_options, rotation_degrees=rotation_overrides[path])
        results.append(process_image(path, per_image))
        if progress is not None:
            progress(index + 1, total, path)
    return BatchResult(results=results)


def process_image(path: Path, options: ProcessingOptions | None = None) -> ImageResult:
    source_path = Path(path)
    if not is_supported_image(source_path):
        return ImageResult(source_path=source_path, success=False, error="Unsupported file type")

    active_options = options or ProcessingOptions()
    destination = output_path_for(source_path, overwrite=active_options.overwrite)
    replace_source = active_options.overwrite and (
        os.path.normcase(os.path.abspath(destination)) == os.path.normcase(os.path.abspath(source_path))
    )

    try:
        source_identity = _source_identity(source_path) if replace_source else None
        with Image.open(source_path) as original:
            if original.width > MAX_IMAGE_DIMENSION or original.height > MAX_IMAGE_DIMENSION:
                return ImageResult(
                    source_path=source_path, success=False,
                    error=f"Image too large ({original.width}x{original.height})",
                )
            processed = _render_square_padded_image(original, active_options)
            processed.load()
        # Save after the source handle is closed: with overwrite on, the
        # destination can be the source file itself, which Windows refuses
        # to replace while it is still open.
        # Overwrite means this source, never a different photo with the same stem.
        try:
            destination = _save_completed_image(processed, source_path, destination, replace_source, source_identity)
        finally:
            processed.close()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError, MemoryError) as exc:
        return ImageResult(source_path=source_path, success=False, error=str(exc) or type(exc).__name__)

    return ImageResult(source_path=source_path, success=True, destination_path=destination)


def _source_identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError("Source is not a regular file; add the original photo again.")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _save_completed_image(
    image: Image.Image, source: Path, destination: Path, overwrite: bool,
    source_identity: tuple[int, int, int, int, int] | None,
) -> Path:
    """Encode completely before publishing, without ever truncating a source."""
    descriptor, temporary = tempfile.mkstemp(prefix=".square-photo-padder-", suffix=".tmp", dir=source.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            image.save(handle, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
            handle.flush()
            if os.name != "nt":
                # mkstemp creates an owner-only file. A replaced photo keeps its
                # permissions; a new copy gets the ordinary ones for a new file.
                try:
                    mode = stat.S_IMODE(source.stat().st_mode) if overwrite else _new_file_mode()
                    os.fchmod(handle.fileno(), mode)
                except OSError:
                    pass  # The folder has no permission bits to set.
            os.fsync(handle.fileno())
        if overwrite:
            if _source_identity(source) != source_identity:
                raise OSError("Source changed while processing; the changed photo was kept. Add it again and retry.")
            os.replace(temporary_path, destination)
        else:
            for _ in range(100):
                try:
                    _publish_no_replace(temporary_path, destination)
                    break
                except FileExistsError:
                    destination = output_path_for(source)
            else:
                raise OSError("Output names keep changing. Try saving again when the folder is idle.")
        return destination
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            # The completed output may already be published. A leftover temporary
            # file must not turn a successful save into a misleading failure.
            logging.getLogger(__name__).warning("Could not remove temporary image %s", temporary_path, exc_info=True)


def _new_file_mode() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def replaces_source(source_path: Path) -> bool:
    """Whether Overwrite would replace this original rather than save a copy."""
    return Path(source_path).suffix.lower() == OUTPUT_EXTENSION


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Atomic publication on supported desktop platforms, including removable media."""
    if os.name == "nt":
        os.rename(source, destination)  # Windows rename refuses an existing file.
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise OSError("This system cannot safely create the output without replacing files.")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        # On other platforms a hard link offers the same no-clobber guarantee.
        os.link(source, destination)


def generate_preview(image_path: Path, options: ProcessingOptions, preview_size: int = 400) -> Image.Image:
    with Image.open(image_path) as original:
        processed = _render_square_padded_image(original, options)
        processed.thumbnail((preview_size, preview_size), Image.Resampling.LANCZOS)
        return processed


def expand_input_paths(paths: Iterable[Path]) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()

    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            resolved_dir = path.resolve()
            for child in sorted(path.rglob("*")):
                resolved = child.resolve()
                if not resolved.is_relative_to(resolved_dir):
                    continue  # skip symlinks pointing outside
                if resolved in seen or not is_supported_image(child):
                    continue
                seen.add(resolved)
                discovered.append(child)
            continue

        resolved = path.resolve()
        if resolved in seen or not is_supported_image(path):
            continue
        seen.add(resolved)
        discovered.append(path)

    return discovered


def output_path_for(source_path: Path, overwrite: bool = False) -> Path:
    """Output path in the same folder as the source.

    Overwrite on: prefer `<stem>.jpg` (replacing the original for .jpg
    sources only). A different existing photo is skipped at publication.
    Overwrite off: always a suffixed `<stem> (n).jpg` — the
    bare name is never used, so a `photo.png` source can't silently claim
    (or appear to overwrite) a neighboring `photo.jpg`.
    """
    output_dir = source_path.parent
    safe_stem = re.sub(r'[\x00/\\]', '_', source_path.stem)
    if overwrite:
        if replaces_source(source_path) and safe_stem == source_path.stem:
            # IMG_001.JPG is the source .jpg photo on every platform. Returning a
            # lowercase name left the original beside a new file on Linux.
            return source_path
        return output_dir / f"{safe_stem}{OUTPUT_EXTENSION}"

    index = 1
    while True:
        candidate = output_dir / f"{safe_stem} ({index}){OUTPUT_EXTENSION}"
        if not os.path.lexists(candidate):
            return candidate
        index += 1


def _normalize_srgb(image: Image.Image) -> Image.Image:
    """Apply orientation and valid color profiles; never copy personal metadata."""
    oriented = ImageOps.exif_transpose(image)
    try:
        rgba = oriented.convert("RGBA")
        profile = image.info.get("icc_profile")
        if not profile:
            return rgba
        try:
            input_profile = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            if oriented.mode in {"RGB", "CMYK", "LAB", "L"}:
                color = oriented
            else:
                color = oriented.convert("L" if oriented.mode == "LA" else "RGB")
            try:
                converted = ImageCms.profileToProfile(
                    color, input_profile, ImageCms.createProfile("sRGB"), outputMode="RGB",
                )
                try:
                    converted.putalpha(rgba.getchannel("A"))
                    rgba.close()
                    return converted
                except BaseException:
                    converted.close()
                    raise
            finally:
                if color is not oriented:
                    color.close()
        except (ImageCms.PyCMSError, OSError, ValueError) as exc:
            rgba.close()
            raise ValueError("Invalid or unsupported color profile; export this photo as sRGB and retry.") from exc
    finally:
        oriented.close()


def _render_square_padded_image(image: Image.Image, options: ProcessingOptions) -> Image.Image:
    width, height = image.width, image.height
    if max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_SOURCE_PIXELS:
        raise ValueError(f"Image too large ({width}x{height}); limit is {MAX_SOURCE_PIXELS:,} source pixels")
    # UI rotation is in quarter turns. Reject arbitrary angles before their
    # expanded bounding box can allocate unexpected amounts of memory.
    if options.rotation_degrees % 90:
        raise ValueError("Rotation must be a multiple of 90 degrees")
    canvas_size = max(width, height)
    target = canvas_size
    if options.resize.size_px is not None and options.resize.size_px > 0:
        target = min(options.resize.size_px, canvas_size)
    if target * target > MAX_CANVAS_PIXELS:
        raise ValueError("Square image too large; choose a smaller resize size (8192 px or less)")

    # Budget source decode, EXIF transpose, conversion/rotation, square and
    # watermark overlays conservatively. A pixel ceiling alone misses panoramas
    # and tiled watermark intermediates. This is a bound, not an RSS guarantee.
    estimated_bytes = width * height * 20 + target * target * 4
    if options.watermark_text.strip():
        estimated_bytes += target * target * (40 if options.watermark_position == "tiled" else 20)
    if estimated_bytes > MAX_WORKING_BYTES:
        raise ValueError("Image needs too much working memory; choose a smaller resize size or remove the watermark")

    # Retain alpha for RGBA, LA, palette transparency and RGB color-key PNGs.
    normalized = _normalize_srgb(image)
    if options.rotation_degrees % 360:
        rotated = normalized.rotate(options.rotation_degrees % 360, expand=True)
        normalized.close()
        normalized = rotated

    # Downsize before allocating the square, including for very narrow panoramas.
    if target != canvas_size:
        normalized.thumbnail((target, target), Image.Resampling.LANCZOS)
    width, height = normalized.size
    canvas = Image.new("RGB", (target, target), options.background_color)
    canvas.paste(normalized, ((target - width) // 2, (target - height) // 2), normalized)
    normalized.close()

    if options.watermark_text.strip():
        watermarked = _apply_watermark(
            canvas, options.watermark_text.strip(),
            options.watermark_size, options.watermark_position,
        )
        if watermarked is not canvas:
            canvas.close()
        canvas = watermarked
    return canvas


def _apply_watermark(
    image: Image.Image, text: str, size: str = "medium", position: str = "bottom-right",
) -> Image.Image:
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)[:100]
    if not text:
        return image
    divisor = WATERMARK_SIZE_DIVISORS.get(size, 20)
    font_size = max(28, image.size[0] // divisor)
    font = _load_watermark_font(font_size)

    if position == "tiled":
        return _apply_tiled_watermark(image, text, font)

    w, h = image.size
    # Reserve the two-pixel halo as well as a clear outer border. A minimum
    # 28px font can be wider than an entire small photo, even for "TEST".
    margin = max(3, w // 40)
    available_width, available_height = w - 2 * margin, h - 2 * margin
    while True:
        bbox = font.getbbox(text)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if text_width <= available_width and text_height <= available_height:
            break
        if font_size <= 1 or available_width <= 0 or available_height <= 0:
            raise ValueError("Watermark text does not fit inside this photo. Shorten the text or use a larger photo.")
        ratio = min(available_width / max(1, text_width), available_height / max(1, text_height))
        font_size = max(1, min(font_size - 1, int(font_size * ratio)))
        font = (font.font_variant(size=font_size) if isinstance(font, ImageFont.FreeTypeFont)
                else _load_watermark_font(font_size))

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if position == "bottom-left":
        x, y = margin, h - text_height - margin
    elif position == "top-left":
        x, y = margin, margin
    elif position == "top-right":
        x, y = w - text_width - margin, margin
    elif position == "center":
        x, y = (w - text_width) // 2, (h - text_height) // 2
    else:
        x, y = w - text_width - margin, h - text_height - margin

    _draw_outlined_text(draw, x - bbox[0], y - bbox[1], text, font)

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _load_watermark_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    import sys

    names = ["arial.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
    search_dirs: list[Path] = []
    if sys.platform == "win32":
        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        search_dirs.append(Path(win_dir) / "Fonts")
    elif sys.platform == "darwin":
        search_dirs += [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    else:
        search_dirs += [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local/share/fonts",
            Path.home() / ".fonts",
        ]

    for name in names:
        try:
            return ImageFont.truetype(name, font_size)
        except OSError:
            pass
        for directory in search_dirs:
            if not directory.exists():
                continue
            for match in directory.rglob(name):
                try:
                    return ImageFont.truetype(str(match), font_size)
                except OSError:
                    continue
    return ImageFont.load_default(size=font_size)


# Translucent fill with a soft dark halo: blends into the photo like a real
# watermark while staying readable on both dark and light backgrounds.
_WATERMARK_FILL = (255, 255, 255, 110)
_WATERMARK_HALO = (0, 0, 0, 60)


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)]:
        draw.text((x + dx, y + dy), text, font=font, fill=_WATERMARK_HALO)
    draw.text((x, y), text, font=font, fill=_WATERMARK_FILL)


def _apply_tiled_watermark(
    image: Image.Image, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Image.Image:
    w, h = image.size
    # Create oversized overlay to allow rotation without clipping
    diag = int((w**2 + h**2) ** 0.5) + 100
    overlay = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    if text_width <= 0 or text_height <= 0:
        overlay.close()
        return image
    step_x = max(1, int(text_width * 1.4))
    step_y = max(1, int(text_height * 2.5))
    outline = (0, 0, 0, 45)
    text_fill = (255, 255, 255, 90)

    for y in range(0, diag, step_y):
        for x in range(0, diag, step_x):
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
            draw.text((x, y), text, font=font, fill=text_fill)

    # Rotate entire overlay, then crop to image size
    rotated = overlay.rotate(-30, resample=Image.Resampling.BICUBIC)
    rx, ry = rotated.size
    left = (rx - w) // 2
    top = (ry - h) // 2
    cropped = rotated.crop((left, top, left + w, top + h))

    return Image.alpha_composite(image.convert("RGBA"), cropped).convert("RGB")
