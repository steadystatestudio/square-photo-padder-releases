"""QPainter-drawn icons so the UI stays crisp at any DPI and follows the theme."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)


def _blank_pixmap(size: int, dpr: float) -> QPixmap:
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _position_pixmap(position: str, color: QColor, size: int, dpr: float) -> QPixmap:
    pixmap = _blank_pixmap(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(color)
    pen.setWidthF(max(1.0, size / 14))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    margin = size * 0.10
    frame = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    radius = size * 0.10
    painter.drawRoundedRect(frame, radius, radius)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    pad = size * 0.10
    inner = frame.adjusted(pad, pad, -pad, -pad)

    if position == "tiled":
        cell = inner.width() / 3
        block = cell * 0.66
        gap = (cell - block) / 2
        for row in range(3):
            for col in range(3):
                painter.drawRect(QRectF(
                    inner.left() + col * cell + gap,
                    inner.top() + row * cell + gap,
                    block, block,
                ))
    else:
        block = inner.width() * 0.48
        if position == "top-left":
            rect = QRectF(inner.left(), inner.top(), block, block)
        elif position == "top-right":
            rect = QRectF(inner.right() - block, inner.top(), block, block)
        elif position == "bottom-left":
            rect = QRectF(inner.left(), inner.bottom() - block, block, block)
        elif position == "bottom-right":
            rect = QRectF(inner.right() - block, inner.bottom() - block, block, block)
        else:  # center
            rect = QRectF(
                inner.center().x() - block / 2, inner.center().y() - block / 2, block, block,
            )
        painter.drawRect(rect)

    painter.end()
    return pixmap


def make_position_icon(
    position: str, off_color: QColor, on_color: QColor, size: int, dpr: float,
) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_position_pixmap(position, off_color, size, dpr), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_position_pixmap(position, on_color, size, dpr), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def make_rotate_pixmap(
    clockwise: bool, color: QColor, size: int, dpr: float, sweep_offset: float = 0.0,
) -> QPixmap:
    pixmap = _blank_pixmap(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    center = size / 2
    painter.translate(center, center)
    painter.rotate(sweep_offset if clockwise else -sweep_offset)
    if not clockwise:
        painter.scale(-1.0, 1.0)

    radius = size * 0.30
    rect = QRectF(-radius, -radius, 2 * radius, 2 * radius)
    start_angle = 150.0
    sweep = -240.0  # negative = clockwise on screen

    path = QPainterPath()
    path.arcMoveTo(rect, start_angle)
    path.arcTo(rect, start_angle, sweep)
    pen = QPen(color)
    pen.setWidthF(max(1.5, size / 9))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.strokePath(path, pen)

    # Arrowhead at the arc's leading end, aligned with the travel direction.
    end_rad = math.radians(start_angle + sweep)
    tip = QPointF(radius * math.cos(end_rad), -radius * math.sin(end_rad))
    direction = math.degrees(math.atan2(math.cos(end_rad), math.sin(end_rad)))
    head_len = size * 0.22
    head_width = size * 0.16
    painter.translate(tip)
    painter.rotate(direction)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([
        QPointF(head_len, 0.0),
        QPointF(-head_len * 0.5, -head_width),
        QPointF(-head_len * 0.5, head_width),
    ]))

    painter.end()
    return pixmap


def make_rotate_icon(
    clockwise: bool, color: QColor, size: int, dpr: float, sweep_offset: float = 0.0,
) -> QIcon:
    return QIcon(make_rotate_pixmap(clockwise, color, size, dpr, sweep_offset))


def _gear_pixmap(color: QColor, size: int, dpr: float) -> QPixmap:
    pixmap = _blank_pixmap(size, dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    center = size / 2
    outer_r = size * 0.30
    inner_r = size * 0.13
    tooth_count = 8
    tooth_len = size * 0.11
    tooth_half_width = size * 0.055

    # An annulus (ring): two circles with odd-even fill leaves only the
    # band between them, so the hub hole falls out for free.
    ring = QPainterPath()
    ring.setFillRule(Qt.FillRule.OddEvenFill)
    ring.addEllipse(QPointF(center, center), outer_r, outer_r)
    ring.addEllipse(QPointF(center, center), inner_r, inner_r)
    painter.drawPath(ring)

    painter.translate(center, center)
    for index in range(tooth_count):
        painter.save()
        painter.rotate(360.0 / tooth_count * index)
        # Slight overlap into the ring so anti-aliasing doesn't leave a seam.
        tooth = QRectF(
            -tooth_half_width, -(outer_r + tooth_len),
            tooth_half_width * 2, tooth_len + size * 0.02,
        )
        painter.drawRoundedRect(tooth, size * 0.015, size * 0.015)
        painter.restore()

    painter.end()
    return pixmap


def make_gear_icon(color: QColor, size: int, dpr: float) -> QIcon:
    return QIcon(_gear_pixmap(color, size, dpr))


def make_fallback_app_icon(size: int = 256) -> QIcon:
    """Painted stand-in when the bundled icon PNG is missing.

    Mirrors the shipped icon: a centered square with black letterbox bars top
    and bottom (the padding the app adds) on a full-bleed blue plate."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, QColor("#5ba6ec"))
    gradient.setColorAt(1.0, QColor("#3876c2"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    # Square canvas of black padding with a lighter photo band across the
    # middle: black bars top and bottom.
    inset = size * 0.24
    side = size - 2 * inset
    painter.setBrush(QColor("#000000"))
    painter.drawRect(QRectF(inset, inset, side, side))
    band_height = side * 0.46
    band_top = inset + (side - band_height) / 2
    painter.setBrush(QColor("#eceff4"))
    painter.drawRect(QRectF(inset, band_top, side, band_height))

    # Crisp white frame around the squared canvas.
    painter.setPen(QPen(QColor("#ffffff"), size * 0.035))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(inset, inset, side, side))

    painter.end()
    return QIcon(pixmap)
