from __future__ import annotations

APP_ORGANIZATION = "Steady State Studio"
APP_NAME = "Square Photo Padder"
APP_VERSION = "1.1.2"
WINDOW_TITLE = "Square Photo Padder"
OUTPUT_EXTENSION = ".jpg"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)
# Marketplace-standard square sizes: Amazon zoom minimum (1000), Instagram (1080),
# eBay/Amazon recommended (1600), Shopify (2048).
RESIZE_PRESET_SIZES = [1000, 1080, 1600, 2048]
RESIZE_MODE_ORIGINAL = "original"
RESIZE_MODE_CUSTOM = "custom"
CUSTOM_SIZE_MIN = 64
CUSTOM_SIZE_MAX = 8192
JPEG_QUALITY = 95
MAX_IMAGE_DIMENSION = 32768  # pixels; reject images larger than this in either dimension
# Bound decoded input and the square allocation before any expensive rendering.
MAX_SOURCE_PIXELS = 80_000_000
MAX_CANVAS_PIXELS = 8192 * 8192
MAX_WORKING_BYTES = 1536 * 1024 * 1024
WATERMARK_SIZE_DIVISORS = {"small": 20, "medium": 12, "large": 8}
WATERMARK_POSITIONS = [
    "top-left", "top-right", "center", "bottom-left", "bottom-right", "tiled",
]
KOFI_URL = "https://ko-fi.com/steadystatestudio"
KOFI_CONFIGURED = "YOUR_KOFI_USERNAME" not in KOFI_URL
