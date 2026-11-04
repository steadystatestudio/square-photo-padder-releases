from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from photocropper.system_fonts import (
    accent_colors,
    apply_system_font,
    bind_appearance_refresh,
    system_font_css,
)


def _is_system_dark_mode() -> bool:
    from .appearance import resolved_color_scheme
    app = QApplication.instance()
    resolved = resolved_color_scheme(app) if app else None
    if resolved in {"dark", "light"}:
        return resolved == "dark"
    palette = app._studio_native_palette if app and hasattr(app, "_studio_native_palette") else QPalette()
    color = palette.window().color()
    return color.lightnessF() < .5


def _read_gtk_colors() -> dict[str, str] | None:
    """Read color definitions from the active GTK3 theme CSS."""
    import os
    import re

    # Get theme name from settings.ini
    theme_name = None
    for config_path in [
        os.path.expanduser("~/.config/gtk-3.0/settings.ini"),
        "/etc/gtk-3.0/settings.ini",
    ]:
        try:
            with open(config_path) as f:
                for line in f:
                    if line.strip().startswith("gtk-theme-name"):
                        theme_name = line.split("=", 1)[1].strip()
                        break
            if theme_name:
                break
        except OSError:
            continue

    if not theme_name:
        return None

    # Find theme CSS file
    search_paths = [
        os.path.expanduser(f"~/.themes/{theme_name}/gtk-3.0"),
        f"/usr/share/themes/{theme_name}/gtk-3.0",
    ]

    colors: dict[str, str] = {}
    color_re = re.compile(r"@define-color\s+(\w+)\s+(#[0-9a-fA-F]{3,8})")

    for theme_dir in search_paths:
        if not os.path.isdir(theme_dir):
            continue
        # Parse well-known CSS files in the theme directory
        for css_name in [
            "gtk.css", "gtk-dark.css", "gtk-main.css", "_colors.css",
        ]:
            css_path = os.path.join(theme_dir, css_name)
            try:
                with open(css_path) as f:
                    for line in f:
                        match = color_re.search(line)
                        if match:
                            colors[match.group(1)] = match.group(2)
            except OSError:
                continue
        # Also follow @import directives in gtk.css
        gtk_css = os.path.join(theme_dir, "gtk.css")
        try:
            with open(gtk_css) as f:
                import_re = re.compile(
                    r'@import\s+url\(["\']?([^"\')\s]+)["\']?\)',
                )
                for line in f:
                    imp = import_re.search(line)
                    if imp:
                        imported = os.path.join(theme_dir, imp.group(1))
                        try:
                            with open(imported) as imp_f:
                                for imp_line in imp_f:
                                    match = color_re.search(imp_line)
                                    if match:
                                        colors[match.group(1)] = (
                                            match.group(2)
                                        )
                        except OSError:
                            continue
        except OSError:
            pass

        if colors:
            return colors

    return None


def _adjust_brightness(hex_color: str, amount: int) -> str:
    """Lighten (positive) or darken (negative) a hex color."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = max(0, min(255, int(hex_color[0:2], 16) + amount))
    g = max(0, min(255, int(hex_color[2:4], 16) + amount))
    b = max(0, min(255, int(hex_color[4:6], 16) + amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _gtk_colors_to_scheme(
    gtk_colors: dict[str, str], dark: bool,
) -> dict[str, str]:
    """Convert GTK @define-color values to our stylesheet color scheme."""
    bg = gtk_colors.get("theme_bg_color") or gtk_colors.get("bg_color", "")
    fg = gtk_colors.get("theme_fg_color") or gtk_colors.get("fg_color", "")
    base = (
        gtk_colors.get("theme_base_color") or gtk_colors.get("base_color", "")
    )
    text = (
        gtk_colors.get("theme_text_color")
        or gtk_colors.get("text_color", "")
        or fg
    )
    sel_bg = (
        gtk_colors.get("theme_selected_bg_color")
        or gtk_colors.get("selected_bg_color", "")
    )
    sel_fg = (
        gtk_colors.get("theme_selected_fg_color")
        or gtk_colors.get("selected_fg_color", "")
    )
    borders = (
        gtk_colors.get("borders") or gtk_colors.get("unfocused_borders", "")
    )

    # If we got enough colors, build scheme
    if bg and fg and base:
        return {
            "window": bg,
            "text": fg,
            "base": base,
            "button": _adjust_brightness(bg, 10 if dark else -8),
            "button_text": fg,
            "border": borders or _adjust_brightness(
                bg, 30 if dark else -25,
            ),
            "hover": _adjust_brightness(bg, 15 if dark else -12),
            "pressed": _adjust_brightness(bg, -5 if dark else -18),
            "highlight": sel_bg or "#4f8cff",
            "highlight_text": sel_fg or "#ffffff",
            "highlight_hover": _adjust_brightness(
                sel_bg or "#4f8cff", 20,
            ),
            "disabled_bg": _adjust_brightness(bg, 15 if dark else -10),
            "disabled_text": _adjust_brightness(
                fg, -40 if dark else 40,
            ),
            "status": _adjust_brightness(fg, -20 if dark else 20),
            "input_text": text,
            "selected": _adjust_brightness(bg, 20 if dark else -12),
        }
    return {}  # Not enough colors, caller should use fallback


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

def _apply_dark_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#2d2d2d"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e8e8e8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252525"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#383838"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#383838"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e8e8e8"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e8e8e8"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#3c3c3c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e8e8e8"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#5294e2"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def _apply_light_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1f"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#ededf0"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1a1a1f"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1a1a1f"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#e4e4e8"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1a1a1f"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4f8cff"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def _apply_gtk_palette(app: QApplication, scheme: dict[str, str]) -> None:
    """Apply a palette derived from GTK theme colors."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(scheme["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(scheme["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(scheme["base"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(scheme["input_text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(scheme["button"]))
    palette.setColor(QPalette.ColorRole.Mid, QColor(scheme["border"]))
    palette.setColor(
        QPalette.ColorRole.ButtonText, QColor(scheme["button_text"]),
    )
    palette.setColor(
        QPalette.ColorRole.Highlight, QColor(scheme["highlight"]),
    )
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor(scheme["highlight_text"]),
    )
    palette.setColor(
        QPalette.ColorRole.ToolTipBase, QColor(scheme["base"]),
    )
    palette.setColor(
        QPalette.ColorRole.ToolTipText, QColor(scheme["text"]),
    )
    app.setPalette(palette)


# Module-level dict populated by apply_theme() for gui.py to read
active_colors: dict[str, str] = {}

# Spacing scale only. Text always retains the operating system UI font.
_UI_SCALE = 1.0


def ui_scale() -> float:
    return _UI_SCALE


def set_ui_scale(app: QApplication, scale: float) -> None:
    """Re-apply spacing without shrinking the operating system font."""
    global _UI_SCALE
    _UI_SCALE = max(1.0, scale)
    if active_colors:
        _apply_styled_sheet(app, active_colors)


class _SystemThemeWatcher(QObject):
    """Re-apply the theme when the OS signals a palette/theme change.

    Re-entrancy is guarded because apply_theme() itself calls setPalette()
    and setStyleSheet(), which re-emit ApplicationPaletteChange.
    """

    _WATCHED = {QEvent.Type.ApplicationPaletteChange, QEvent.Type.ThemeChange}

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._busy = False

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self._app and not self._busy and event.type() in self._WATCHED:
            self._busy = True
            try:
                apply_theme(self._app)
            except Exception:
                pass
            finally:
                self._busy = False
        return False


def install_theme_watcher(app: QApplication) -> _SystemThemeWatcher:
    if hasattr(app, "_spp_theme_watcher"):
        return app._spp_theme_watcher
    watcher = _SystemThemeWatcher(app)
    app.installEventFilter(watcher)
    app._spp_theme_watcher = watcher
    return watcher


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def apply_theme(app: QApplication) -> None:
    if getattr(app, "_spp_applying_theme", False):
        return
    app._spp_applying_theme = True
    try:
        _apply_theme(app)
    finally:
        app._spp_applying_theme = False


def _apply_theme(app: QApplication) -> None:
    import os

    from photocropper.settings import load_appearance

    apply_system_font(app)
    app.setStyleSheet("")
    appearance = os.environ.get("SPP_THEME", "").lower()
    if appearance not in {"dark", "light"}:
        appearance = load_appearance()
    dark = _is_system_dark_mode() if appearance == "system" else appearance == "dark"

    # Studio colors stay consistent; System follows the OS light/dark choice.
    scheme = dict(_D if dark else _L)
    colors = accent_colors(app)
    scheme.update(highlight=colors["accent"], highlight_text=colors["on_accent"],
                  highlight_hover=colors["hover"], highlight_pressed=colors["pressed"])
    active_colors.update(scheme)
    _apply_gtk_palette(app, scheme)
    _apply_styled_sheet(app, scheme)
    bind_appearance_refresh(app, lambda: apply_theme(app))



# ---------------------------------------------------------------------------
# Stylesheet (hardcoded hex — palette() is unreliable with Fusion on Linux)
# ---------------------------------------------------------------------------

# Dark colors — tuned to blend with Linux Mint-Y-Dark and similar warm-neutral themes
_D = {
    "window": "#2c2c2c",
    "text": "#f1f1f1",
    "base": "#252525",
    "button": "#252525",
    "button_text": "#f1f1f1",
    "border": "#555555",
    "hover": "#4a4a4a",
    "pressed": "#2a2a2a",
    "highlight": "#508fdb",
    "highlight_text": "#111111",
    "highlight_hover": "#6ba4e8",
    "disabled_bg": "#3c3c3c",
    "disabled_text": "#7a7a7a",
    "status": "#b5b5b5",
    "input_text": "#f1f1f1",
    "selected": "#4a4a4a",
}

# Light colors
_L = {
    "window": "#f3f3f3",
    "text": "#222222",
    "base": "#ffffff",
    "button": "#ffffff",
    "button_text": "#222222",
    "border": "#cccccc",
    "hover": "#d4d4d4",
    "pressed": "#bfbfbf",
    "highlight": "#508fdb",
    "highlight_text": "#111111",
    "highlight_hover": "#3f84d4",
    "disabled_bg": "#d4d4d4",
    "disabled_text": "#888888",
    "status": "#626262",
    "input_text": "#222222",
    "selected": "#dddddd",
}


def _apply_styled_sheet(app: QApplication, c: dict[str, str]) -> None:

    def px(value: float) -> int:
        return max(1, round(value * _UI_SCALE))

    app.setStyleSheet(f"""
        /* --- Base --- */
        QWidget {{
            {system_font_css(app)}
            color: {c["text"]};
        }}
        QMainWindow {{
            background-color: {c["window"]};
        }}

        /* --- Drag-and-drop feedback --- */
        QWidget#mainContainer[dropActive="true"] {{
            background-color: {_adjust_brightness(c["base"], 8)};
        }}

        /* --- Controls panel --- */
        QWidget#controlsPanel {{
            background-color: {c["base"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: {px(6)}px;
        }}

        /* --- Buttons --- */
        QPushButton {{
            background-color: {c["button"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: {px(5)}px {px(10)}px;
            color: {c["button_text"]};
            min-height: 0px;
        }}
        QPushButton:hover {{
            background-color: {c["hover"]};
        }}
        QPushButton:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {c["highlight"]};
        }}
        QPushButton:pressed {{
            background-color: {c["pressed"]};
        }}
        QPushButton#processBtn {{
            background-color: {c["highlight"]};
            color: {c["highlight_text"]};
            font-weight: 600;
            padding: {px(6)}px {px(14)}px;
            border-radius: 6px;
            border: 1px solid {c["highlight"]};
            min-height: 0px;
        }}
        QPushButton#processBtn:enabled:focus {{
            border: 1px solid {c["highlight_text"]};
        }}
        QPushButton#processBtn:enabled:pressed {{
            background-color: {c["highlight_pressed"]};
        }}
        QPushButton#processBtn:disabled {{
            background-color: {c["disabled_bg"]};
            color: {c["disabled_text"]};
            border: none;
        }}
        QPushButton#processBtn:hover:!disabled {{
            background-color: {c["highlight_hover"]};
        }}
        QPushButton#colorSwatch {{
            border-radius: 4px;
            min-width: {px(32)}px;
            max-width: {px(32)}px;
            min-height: {px(24)}px;
            max-height: {px(24)}px;
        }}
        QPushButton#rotateBtn {{
            padding: {px(4)}px {px(10)}px;
        }}
        QPushButton#iconBtn {{
            background-color: transparent;
            border: none;
            border-radius: {px(6)}px;
            padding: {px(4)}px;
            min-width: {px(28)}px;
            max-width: {px(28)}px;
            min-height: 0px;
            max-height: {px(28)}px;
        }}
        QPushButton#iconBtn:hover {{
            background-color: {c["hover"]};
        }}
        QPushButton#iconBtn:pressed {{
            background-color: {c["pressed"]};
        }}
        QPushButton#iconBtn[busy="true"] {{
            background-color: {c["highlight"]};
        }}

        /* --- Inputs --- */
        QLineEdit {{
            background-color: {c["base"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: {px(5)}px {px(8)}px;
            color: {c["input_text"]};
            min-height: {px(24)}px;
        }}
        QLineEdit:focus {{
            border-color: {c["highlight"]};
        }}
        QSpinBox, QDoubleSpinBox {{
            background-color: {c["base"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: {px(5)}px {px(8)}px;
            color: {c["input_text"]};
            min-height: {px(24)}px;
        }}
        QSpinBox:focus {{
            border-color: {c["highlight"]};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            border: none;
            background-color: transparent;
            width: {px(14)}px;
        }}
        QCheckBox {{
            color: {c["text"]};
            spacing: {px(6)}px;
        }}
        QCheckBox::indicator {{
            width: {px(16)}px;
            height: {px(16)}px;
            border: 1px solid {c["border"]};
            border-radius: 4px;
            background-color: {c["base"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {c["highlight"]};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c["highlight"]};
            border-color: {c["highlight"]};
        }}
        QComboBox {{
            background-color: {c["button"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: {px(4)}px {px(8)}px;
            color: {c["button_text"]};
            min-height: {px(24)}px;
        }}
        QComboBox:hover {{
            background-color: {c["hover"]};
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c["base"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            selection-background-color: {c["highlight"]};
            selection-color: {c["highlight_text"]};
        }}

        /* --- Preview --- */
        QLabel#previewLabel {{
            border: 1px solid {c["border"]};
            border-radius: 10px;
            background-color: {c["base"]};
            color: {c["status"]};
        }}

        /* --- Results --- */
        QListWidget {{
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 8px;
            background-color: {c["base"]};
            color: {c["text"]};
        }}

        /* --- Status --- */
        QLabel#statusLabel {{
            color: {c["status"]};
            padding: 4px 0px;
        }}

        /* --- Toolbar buttons (boxed for clarity; light up while busy) --- */
        QPushButton#toolbarBtn {{
            background-color: transparent;
            border: 1px solid {c["border"]};
            border-radius: 6px;
            padding: {px(9)}px {px(13)}px;
            color: {c["text"]};
            min-height: {px(24)}px;
        }}
        QPushButton#toolbarBtn:hover {{
            background-color: {c["hover"]};
        }}
        QPushButton#toolbarBtn:pressed {{
            background-color: {c["pressed"]};
        }}
        QPushButton#toolbarBtn[busy="true"] {{
            background-color: {c["highlight"]};
            border-color: {c["highlight"]};
            color: {c["highlight_text"]};
        }}

        /* --- Scrollbars --- */
        QScrollBar:vertical {{
            background-color: {c["base"]};
            width: 10px;
            border: none;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c["border"]};
            border-radius: 5px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {c["hover"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* --- Segmented buttons (one-click pickers) --- */
        QPushButton#segBtn {{
            background-color: {c["button"]};
            border: 1px solid {c["border"]};
            border-radius: 5px;
            padding: {px(4)}px {px(12)}px;
            color: {c["button_text"]};
            min-height: {px(26)}px;
        }}
        QPushButton#segBtn:hover {{
            background-color: {c["hover"]};
        }}
        QPushButton#segBtn:checked {{
            background-color: {c["highlight"]};
            border-color: {c["highlight"]};
            color: {c["highlight_text"]};
        }}
        QPushButton#segBtn:checked:hover {{
            background-color: {c["highlight_hover"]};
        }}

        /* --- Progress bar (sized to swap with the Process button) --- */
        QProgressBar {{
            background-color: {c["base"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            text-align: center;
            color: {c["text"]};
            font-weight: 600;
            min-height: 0px;
        }}
        QProgressBar::chunk {{
            background-color: {c["highlight"]};
            border-radius: 5px;
        }}

        /* --- Group labels inside the controls panel --- */
        QLabel#fieldLabel {{
            color: {c["status"]};
            padding-right: 4px;
        }}
    """)
