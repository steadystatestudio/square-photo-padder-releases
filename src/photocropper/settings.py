from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

from photocropper.constants import (
    APP_NAME,
    APP_ORGANIZATION,
    DEFAULT_BACKGROUND_COLOR,
    RESIZE_MODE_CUSTOM,
    RESIZE_MODE_ORIGINAL,
)

SETTINGS_KEY_RESIZE_MODE = "resize/mode"
SETTINGS_KEY_RESIZE_SIZE = "resize/size"
SETTINGS_KEY_CUSTOM_SIZE = "resize/custom_size"
SETTINGS_KEY_BG_COLOR_R = "background/r"
SETTINGS_KEY_BG_COLOR_G = "background/g"
SETTINGS_KEY_BG_COLOR_B = "background/b"
SETTINGS_KEY_CUSTOM_COLORS = "background/custom_colors"
SETTINGS_KEY_WATERMARK_TEXT = "processing/watermark_text"
SETTINGS_KEY_WATERMARK_SIZE = "processing/watermark_size"
SETTINGS_KEY_WATERMARK_POSITION = "processing/watermark_position"
SETTINGS_KEY_OVERWRITE = "processing/overwrite"
SETTINGS_KEY_TOOLTIPS_ENABLED = "ui/tooltips_enabled"
SETTINGS_KEY_APPEARANCE = "ui/appearance"


def load_appearance() -> str:
    value = _settings().value(SETTINGS_KEY_APPEARANCE, "system", type=str)
    return value if value in {"system", "dark", "light"} else "system"


def save_appearance(value: str) -> None:
    settings = _settings()
    settings.setValue(SETTINGS_KEY_APPEARANCE, value)
    settings.sync()


@dataclass(slots=True, frozen=True)
class StoredResizePreference:
    mode: str = RESIZE_MODE_ORIGINAL
    size_px: int | None = None


@dataclass(slots=True, frozen=True)
class StoredProcessingPreference:
    background_color: tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR
    watermark_text: str = ""
    watermark_size: str = "medium"
    watermark_position: str = "bottom-right"
    overwrite: bool = False


def _settings() -> QSettings:
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, APP_ORGANIZATION, APP_NAME)


def load_resize_preference() -> StoredResizePreference:
    settings = _settings()
    mode = settings.value(SETTINGS_KEY_RESIZE_MODE, RESIZE_MODE_ORIGINAL, type=str)
    size_px = settings.value(SETTINGS_KEY_RESIZE_SIZE, None, type=int)
    if mode == RESIZE_MODE_CUSTOM and size_px:
        return StoredResizePreference(mode=mode, size_px=size_px)
    if mode == RESIZE_MODE_ORIGINAL:
        return StoredResizePreference(mode=mode, size_px=None)
    if size_px:
        return StoredResizePreference(mode=mode, size_px=size_px)
    return StoredResizePreference()


def save_resize_preference(preference: StoredResizePreference) -> None:
    settings = _settings()
    settings.setValue(SETTINGS_KEY_RESIZE_MODE, preference.mode)
    if preference.size_px is None:
        settings.remove(SETTINGS_KEY_RESIZE_SIZE)
    else:
        settings.setValue(SETTINGS_KEY_RESIZE_SIZE, preference.size_px)
    settings.sync()


def load_processing_preference() -> StoredProcessingPreference:
    settings = _settings()
    dr, dg, db = DEFAULT_BACKGROUND_COLOR
    r = max(0, min(255, settings.value(SETTINGS_KEY_BG_COLOR_R, dr, type=int)))
    g = max(0, min(255, settings.value(SETTINGS_KEY_BG_COLOR_G, dg, type=int)))
    b = max(0, min(255, settings.value(SETTINGS_KEY_BG_COLOR_B, db, type=int)))
    watermark_text = settings.value(SETTINGS_KEY_WATERMARK_TEXT, "", type=str)[:100]
    watermark_size = settings.value(SETTINGS_KEY_WATERMARK_SIZE, "medium", type=str)
    if watermark_size not in {"small", "medium", "large"}:
        watermark_size = "medium"
    watermark_position = settings.value(SETTINGS_KEY_WATERMARK_POSITION, "bottom-right", type=str)
    if watermark_position not in {
        "top-left", "top-right", "center",
        "bottom-left", "bottom-right", "tiled",
    }:
        watermark_position = "bottom-right"
    overwrite = settings.value(SETTINGS_KEY_OVERWRITE, False, type=bool)
    return StoredProcessingPreference(
        background_color=(r, g, b),
        watermark_text=watermark_text,
        watermark_size=watermark_size,
        watermark_position=watermark_position,
        overwrite=overwrite,
    )


def save_processing_preference(preference: StoredProcessingPreference) -> None:
    settings = _settings()
    r, g, b = preference.background_color
    settings.setValue(SETTINGS_KEY_BG_COLOR_R, r)
    settings.setValue(SETTINGS_KEY_BG_COLOR_G, g)
    settings.setValue(SETTINGS_KEY_BG_COLOR_B, b)
    settings.setValue(SETTINGS_KEY_WATERMARK_TEXT, preference.watermark_text)
    settings.setValue(SETTINGS_KEY_WATERMARK_SIZE, preference.watermark_size)
    settings.setValue(SETTINGS_KEY_WATERMARK_POSITION, preference.watermark_position)
    settings.setValue(SETTINGS_KEY_OVERWRITE, preference.overwrite)
    settings.sync()


def load_custom_colors() -> list[tuple[int, int, int]]:
    """The color picker's saved custom colors, most recent first."""
    raw = _settings().value(SETTINGS_KEY_CUSTOM_COLORS, "", type=str)
    colors: list[tuple[int, int, int]] = []
    for part in raw.split(","):
        part = part.strip().lstrip("#")
        if len(part) != 6:
            continue
        try:
            value = int(part, 16)
        except ValueError:
            continue
        colors.append(((value >> 16) & 255, (value >> 8) & 255, value & 255))
    return colors


def save_custom_colors(colors: list[tuple[int, int, int]]) -> None:
    settings = _settings()
    encoded = ",".join(f"{r:02x}{g:02x}{b:02x}" for r, g, b in colors)
    settings.setValue(SETTINGS_KEY_CUSTOM_COLORS, encoded)
    settings.sync()


def load_tooltips_enabled() -> bool:
    return _settings().value(SETTINGS_KEY_TOOLTIPS_ENABLED, True, type=bool)


def save_tooltips_enabled(enabled: bool) -> None:
    settings = _settings()
    settings.setValue(SETTINGS_KEY_TOOLTIPS_ENABLED, bool(enabled))
    settings.sync()


def load_custom_size(default: int) -> int:
    value = _settings().value(SETTINGS_KEY_CUSTOM_SIZE, default, type=int)
    return value if value > 0 else default


def save_custom_size(size_px: int) -> None:
    settings = _settings()
    settings.setValue(SETTINGS_KEY_CUSTOM_SIZE, int(size_px))
    settings.sync()
