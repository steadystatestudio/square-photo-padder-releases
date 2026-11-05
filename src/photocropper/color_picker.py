"""The app's own background-color picker.

Qt's stock QColorDialog was too much (tester feedback): 42 basic colors,
HSV/RGB number grids, screen picking, and a manual "Add to Custom Colors"
step. This dialog is one compact panel: a row of common colors, the saved
custom colors, and a small shade square + hue strip + hex box for mixing a
new one. Clicking any swatch applies it immediately; a mixed color is saved
automatically. Everything is drawn by Qt, so it looks and works the same on
Windows and Linux.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from photocropper.desktop_geometry import available_geometry, workarea_provider
from photocropper.settings import load_custom_colors, save_custom_colors
from photocropper.themes import active_colors, ui_scale
from photocropper.window_screen import observe_window_screen

# One row of common backgrounds: neutrals first (most product photos sit on
# white/gray/black), then one of each basic color. Deliberately few — the
# shade picker below covers everything else.
BASIC_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 255, 255),  # white
    (216, 216, 216),  # light gray
    (128, 128, 128),  # gray
    (0, 0, 0),        # black
    (229, 57, 53),    # red
    (251, 140, 0),    # orange
    (253, 216, 53),   # yellow
    (67, 160, 71),    # green
    (30, 136, 229),   # blue
    (142, 36, 170),   # purple
    (236, 64, 122),   # pink
    (109, 76, 65),    # brown
)

MAX_CUSTOM_COLORS = 8


class _Swatch(QPushButton):
    """A flat square of one color; clicking it picks that color."""

    def __init__(self, color: tuple[int, int, int], side: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(side, side)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        r, g, b = color
        border = active_colors.get("border", "#555555")
        highlight = active_colors.get("highlight", "#5294e2")
        self.setStyleSheet(
            f"QPushButton {{ background-color: rgb({r},{g},{b}); border: 1px solid {border}; "
            f"border-radius: 4px; padding: 0px; min-height: 0px; }} "
            f"QPushButton:hover {{ border: 2px solid {highlight}; }}"
        )

    def color(self) -> tuple[int, int, int]:
        return self._color


class _ShadeSquare(QWidget):
    """Saturation/brightness field for the current hue — one click or drag."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hue = 0
        self._sat = 0
        self._val = 255
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumHeight(130)

    def set_color(self, color: QColor) -> None:
        hue, sat, val, _ = color.getHsv()
        if hue >= 0:  # getHsv reports -1 for grays; keep the last hue then
            self._hue = hue
        self._sat = sat
        self._val = val
        self.update()
        self.changed.emit()

    def set_hue(self, hue: int) -> None:
        self._hue = max(0, min(359, hue))
        self.update()
        self.changed.emit()

    def hue(self) -> int:
        return self._hue

    def color(self) -> QColor:
        return QColor.fromHsv(self._hue, self._sat, self._val)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)
        # White→hue across, then transparent→black down: the classic HSV field.
        across = QLinearGradient(rect.topLeft(), rect.topRight())
        across.setColorAt(0.0, QColor(255, 255, 255))
        across.setColorAt(1.0, QColor.fromHsv(self._hue, 255, 255))
        painter.fillRect(rect, across)
        down = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        down.setColorAt(0.0, QColor(0, 0, 0, 0))
        down.setColorAt(1.0, QColor(0, 0, 0))
        painter.fillRect(rect, down)
        painter.setPen(QPen(QColor(active_colors.get("border", "#555555"))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        # Marker outlined in both black and white so it shows on any shade.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = rect.left() + self._sat / 255 * rect.width()
        y = rect.top() + (1 - self._val / 255) * rect.height()
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        painter.drawEllipse(QPointF(x, y), 6, 6)
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
        painter.end()

    def _pick(self, pos: QPointF) -> None:
        rect = self.rect()
        fx = min(1.0, max(0.0, pos.x() / max(1, rect.width() - 1)))
        fy = min(1.0, max(0.0, pos.y() / max(1, rect.height() - 1)))
        self._sat = round(fx * 255)
        self._val = round((1 - fy) * 255)
        self.update()
        self.changed.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pick(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._pick(event.position())


class _HueStrip(QWidget):
    """Vertical rainbow strip; click or drag to set the hue."""

    changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hue = 0
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFixedWidth(round(18 * ui_scale()))

    def set_hue(self, hue: int) -> None:
        self._hue = max(0, min(359, hue))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        for step in range(7):
            gradient.setColorAt(step / 6, QColor.fromHsv((step * 60) % 360, 255, 255))
        painter.fillRect(rect, gradient)
        painter.setPen(QPen(QColor(active_colors.get("border", "#555555"))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        y = rect.top() + self._hue / 359 * rect.height()
        marker = QRectF(rect.left() + 1, y - 2, rect.width() - 1, 4)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawRect(marker)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawRect(marker.adjusted(1, 1, -1, -1))
        painter.end()

    def _pick(self, pos: QPointF) -> None:
        fy = min(1.0, max(0.0, pos.y() / max(1, self.rect().height() - 1)))
        self._hue = round(fy * 359)
        self.update()
        self.changed.emit(self._hue)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pick(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._pick(event.position())


class BackgroundColorDialog(QDialog):
    """Pick a background color in one click (or mix one in a few)."""

    def __init__(self, parent: QWidget | None = None, initial: tuple[int, int, int] = (0, 0, 0)) -> None:
        super().__init__(parent)
        self.setWindowTitle("Background Color")
        self._selected: tuple[int, int, int] | None = None
        self._custom_colors: list[tuple[int, int, int]] = load_custom_colors()
        self._updating_hex = False
        side = max(24, min(40, self.fontMetrics().height() + 8))

        # Row of common colors — one click applies and closes.
        self._basic_swatches: list[_Swatch] = []
        basics_row = QGridLayout()
        self._basics_layout = basics_row
        basics_row.setSpacing(4)
        for index, color in enumerate(BASIC_COLORS):
            swatch = _Swatch(color, side)
            swatch.clicked.connect(lambda _=False, c=color: self._choose(c))
            self._basic_swatches.append(swatch)
            basics_row.addWidget(swatch, 0, index)

        # Saved custom colors + the button that empties them. The whole row
        # hides when there is nothing saved.
        self._custom_swatches: list[_Swatch] = []
        self.clear_colors_btn = QPushButton("Clear colors")
        self.clear_colors_btn.setObjectName("toolbarBtn")
        self.clear_colors_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_colors_btn.clicked.connect(self._clear_custom_colors)
        self._custom_row = QWidget()
        custom_layout = QGridLayout(self._custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(4)
        self._custom_layout = custom_layout
        self._swatch_side = side
        self._rebuild_custom_row()

        # Shade square with the hue strip at its side.
        self.shade_square = _ShadeSquare()
        self.hue_strip = _HueStrip()
        picker_row = QHBoxLayout()
        picker_row.setSpacing(6)
        picker_row.addWidget(self.shade_square, stretch=1)
        picker_row.addWidget(self.hue_strip)

        # Hex box, live preview, and the one button that applies the mix.
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#rrggbb")
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setFixedWidth(self.hex_edit.fontMetrics().horizontalAdvance("#ffffff") + 24)
        self.hex_edit.textEdited.connect(self._hex_edited)
        self.hex_edit.returnPressed.connect(self._use_mixed_color)
        self.preview = QLabel()
        self.preview.setFixedSize(side, side)
        self.use_btn = QPushButton("Use color")
        self.use_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.use_btn.setDefault(True)
        self.use_btn.clicked.connect(self._use_mixed_color)
        mix_row = QGridLayout()
        self._mix_layout = mix_row
        mix_row.setSpacing(6)
        mix_row.addWidget(self.hex_edit, 0, 0)
        mix_row.addWidget(self.preview, 0, 1)
        mix_row.setColumnStretch(2, 1)
        mix_row.addWidget(self.use_btn, 0, 3)

        self._body = QWidget()
        layout = QVBoxLayout(self._body)
        layout.setSpacing(8)
        layout.addLayout(basics_row)
        layout.addWidget(self._custom_row)
        layout.addLayout(picker_row)
        layout.addLayout(mix_row)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setSizeGripEnabled(False)

        self.shade_square.changed.connect(self._mix_changed)
        self.hue_strip.changed.connect(self.shade_square.set_hue)

        self.shade_square.set_color(QColor(*initial))
        self.hue_strip.set_hue(self.shade_square.hue())
        self._fitting = False
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_form)
        self._workarea = workarea_provider(QGuiApplication.instance())
        self._workarea.changed.connect(self._fit_timer.start)
        self._fit_timer.start(0)

    def _fit_form(self) -> None:
        if self._fitting or self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        self._fitting = True
        try:
            area = available_geometry(self, self.screen().availableGeometry())
            cap_width, cap_height = max(1, area.width() - 48), max(1, area.height() - 80)
            side = self._swatch_side
            columns = max(1, min(12, (cap_width - 24) // (side + 4)))
            for index, swatch in enumerate(self._basic_swatches):
                self._basics_layout.addWidget(swatch, index // columns, index % columns)
            for index, swatch in enumerate(self._custom_swatches):
                self._custom_layout.addWidget(swatch, index // columns, index % columns)
            self._custom_layout.addWidget(self.clear_colors_btn, (len(self._custom_swatches) + columns - 1) // columns,
                                          0, 1, max(1, min(columns, 4)))
            hex_width = self.hex_edit.fontMetrics().horizontalAdvance("#ffffff") + 24
            self.hex_edit.setFixedWidth(min(hex_width, max(1, cap_width - 24)))
            needed = hex_width + self.preview.width() + self.use_btn.sizeHint().width() + 3 * 6 + 24
            self._mix_layout.removeWidget(self.use_btn)
            if needed > cap_width:
                self._mix_layout.addWidget(self.use_btn, 1, 0, 1, 4)
            else:
                self._mix_layout.addWidget(self.use_btn, 0, 3)
            self._body.layout().activate()
            wanted = self._body.layout().sizeHint()
            overflow = wanted.height() > cap_height or wanted.width() > cap_width
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if overflow
                                                     else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if overflow
                                                       else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scrollbar = self.style().pixelMetric(self.style().PixelMetric.PM_ScrollBarExtent) if overflow else 0
            self.setFixedSize(min(cap_width, wanted.width() + scrollbar), min(cap_height, wanted.height()))
        finally:
            self._fitting = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        observe_window_screen(self, self._screen_changed)
        self._fit_form()

    def _screen_changed(self, *_):
        self._workarea.refresh()
        self._fit_timer.start(0)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange, QEvent.Type.StyleChange}:
            if hasattr(self, "_fit_timer"):
                self._workarea.refresh()
                self._fit_timer.start(0)

    # --- Result ---

    def selected_color(self) -> tuple[int, int, int] | None:
        return self._selected

    def _choose(self, color: tuple[int, int, int]) -> None:
        self._selected = color
        self.accept()

    # --- Mixed (custom) colors ---

    def _mix_changed(self) -> None:
        color = self.shade_square.color()
        self.hue_strip.set_hue(self.shade_square.hue())
        if not self._updating_hex:
            self.hex_edit.setText(color.name())
        border = active_colors.get("border", "#555555")
        self.preview.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid {border}; border-radius: 4px;"
        )

    def _hex_edited(self, text: str) -> None:
        color = QColor(text if text.startswith("#") else f"#{text}")
        if color.isValid():
            self._updating_hex = True
            try:
                self.shade_square.set_color(color)
            finally:
                self._updating_hex = False

    def _use_mixed_color(self) -> None:
        color = self.shade_square.color()
        rgb = (color.red(), color.green(), color.blue())
        # Saved automatically — no separate "Add to Custom Colors" step.
        colors = [rgb] + [c for c in self._custom_colors if c != rgb]
        save_custom_colors(colors[:MAX_CUSTOM_COLORS])
        self._choose(rgb)

    def _clear_custom_colors(self) -> None:
        self._custom_colors = []
        save_custom_colors([])
        self._rebuild_custom_row()

    def _rebuild_custom_row(self) -> None:
        while self._custom_layout.count():
            item = self._custom_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.clear_colors_btn:
                widget.deleteLater()
        self._custom_swatches = []
        for index, color in enumerate(self._custom_colors):
            swatch = _Swatch(color, self._swatch_side)
            swatch.clicked.connect(lambda _=False, c=color: self._choose(c))
            self._custom_swatches.append(swatch)
            self._custom_layout.addWidget(swatch, 0, index)
        self._custom_layout.addWidget(self.clear_colors_btn, 1, 0)
        self._custom_row.setVisible(bool(self._custom_colors))
        if hasattr(self, "_fit_timer"):
            self._fit_timer.start(0)
