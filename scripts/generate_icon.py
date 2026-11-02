"""Generate the app icon for every packaging target.

With OPENAI_API_KEY set, candidates can be generated via the OpenAI Images
API; otherwise (or with --fallback) the icon is drawn with Pillow. The chosen
1024px master is written to:

- src/photocropper/assets/icon-256.png  (runtime window icon)
- packaging/linux/square-photo-padder.png
- packaging/windows/app.ico  (multi-size)
- docs/icon.png

Usage:
  python scripts/generate_icon.py                 # AI if key set, else fallback
  python scripts/generate_icon.py --fallback      # Pillow-drawn icon
  python scripts/generate_icon.py --candidates 2 --out DIR   # AI candidates only
  python scripts/generate_icon.py --from FILE     # finalize a chosen candidate
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MASTER_SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PROMPT = (
    "Flat minimal desktop app icon: a full-bleed rounded square filled with a "
    "smooth vertical blue gradient. Centered inside, a square photo with solid "
    "black letterbox bars across the top and bottom edges, framed by a thin "
    "white border. Nothing else — no letters, no text, no shadows, no padding "
    "around the plate. Clean professional flat vector style, crisp edges."
)


def draw_fallback_icon(size: int = MASTER_SIZE) -> Image.Image:
    """Full-bleed blue plate with a centered square that has black bars top
    and bottom — the letterbox padding the app adds to make a photo square.

    Tester feedback: show what the tool does. Black bars above and below a
    photo band read instantly as 'padded to square'."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    def s(value: float) -> int:
        return round(size * value)

    # Full-bleed plate with a subtle vertical blue gradient.
    top, bottom = (91, 166, 236), (56, 118, 194)
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    plate = gradient.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=s(0.22), fill=255)
    image.paste(plate, (0, 0), mask)

    # The mark: a square canvas of black padding with the photo as a lighter
    # band across the middle — black bars top and bottom.
    inset = s(0.24)
    square = size - 2 * inset
    canvas = Image.new("RGB", (square, square), (0, 0, 0))
    band_height = round(square * 0.46)
    band_top = (square - band_height) // 2
    ImageDraw.Draw(canvas).rectangle(
        (0, band_top, square, band_top + band_height), fill=(236, 239, 244),
    )
    image.paste(canvas, (inset, inset))

    # Crisp white frame around the squared canvas.
    ImageDraw.Draw(image).rectangle(
        (inset, inset, inset + square, inset + square),
        outline="#ffffff",
        width=s(0.035),
    )
    return image


def generate_ai_candidates(count: int, out_dir: Path) -> list[Path]:
    api_key = os.environ["OPENAI_API_KEY"]
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps({
            "model": "gpt-image-1",
            "prompt": PROMPT,
            "size": "1024x1024",
            "quality": "high",
            "n": count,
        }).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.load(response)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, item in enumerate(payload["data"], start=1):
        path = out_dir / f"candidate-{index}.png"
        path.write_bytes(base64.b64decode(item["b64_json"]))
        paths.append(path)
    return paths


def clean_ai_master(image: Image.Image) -> Image.Image:
    """Crop an AI candidate to its icon plate and make the corners transparent.

    Generated images sit on an opaque page-colored background; without this
    the taskbar icon shows a white plate.
    """
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, rgba.getpixel((2, 2)))
    # High threshold so soft drop shadows around the plate don't skew the crop.
    difference = ImageChops.difference(rgba, background).convert("L")
    bbox = difference.point(lambda v: 255 if v > 60 else 0).getbbox()
    if bbox:
        rgba = rgba.crop(bbox)

    side = max(rgba.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
    square = square.resize((MASTER_SIZE, MASTER_SIZE), Image.Resampling.LANCZOS)

    mask = Image.new("L", (MASTER_SIZE, MASTER_SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, MASTER_SIZE - 1, MASTER_SIZE - 1), radius=round(MASTER_SIZE * 0.28), fill=255,
    )
    square.putalpha(mask)
    return square


def finalize(master: Image.Image) -> None:
    master = master.convert("RGBA")
    if master.size != (MASTER_SIZE, MASTER_SIZE):
        master = master.resize((MASTER_SIZE, MASTER_SIZE), Image.Resampling.LANCZOS)
    icon_256 = master.resize((256, 256), Image.Resampling.LANCZOS)

    targets = [
        ROOT / "src" / "photocropper" / "assets" / "icon-256.png",
        ROOT / "packaging" / "linux" / "square-photo-padder.png",
        ROOT / "docs" / "icon.png",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        icon_256.save(target)
        print(f"wrote {target.relative_to(ROOT)}")

    ico_path = ROOT / "packaging" / "windows" / "app.ico"
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    icon_256.save(ico_path, format="ICO", sizes=ICO_SIZES)
    print(f"wrote {ico_path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fallback", action="store_true", help="use the Pillow-drawn icon")
    parser.add_argument("--candidates", type=int, default=0, help="generate N AI candidates and stop")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "icon-candidates")
    parser.add_argument("--from", dest="source", type=Path, help="finalize this image file")
    args = parser.parse_args()

    if args.candidates:
        for path in generate_ai_candidates(args.candidates, args.out):
            print(f"wrote {path}")
        return

    if args.source:
        finalize(clean_ai_master(Image.open(args.source)))
        return

    if not args.fallback and os.environ.get("OPENAI_API_KEY"):
        candidate = generate_ai_candidates(1, args.out)[0]
        finalize(clean_ai_master(Image.open(candidate)))
        return

    finalize(draw_fallback_icon())


if __name__ == "__main__":
    main()
