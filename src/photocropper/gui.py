from __future__ import annotations

import io
import math
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from PIL import Image
from PySide6.QtCore import QEasingCurve, QEvent, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from photocropper.color_picker import BackgroundColorDialog
from photocropper.constants import (
    APP_NAME,
    APP_VERSION,
    CUSTOM_SIZE_MAX,
    CUSTOM_SIZE_MIN,
    DEFAULT_BACKGROUND_COLOR,
    KOFI_CONFIGURED,
    KOFI_URL,
    RESIZE_MODE_CUSTOM,
    RESIZE_MODE_ORIGINAL,
    RESIZE_PRESET_SIZES,
    WINDOW_TITLE,
)
from photocropper.dialogs import FileFolderDialog, SettingsDialog
from photocropper.icons import (
    make_position_icon,
    make_rotate_icon,
    make_rotate_pixmap,
)
from photocropper.processor import (
    BatchResult,
    ProcessingOptions,
    ResizeSetting,
    expand_input_paths,
    generate_preview,
    process_images,
)
from photocropper.settings import (
    StoredProcessingPreference,
    StoredResizePreference,
    _settings,
    load_appearance,
    load_custom_size,
    load_processing_preference,
    load_resize_preference,
    load_tooltips_enabled,
    save_appearance,
    save_custom_size,
    save_processing_preference,
    save_resize_preference,
    save_tooltips_enabled,
)
from photocropper.themes import active_colors, apply_theme, set_ui_scale, ui_scale

INITIAL_STATUS = "Click Add Photos or drag images or folders here."

# Initial preview size; the viewport grows with the window.
PREVIEW_SIDE = 420


class SquarePreview(QWidget):
    """Center the largest square viewport inside the available space."""

    def __init__(self, label: QLabel) -> None:
        super().__init__()
        self.label = label
        label.setParent(self)
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(PREVIEW_SIDE, PREVIEW_SIDE)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        side = min(self.width(), self.height())
        self.label.setGeometry((self.width() - side) // 2, (self.height() - side) // 2, side, side)


class FilenameLabel(QLabel):
    def set_filename(self, name: str) -> None:
        self._filename = name
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(
            getattr(self, "_filename", ""), Qt.TextElideMode.ElideMiddle, self.contentsRect().width(),
        ))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()


class SegmentProgress(QProgressBar):
    """Read-only file progress, separate from the action that starts a job."""

    _GAP = 2.0
    _MIN_SEGMENT_PX = 5.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._total = 0
        self._done = 0
        self._progress_text: str | None = None
        self.setFormat("Ready")
        self.setMinimumHeight(44)
        self.setAccessibleName("Photo progress")

    def set_progress(self, done: int, total: int, text: str | None = None) -> None:
        """Update the fill; `text` temporarily replaces the Process label."""
        self._done = done
        self._total = total
        self._progress_text = text
        self.setRange(0, max(1, total))
        self.setValue(done)
        self.setToolTip(text or (f"{done} / {total} photos" if total else "Ready"))
        self.update()

    def progress_value(self) -> int:
        return self._done

    def progress_total(self) -> int:
        return self._total

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        enabled = self.isEnabled()
        face = QColor(active_colors.get("base" if enabled else "disabled_bg", "#252525"))
        text_color = QColor(active_colors.get("text" if enabled else "disabled_text", "#e8e8e8"))

        painter.setPen(QPen(QColor(active_colors.get("border", "#555555"))))
        painter.setBrush(face)
        painter.drawRoundedRect(rect, 6, 6)

        hovered = enabled and self.underMouse()
        highlight = QColor(active_colors.get("highlight_hover" if hovered else "highlight", "#5294e2"))
        track = QColor(active_colors.get("hover", "#4a4a4a"))

        total = self._total
        done = self._done
        # Put the colored track below its label; text never straddles two
        # backgrounds with incompatible contrast requirements.
        inner = rect.adjusted(4, max(4, rect.height() - 10), -4, -4)
        if total >= 1 and inner.width() > 0:
            max_segments = max(1, int((inner.width() + self._GAP) // (self._MIN_SEGMENT_PX + self._GAP)))
            seg_count = min(total, max_segments)
            segment_width = (inner.width() - self._GAP * (seg_count - 1)) / seg_count
            files_per_segment = total / seg_count
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(seg_count):
                x = inner.left() + index * (segment_width + self._GAP)
                painter.setBrush(track)
                painter.drawRoundedRect(QRectF(x, inner.top(), segment_width, inner.height()), 2, 2)
                fraction = min(1.0, (done - index * files_per_segment) / files_per_segment)
                if fraction > 0:
                    painter.setBrush(highlight)
                    painter.drawRoundedRect(
                        QRectF(x, inner.top(), segment_width * fraction, inner.height()), 2, 2
                    )

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(text_color))
        painter.drawText(rect.adjusted(0, 0, 0, -8), Qt.AlignmentFlag.AlignCenter,
                         self._progress_text or (f"{done} / {total} photos" if total else "Ready"))
        painter.end()


def _make_seg_button(label: str, data: object) -> QPushButton:
    btn = QPushButton(label)
    btn.setObjectName("segBtn")
    btn.setCheckable(True)
    btn.setProperty("segData", data)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setAcceptDrops(True)
        self._background_color: tuple[int, int, int] = DEFAULT_BACKGROUND_COLOR
        # Rotation is remembered per photo: each image keeps its own
        # orientation as you flip through the batch and when you process.
        self._rotation_degrees: int = 0
        self._rotation_by_path: dict[Path, int] = {}
        self._preview_path: Path | None = None
        self._preview_paths: list[Path] = []
        self._preview_index: int = 0
        self._pending_paths: list[Path] = []
        self._custom_resize_size: int = load_custom_size(RESIZE_PRESET_SIZES[0])
        self._resize_mode: str = RESIZE_MODE_ORIGINAL
        self._resize_size_px: int | None = None

        # Tooltips: text is recorded per widget so the toggle can restore it
        # without every call site needing to remember the string again.
        self._tooltip_texts: dict[QWidget, str] = {}
        self._tooltips_enabled: bool = load_tooltips_enabled()

        # Debounce timers
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_processing_preference)

        self._scale_timer = QTimer(self)
        self._scale_timer.setSingleShot(True)
        self._scale_timer.setInterval(120)
        self._scale_timer.timeout.connect(self._fit_ui_scale)

        # Segment-by-segment fill when photos are added
        self._load_anim_timer = QTimer(self)
        self._load_anim_timer.timeout.connect(self._advance_load_animation)
        self._load_anim_step = 1
        self._processing = False
        self._cancel_requested = False
        self._close_when_finished = False
        self._batch_running = False
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.close)

        # --- Toolbar row ---
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.add_btn = QPushButton("Add Photos")
        self.add_btn.setObjectName("toolbarBtn")
        self.add_btn.clicked.connect(self._browse)
        self._set_tooltip(self.add_btn, "Add photos or folders to process")

        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.setObjectName("toolbarBtn")
        self.add_folder_btn.clicked.connect(self._browse_folder)
        self._set_tooltip(self.add_folder_btn, "Add the supported photos in one folder")

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("toolbarBtn")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self._clear_photos)
        self._set_tooltip(self.clear_btn, "Remove all loaded photos")

        self.help_btn = QPushButton("Help")
        self.help_btn.setObjectName("toolbarBtn")
        self.help_btn.clicked.connect(self._show_help)
        self._set_tooltip(self.help_btn, f"How to use {APP_NAME}, and about this app")

        toolbar_layout.addWidget(self.add_btn)
        toolbar_layout.addWidget(self.add_folder_btn)
        toolbar_layout.addWidget(self.clear_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.help_btn)

        self.donate_btn: QPushButton | None = None
        if KOFI_CONFIGURED:
            self.donate_btn = QPushButton("Donate")
            self.donate_btn.setObjectName("toolbarBtn")
            self.donate_btn.clicked.connect(self._open_donate)
            self._set_tooltip(self.donate_btn, "Support development on Ko-fi")
            toolbar_layout.addWidget(self.donate_btn)

        # Keep the shared Studio actions in the top-right corner.
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("toolbarBtn")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self._show_settings)
        self._set_tooltip(self.settings_btn, "Settings")
        toolbar_layout.addWidget(self.settings_btn)

        # --- Preview area ---
        self.preview_label = QLabel(INITIAL_STATUS)
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setWordWrap(True)
        self.preview_label.resize(PREVIEW_SIDE, PREVIEW_SIDE)
        self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_area = SquarePreview(self.preview_label)

        # Window shortcuts work from buttons and checkboxes; the editor
        # event filter reserves these keys for normal text/number editing.
        self._review_shortcuts = []
        for key, action in (
            (Qt.Key.Key_Left, lambda: self._rotate(-90)),
            (Qt.Key.Key_Right, lambda: self._rotate(90)),
            (Qt.Key.Key_Up, lambda: self._show_preview_at(self._preview_index - 1)),
            (Qt.Key.Key_Down, lambda: self._show_preview_at(self._preview_index + 1)),
            (Qt.Key.Key_Return, self._save_current_photo),
            (Qt.Key.Key_Enter, self._save_current_photo),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda action=action: self._review_action(action))
            self._review_shortcuts.append(shortcut)

        # Keep a stable metadata row while browsing.
        self.preview_counter = QLabel("")
        self.preview_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_counter.setFixedHeight(self.preview_counter.fontMetrics().height() + 4)
        self._set_tooltip(self.preview_counter, "Up/Down arrows browse photos")

        self.filename_label = FilenameLabel()
        self.filename_label.setObjectName("statusLabel")
        self.filename_label.setTextFormat(Qt.TextFormat.PlainText)
        self.filename_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.metadata_label = QLabel()
        self.metadata_label.setObjectName("statusLabel")
        metadata_row = QHBoxLayout()
        metadata_row.addWidget(self.filename_label, 1)
        metadata_row.addWidget(self.metadata_label)
        metadata_row.addWidget(self.preview_counter)
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(self.preview_area, stretch=1)
        preview_layout.addLayout(metadata_row)

        # --- Size row (segmented) ---
        size_label = QLabel("Size")
        size_label.setObjectName("fieldLabel")
        self._resize_group = QButtonGroup(self)
        self._resize_group.setExclusive(True)
        self._resize_buttons: list[QPushButton] = []

        def _add_size(label: str, data: object, tooltip: str) -> QPushButton:
            btn = _make_seg_button(label, data)
            btn.clicked.connect(lambda _, d=data: self._handle_resize_choice(d))
            self._resize_group.addButton(btn)
            self._resize_buttons.append(btn)
            self._set_tooltip(btn, tooltip)
            return btn

        self.custom_size_spin = QSpinBox()
        self.custom_size_spin.setRange(CUSTOM_SIZE_MIN, CUSTOM_SIZE_MAX)
        self.custom_size_spin.setValue(self._custom_resize_size)
        # Right-aligned digits in a fixed box: numbers enter at the right
        # edge and fill leftward as you type (tester feedback).
        self.custom_size_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.custom_size_spin.setFixedWidth(90)
        self.custom_size_spin.valueChanged.connect(self._custom_size_changed)
        self.custom_size_spin.editingFinished.connect(self._custom_size_committed)
        self._set_tooltip(self.custom_size_spin, "Custom square size in pixels")

        row_size = QHBoxLayout()
        row_size.setSpacing(4)
        row_size.addWidget(size_label)
        row_size.addWidget(_add_size("Original", RESIZE_MODE_ORIGINAL, "Keep the original resolution"))
        for size_px in sorted(RESIZE_PRESET_SIZES, reverse=True):
            row_size.addWidget(_add_size(str(size_px), size_px, f"Resize to {size_px}px square"))
        self._custom_btn = _add_size("Custom", RESIZE_MODE_CUSTOM, "Use a custom square size")
        row_size.addWidget(self._custom_btn)
        row_size.addWidget(self.custom_size_spin)
        row_size.addStretch()

        # --- Background + Rotation (single row) ---
        bg_label = QLabel("Background")
        bg_label.setObjectName("fieldLabel")
        self.color_swatch = QPushButton()
        self.color_swatch.setObjectName("colorSwatch")
        self.color_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_swatch.clicked.connect(self._pick_background_color)
        self._set_tooltip(self.color_swatch, "Choose the background color")

        rotation_label = QLabel("Rotate")
        rotation_label.setObjectName("fieldLabel")
        self.rotate_ccw_btn = QPushButton()
        self.rotate_ccw_btn.setObjectName("rotateBtn")
        self.rotate_ccw_btn.clicked.connect(lambda: self._rotate(-90))
        self._set_tooltip(self.rotate_ccw_btn, "Rotate left 90° (Left arrow)")
        self.rotate_cw_btn = QPushButton()
        self.rotate_cw_btn.setObjectName("rotateBtn")
        self.rotate_cw_btn.clicked.connect(lambda: self._rotate(90))
        self._set_tooltip(self.rotate_cw_btn, "Rotate right 90° (Right arrow)")

        self.overwrite_check = QCheckBox("Overwrite")
        # Indicator on the right of the label (tester feedback).
        self.overwrite_check.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._set_tooltip(
            self.overwrite_check, "Replace the source .jpg photo; other originals are kept and saved as JPEG copies"
        )

        row_bg = QHBoxLayout()
        row_bg.setSpacing(4)
        row_bg.addWidget(bg_label)
        row_bg.addWidget(self.color_swatch)
        row_bg.addSpacing(20)
        row_bg.addWidget(rotation_label)
        row_bg.addWidget(self.rotate_ccw_btn)
        row_bg.addWidget(self.rotate_cw_btn)
        row_bg.addSpacing(20)
        row_bg.addWidget(self.overwrite_check)
        row_bg.addStretch()

        # --- Watermark: controls in the panel; the text input is a long
        # window-wide bar just above the Process button (tester feedback) ---
        self.watermark_input = QLineEdit()
        self.watermark_input.setPlaceholderText("Watermark")
        self.watermark_input.setMaxLength(100)
        self._set_tooltip(self.watermark_input, "Optional watermark text, blended into the photo")

        self._watermark_size_group = QButtonGroup(self)
        self._watermark_size_group.setExclusive(True)
        self._watermark_size_buttons: dict[str, QPushButton] = {}
        _watermark_size_tooltips = {
            "small": "Small watermark text",
            "medium": "Medium watermark text",
            "large": "Large watermark text",
        }
        for short, data in (("S", "small"), ("M", "medium"), ("L", "large")):
            btn = _make_seg_button(short, data)
            btn.clicked.connect(lambda _, d=data: self._set_watermark_size(d))
            self._watermark_size_group.addButton(btn)
            self._watermark_size_buttons[data] = btn
            self._set_tooltip(btn, _watermark_size_tooltips[data])

        self._watermark_position_group = QButtonGroup(self)
        self._watermark_position_group.setExclusive(True)
        self._watermark_position_buttons: dict[str, QPushButton] = {}
        _watermark_position_tooltips = {
            "top-left": "Place watermark top left",
            "top-right": "Place watermark top right",
            "center": "Place watermark in the center",
            "bottom-left": "Place watermark bottom left",
            "bottom-right": "Place watermark bottom right",
            "tiled": "Tile the watermark across the photo",
        }
        for data in ("top-left", "top-right", "center", "bottom-left", "bottom-right", "tiled"):
            btn = _make_seg_button("", data)
            btn.clicked.connect(lambda _, d=data: self._set_watermark_position(d))
            self._watermark_position_group.addButton(btn)
            self._watermark_position_buttons[data] = btn
            self._set_tooltip(btn, _watermark_position_tooltips[data])

        watermark_label = QLabel("Watermark")
        watermark_label.setObjectName("fieldLabel")
        row_watermark = QHBoxLayout()
        row_watermark.setSpacing(4)
        row_watermark.addWidget(watermark_label)
        for btn in self._watermark_size_buttons.values():
            row_watermark.addWidget(btn)
        row_watermark.addSpacing(6)
        for btn in self._watermark_position_buttons.values():
            row_watermark.addWidget(btn)
        row_watermark.addStretch()

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(8)
        controls_layout.addLayout(row_size)
        controls_layout.addLayout(row_bg)
        controls_layout.addLayout(row_watermark)

        controls_widget = QWidget()
        controls_widget.setObjectName("controlsPanel")
        controls_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        controls_widget.setLayout(controls_layout)
        self.controls_widget = controls_widget

        # Actions keep a stable position; progress remains visible underneath.
        self.process_btn = QPushButton("Process All")
        self.process_btn.setObjectName("processBtn")
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self._process_or_cancel)
        self._set_tooltip(self.process_btn, "Pad and save all loaded photos")
        self.save_photo_btn = QPushButton("Save Photo")
        self.save_photo_btn.setEnabled(False)
        self.save_photo_btn.clicked.connect(self._save_current_photo)
        self._set_tooltip(self.save_photo_btn, "Pad and save the displayed photo (Enter)")
        self.progress_bar = SegmentProgress()

        # --- Status: one permanent summary line (no results box below) ---
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        # Fixed one-line footprint so the preview never jumps, and
        # long messages clip instead of stretching the window wider.
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status_label.setFixedHeight(self.status_label.fontMetrics().height() + 8)

        # --- Main layout ---
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(toolbar_layout)
        layout.addLayout(preview_layout, stretch=1)
        layout.addWidget(controls_widget)
        # One long window-wide watermark bar, just above Process.
        layout.addWidget(self.watermark_input)
        save_row = QHBoxLayout()
        left_balance = QWidget()
        left_balance.setMinimumWidth(self.save_photo_btn.sizeHint().width())
        save_row.addWidget(left_balance, 1)
        save_row.addWidget(self.process_btn)
        right_actions = QHBoxLayout()
        right_actions.addStretch()
        right_actions.addWidget(self.save_photo_btn)
        save_row.addLayout(right_actions, 1)
        layout.addLayout(save_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        self.container = QWidget()
        self.container.setObjectName("mainContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.container.setLayout(layout)
        self.setCentralWidget(self.container)

        self._restore_resize_preference()
        self._restore_processing_preference()
        had_saved_geometry = _settings().value("window/geometry") is not None
        self.resize(self.sizeHint())
        self._restore_geometry()
        self._rebuild_icons()

        if not had_saved_geometry:
            self._center_on_screen()

        # Debounced preview refresh for text input
        self.watermark_input.textChanged.connect(self._schedule_preview_refresh)
        # Debounced save for text input
        self.watermark_input.textChanged.connect(self._schedule_save_preference)
        for editor in (self.watermark_input, self.custom_size_spin, self.custom_size_spin.lineEdit()):
            editor.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ShortcutOverride and event.key() in {
            Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Return, Qt.Key.Key_Enter,
        }:
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _review_action(self, action) -> None:
        if not self._processing and self._preview_path is not None:
            action()

    def _set_processing(self, busy: bool) -> None:
        self._processing = busy
        if busy:
            self._cancel_requested = False
            self._close_when_finished = False
        for widget in (
            self.add_btn, self.add_folder_btn, self.clear_btn, self.settings_btn, self.controls_widget,
            self.watermark_input, self.save_photo_btn,
        ):
            widget.setEnabled(not busy)
        has_photos = bool(self._preview_paths)
        for widget in (self.clear_btn, self.save_photo_btn):
            widget.setEnabled(not busy and has_photos)
        self.process_btn.setText("Cancel" if busy else "Process All")
        self.process_btn.setEnabled(busy or has_photos)
        self._set_tooltip(
            self.process_btn,
            "Stop safely after the current photo" if busy else "Pad and save all loaded photos",
        )
        if not busy and self._close_when_finished:
            self._close_when_finished = False
            self._close_timer.start(0)

    def _request_cancel(self) -> None:
        if not self._processing or self._cancel_requested:
            return
        self._cancel_requested = True
        self.process_btn.setEnabled(False)
        self.process_btn.setText("Stopping…")
        self.progress_bar.set_progress(
            self.progress_bar.progress_value(), self.progress_bar.progress_total(), text="Stopping…",
        )
        self._set_status("Stopping safely after the current photo…")

    def _process_or_cancel(self) -> None:
        if self._processing:
            self._request_cancel()
        else:
            self._process_pending()

    def _save_current_photo(self) -> None:
        if self._processing or self._preview_path is None:
            return
        path = self._preview_path
        self._stop_load_animation()
        self._set_processing(True)
        try:
            batch = self.process_paths([path])
            if batch.success_count:
                result = batch.results[0]
                self._set_status(f"Saved {result.destination_path.name}")
                if result.destination_path == path:
                    self._rotation_by_path.pop(path, None)
                    self._rotation_degrees = 0
                self._refresh_preview()
            self._update_metadata()
        finally:
            self._set_processing(False)

    # --- Browse ---

    def _browse(self) -> None:
        settings = _settings()
        last_dir = settings.value("browse/last_directory", "")
        dialog = FileFolderDialog(self, "Select Images or Folders", last_dir)
        self._set_toolbar_busy(self.add_btn, True)
        try:
            accepted = dialog.exec()
        finally:
            self._set_toolbar_busy(self.add_btn, False)
        if accepted:
            paths = dialog.selected_paths()
            if paths:
                anchor = paths[0] if paths[0].is_dir() else paths[0].parent
                settings.setValue("browse/last_directory", str(anchor))
                self._open_paths(paths)

    def _browse_folder(self) -> None:
        settings = _settings()
        folder = QFileDialog.getExistingDirectory(
            self, "Add Folder", settings.value("browse/last_directory", "")
        )
        if folder:
            settings.setValue("browse/last_directory", folder)
            self._open_paths([Path(folder)])

    def _clear_photos(self) -> None:
        if self._processing:
            return
        self._flash_toolbar_busy(self.clear_btn)
        self._stop_load_animation()
        self._pending_paths = []
        self._preview_paths = []
        self._preview_index = 0
        self._preview_path = None
        self._rotation_by_path = {}
        self._rotation_degrees = 0
        self.preview_label.clear()
        self.preview_label.setText(INITIAL_STATUS)
        self._update_preview_counter()
        self._update_metadata()
        self.save_photo_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._set_status("")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self._set_tooltip(self.status_label, text)

    # --- Tooltips ---

    def _set_tooltip(self, widget: QWidget, text: str) -> None:
        self._tooltip_texts[widget] = text
        widget.setToolTip(text if self._tooltips_enabled else "")

    def _set_tooltips_enabled(self, enabled: bool) -> None:
        self._tooltips_enabled = enabled
        for widget, text in self._tooltip_texts.items():
            widget.setToolTip(text if enabled else "")
        save_tooltips_enabled(enabled)

    # --- Toolbar busy highlight (button lights up while its action runs) ---

    def _set_toolbar_busy(self, btn: QPushButton, busy: bool) -> None:
        btn.setProperty("busy", busy)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _flash_toolbar_busy(self, btn: QPushButton, duration_ms: int = 300) -> None:
        """Momentary highlight for actions that finish instantly."""
        self._set_toolbar_busy(btn, True)
        timer = QTimer(btn)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._set_toolbar_busy(btn, False))
        timer.timeout.connect(timer.deleteLater)
        timer.start(duration_ms)

    def _open_paths(self, paths: list[Path]) -> None:
        if self._processing:
            return
        expanded = expand_input_paths(paths)
        # Process exactly the selection shown in the preview, even on repeat saves.
        self._pending_paths = list(expanded)
        self._preview_paths = expanded
        self._preview_index = 0
        # A fresh selection starts unrotated; rotations are per photo.
        self._rotation_by_path = {}
        self._rotation_degrees = 0
        if expanded:
            self._preview_path = expanded[0]
            self._refresh_preview()
        else:
            self._preview_path = None
            self.preview_label.setText(INITIAL_STATUS)
        self._update_preview_counter()
        self._update_metadata()
        count = len(expanded)
        self.process_btn.setEnabled(count > 0)
        self.save_photo_btn.setEnabled(count > 0)
        self.clear_btn.setEnabled(count > 0)
        if count > 0:
            self._start_load_animation(count)
        else:
            self._stop_load_animation()

    # --- Load animation (the button's segments fill as photos are added) ---

    def _start_load_animation(self, count: int) -> None:
        self._load_anim_timer.stop()
        self.progress_bar.set_progress(0, count)
        # Step through several files per tick on big batches so the fill
        # always completes in roughly half a second, whatever the count.
        self._load_anim_step = max(1, math.ceil(count / 36))
        self._load_anim_timer.setInterval(max(16, min(80, 600 * self._load_anim_step // count)))
        self._load_anim_timer.start()

    def _advance_load_animation(self) -> None:
        total = self.progress_bar.progress_total()
        done = min(total, self.progress_bar.progress_value() + self._load_anim_step)
        self.progress_bar.set_progress(done, total)
        if done >= total:
            self._load_anim_timer.stop()

    def _stop_load_animation(self) -> None:
        self._load_anim_timer.stop()
        if not self._processing:
            self.progress_bar.set_progress(0, 0)

    def _process_pending(self) -> None:
        if self._processing or not self._pending_paths:
            return
        self._load_anim_timer.stop()
        self._set_processing(True)
        QApplication.processEvents()
        try:
            self.process_paths(self._pending_paths)
        finally:
            self._set_processing(False)

    # --- Toolbar actions ---

    def _show_help(self) -> None:
        about = (
            f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
            "Pad photos to square without cropping anything out.<br><br>"
            "No cloud.<br>"
            "Squared copies are saved next to the originals."
        )
        if KOFI_CONFIGURED:
            about += f'<br><br><a href="{KOFI_URL}">Support on Ko-fi</a>'

        self._set_toolbar_busy(self.help_btn, True)
        try:
            QMessageBox.information(
                self,
                f"{APP_NAME} Help & About",
                about + "<br><br><hr><br>"
                "<b>How to use:</b><br><br>"
                "1. Click <b>Add Photos</b> to pick images or folders, "
                "or drag them onto the window.<br>"
                "2. Pick a size, background, and optional watermark/rotation.<br>"
                "3. Click <b>Process All</b> to pad all loaded images to square.<br><br>"
                "While processing, the button becomes <b>Cancel</b>. Cancel or close "
                "finishes the current photo safely, then leaves the remaining photos untouched.<br><br>"
                "<b>Keyboard:</b> Left/Right rotate; Up/Down browse photos. "
                "Enter or <b>Save Photo</b> saves the displayed photo and stays on it. "
                "Shortcuts leave text and size editing alone.<br><br>"
                "<b>Rotation</b> is remembered per photo — rotate each image as "
                "you flip through them and every photo keeps its own orientation.<br><br>"
                "<b>Background</b> opens the color picker: click a color to use it, "
                "or mix your own — mixed colors are saved in the picker and "
                "<b>Clear colors</b> empties them.<br><br>"
                "<b>Choose a size for your destination</b><br>"
                "Presets <b>1000</b>, <b>1080</b>, <b>1600</b> and <b>2048</b> "
                "set the maximum square side in pixels. <b>Original</b> keeps the "
                "photo's resolution within the app's image limits. Smaller photos "
                "are never upscaled.<br><br>"
                "Square padding is useful when your destination accepts square images; "
                "these are not marketplace compliance presets. Check current listing rules. "
                "<b>eBay</b> disallows added borders, text and watermarks. "
                "<b>Poshmark</b> uses 3:4 portrait cover photos, so a square export "
                "may need a different crop there.<br><br>"
                "Squared copies are saved next to the originals as "
                "<code>name (1).jpg</code>. Enable <b>Overwrite</b> to replace "
                "the source <code>name.jpg</code> instead. Other formats are kept "
                "and produce a JPEG copy; a different existing photo is never "
                "replaced, so a numbered copy is used when needed.",
            )
        finally:
            self._set_toolbar_busy(self.help_btn, False)

    def _show_settings(self) -> None:
        self._set_toolbar_busy(self.settings_btn, True)
        try:
            dialog = SettingsDialog(self, self._tooltips_enabled, load_appearance())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._set_tooltips_enabled(dialog.tooltips_check.isChecked())
                save_appearance(dialog.appearance.currentData())
                apply_theme(QApplication.instance())
                self._rebuild_icons()
                self._update_color_swatch()
        finally:
            self._set_toolbar_busy(self.settings_btn, False)

    def _open_donate(self) -> None:
        from PySide6.QtCore import QUrl
        if self.donate_btn is not None:
            self._flash_toolbar_busy(self.donate_btn, duration_ms=600)
        QDesktopServices.openUrl(QUrl(KOFI_URL))

    # --- Processing ---

    def current_processing_options(self) -> ProcessingOptions:
        return ProcessingOptions(
            resize=self.current_resize_setting(),
            background_color=self._background_color,
            watermark_text=self.watermark_input.text(),
            watermark_size=self._current_watermark_size(),
            watermark_position=self._current_watermark_position(),
            rotation_degrees=self._rotation_degrees,
            overwrite=self.overwrite_check.isChecked(),
        )

    def process_paths(self, paths: Iterable[Path]) -> BatchResult:
        if self._batch_running:
            return BatchResult(results=[])
        unique_paths = list(dict.fromkeys(Path(path) for path in paths))
        if not unique_paths:
            batch = BatchResult(results=[])
            self._set_status("No files were provided.")
            return batch

        owns_processing = not self._processing
        if owns_processing:
            self._set_processing(True)
        self._batch_running = True
        try:
            options = self.current_processing_options()
            # Each photo carries its own rotation; the batch base is unrotated and
            # per-path overrides supply each image's remembered orientation.
            batch_options = replace(options, rotation_degrees=0)
            total = len(expand_input_paths(unique_paths))
            resize_label = options.resize.output_label
            self._set_status(f"Processing {total} item(s) with size {resize_label}…")
            self.progress_bar.set_progress(0, total, text=f"Processing 0 / {total}" if total else None)
            QApplication.processEvents()

            def _on_progress(current: int, _total: int, _path: Path) -> None:
                label = "Stopping…" if self._cancel_requested else f"Processing {current} / {total}"
                self.progress_bar.set_progress(current, total, text=label)
                QApplication.processEvents()

            batch = process_images(
                unique_paths,
                batch_options,
                progress=_on_progress,
                rotation_overrides=dict(self._rotation_by_path),
                cancelled=lambda: self._cancel_requested,
            )
            # Only completed files fill the segments when a batch is stopped.
            self.progress_bar.set_progress(len(batch.results), total)
            replaced = {
                result.source_path for result in batch.results
                if result.success and result.destination_path == result.source_path
            }
            for path in replaced:
                self._rotation_by_path.pop(path, None)
            if self._preview_path in replaced:
                self._rotation_degrees = 0
                self._refresh_preview()
                self._update_metadata()
            self._render_results(batch, options.resize, total)
            self._save_processing_preference()
            return batch
        finally:
            self._batch_running = False
            if owns_processing:
                self._set_processing(False)

    def _render_results(self, batch: BatchResult, resize_setting: ResizeSetting, total: int | None = None) -> None:
        if batch.cancelled:
            total = total if total is not None else len(batch.results)
            self._set_status(
                f"Stopped after {len(batch.results)} of {total} file(s): "
                f"{batch.success_count} succeeded, {batch.failure_count} failed; "
                f"{total - len(batch.results)} not processed."
            )
        elif not batch.results:
            self._set_status("No files were processed.")
            return
        else:
            summary = (
                f"Finished {len(batch.results)} file(s): "
                f"{batch.success_count} succeeded, {batch.failure_count} failed. "
                f"Size: {resize_setting.output_label}."
            )
            self._set_status(summary)

        if batch.failure_count:
            # No per-file results box anymore; surface the failures here.
            failed = [r for r in batch.results if not r.success]
            lines = "\n".join(
                f"{r.source_path.name} — {r.error or 'Unknown error'}" for r in failed[:12]
            )
            if len(failed) > 12:
                lines += f"\n… and {len(failed) - 12} more"
            QMessageBox.warning(
                self, APP_NAME, f"{len(failed)} file(s) could not be processed:\n\n{lines}"
            )

    # --- Resize ---

    def current_resize_setting(self) -> ResizeSetting:
        if self._resize_mode == RESIZE_MODE_ORIGINAL:
            return ResizeSetting.original()
        if self._resize_mode == RESIZE_MODE_CUSTOM:
            return ResizeSetting.custom(int(self._resize_size_px or self._custom_resize_size))
        if self._resize_size_px is not None:
            return ResizeSetting.preset(int(self._resize_size_px))
        return ResizeSetting.original()

    def _handle_resize_choice(self, data: object) -> None:
        if data == RESIZE_MODE_ORIGINAL:
            self._set_resize_selection(RESIZE_MODE_ORIGINAL, None, save=True)
            return
        if data == RESIZE_MODE_CUSTOM:
            self.apply_custom_resize(self.custom_size_spin.value())
            return
        self._set_resize_selection(f"preset:{data}", int(data), save=True)

    def _custom_size_changed(self, value: int) -> None:
        self._custom_resize_size = int(value)
        if self._resize_mode == RESIZE_MODE_CUSTOM:
            self._resize_size_px = int(value)
            self._schedule_preview_refresh()

    def _custom_size_committed(self) -> None:
        save_custom_size(self._custom_resize_size)
        if self._resize_mode == RESIZE_MODE_CUSTOM:
            save_resize_preference(
                StoredResizePreference(mode=RESIZE_MODE_CUSTOM, size_px=self._custom_resize_size)
            )

    def _set_resize_selection(
        self, mode: str, size_px: int | None, save: bool,
    ) -> None:
        self._resize_mode = mode
        self._resize_size_px = size_px
        self._sync_resize_buttons()
        self._refresh_preview()
        if save:
            if mode == RESIZE_MODE_ORIGINAL:
                save_resize_preference(StoredResizePreference(mode=mode, size_px=None))
            else:
                save_resize_preference(StoredResizePreference(mode=mode, size_px=size_px))

    def _sync_resize_buttons(self) -> None:
        target: object
        if self._resize_mode == RESIZE_MODE_ORIGINAL:
            target = RESIZE_MODE_ORIGINAL
        elif self._resize_mode == RESIZE_MODE_CUSTOM:
            target = RESIZE_MODE_CUSTOM
        else:
            target = self._resize_size_px
        for btn in self._resize_buttons:
            btn.setChecked(btn.property("segData") == target)

    def apply_custom_resize(self, size_px: int, save_preference: bool = True) -> None:
        self._custom_resize_size = int(size_px)
        if self.custom_size_spin.value() != int(size_px):
            self.custom_size_spin.blockSignals(True)
            self.custom_size_spin.setValue(int(size_px))
            self.custom_size_spin.blockSignals(False)
        if save_preference:
            save_custom_size(int(size_px))
        self._set_resize_selection(RESIZE_MODE_CUSTOM, int(size_px), save=save_preference)

    def _restore_resize_preference(self) -> None:
        preference = load_resize_preference()
        if preference.mode == RESIZE_MODE_CUSTOM and preference.size_px:
            self.apply_custom_resize(int(preference.size_px), save_preference=False)
            return
        if preference.mode == RESIZE_MODE_ORIGINAL or not preference.size_px:
            self._set_resize_selection(RESIZE_MODE_ORIGINAL, None, save=False)
            return
        if int(preference.size_px) not in RESIZE_PRESET_SIZES:
            # Preset removed in an update (e.g. old 1200): keep the size as custom.
            self.apply_custom_resize(int(preference.size_px), save_preference=False)
            return
        self._set_resize_selection(f"preset:{preference.size_px}", int(preference.size_px), save=False)

    # --- Watermark selection ---

    def _current_watermark_size(self) -> str:
        btn = self._watermark_size_group.checkedButton()
        return str(btn.property("segData")) if btn else "medium"

    def _current_watermark_position(self) -> str:
        btn = self._watermark_position_group.checkedButton()
        return str(btn.property("segData")) if btn else "bottom-right"

    def _set_watermark_size(self, data: str) -> None:
        btn = self._watermark_size_buttons.get(data)
        if btn:
            btn.setChecked(True)
        self._refresh_preview()
        self._save_processing_preference()

    def _set_watermark_position(self, data: str) -> None:
        btn = self._watermark_position_buttons.get(data)
        if btn:
            btn.setChecked(True)
        self._refresh_preview()
        self._save_processing_preference()

    # --- Background color ---

    def _set_background_color(self, color: tuple[int, int, int]) -> None:
        self._background_color = color
        self._update_color_swatch()
        self._refresh_preview()
        self._save_processing_preference()

    def _pick_background_color(self) -> None:
        dialog = BackgroundColorDialog(self, self._background_color)
        if dialog.exec():
            chosen = dialog.selected_color()
            if chosen is not None:
                self._set_background_color(chosen)

    def _update_color_swatch(self) -> None:
        r, g, b = self._background_color
        w, h = round(32 * ui_scale()), round(24 * ui_scale())
        self.color_swatch.setStyleSheet(
            f"QPushButton#colorSwatch {{ background-color: rgb({r},{g},{b}); border: 1px solid palette(mid); "
            f"border-radius: 4px; min-width: {w}px; max-width: {w}px; min-height: {h}px; max-height: {h}px; }}"
        )

    # --- Rotation ---

    def _rotate(self, degrees: int) -> None:
        if self._processing or self._preview_path is None:
            return
        self._rotation_degrees = (self._rotation_degrees + degrees) % 360
        # Remember this rotation against the photo currently shown so each
        # image in the batch keeps its own orientation.
        if self._preview_path is not None:
            if self._rotation_degrees:
                self._rotation_by_path[self._preview_path] = self._rotation_degrees
            else:
                self._rotation_by_path.pop(self._preview_path, None)
        clockwise = degrees > 0
        self._animate_rotate_button(
            self.rotate_cw_btn if clockwise else self.rotate_ccw_btn, clockwise,
        )
        self._refresh_preview()

    def _animate_rotate_button(self, btn: QPushButton, clockwise: bool) -> None:
        color = QColor(active_colors.get("text", "#e8e8e8"))
        size = self._icon_px
        dpr = self.devicePixelRatioF()
        old = getattr(btn, "_swing_anim", None)
        if old is not None:
            old.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(90.0)
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(
            lambda v: btn.setIcon(QIcon(make_rotate_pixmap(clockwise, color, size, dpr, float(v))))
        )
        anim.finished.connect(lambda: btn.setIcon(make_rotate_icon(clockwise, color, size, dpr)))
        btn._swing_anim = anim
        anim.start()

    # --- Theme-following icons ---

    def _rebuild_icons(self) -> None:
        off_color = QColor(active_colors.get("text", "#e8e8e8"))
        on_color = QColor(active_colors.get("highlight_text", "#ffffff"))
        dpr = self.devicePixelRatioF()
        self._icon_px = max(14, QFontMetrics(QApplication.font()).height())
        icon_size = QSize(self._icon_px, self._icon_px)
        for position, btn in self._watermark_position_buttons.items():
            btn.setIcon(make_position_icon(position, off_color, on_color, self._icon_px, dpr))
            btn.setIconSize(icon_size)
        for btn, clockwise in ((self.rotate_ccw_btn, False), (self.rotate_cw_btn, True)):
            btn.setIcon(make_rotate_icon(clockwise, off_color, self._icon_px, dpr))
            btn.setIconSize(icon_size)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            # Can fire mid-construction, before the buttons exist.
            if hasattr(self, "rotate_cw_btn"):
                self._rebuild_icons()
        super().changeEvent(event)

    # --- Preview ---

    def _schedule_preview_refresh(self) -> None:
        self._preview_timer.start()

    def _schedule_save_preference(self) -> None:
        self._save_timer.start()

    def _refresh_preview(self) -> None:
        if self._preview_path is None or not self._preview_path.is_file():
            if self._preview_path is not None:
                self.preview_label.setText("Preview unavailable (file missing)")
            return

        try:
            preview_size = max(280, min(self.preview_label.width(), self.preview_label.height(), 1600))
            options = self.current_processing_options()
            pil_image = generate_preview(self._preview_path, options, preview_size=preview_size)
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            buf.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(buf.read())
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            self.preview_label.setText(f"Preview unavailable ({detail})")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scale_timer.start()
        if self._preview_path is not None:
            self._preview_timer.start()

    def _update_metadata(self) -> None:
        path = self._preview_path
        self.filename_label.set_filename(path.name if path else "")
        self._set_tooltip(self.filename_label, path.name if path else "")
        if path is None:
            self.metadata_label.clear()
            return
        dimensions = image_format = file_size = "—"
        try:
            size = float(path.stat().st_size)
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024 or unit == "GB":
                    file_size = f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
                    break
                size /= 1024
        except OSError:
            pass
        try:
            with Image.open(path) as image:
                dimensions = f"{image.width} × {image.height}"
                image_format = image.format or "—"
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
        self.metadata_label.setText(f"{dimensions} · {image_format} · {file_size}")

    # --- Fit-to-width UI scaling ---

    _SCALE_MIN = 0.5

    def _fit_ui_scale(self) -> None:
        """Shrink fonts and control paddings so the widest row fits the
        window width (large system fonts on Linux otherwise clip button
        text); restore toward native size when the window widens again."""
        needed = self.container.layout().minimumSize().width()
        available = self.container.width()
        if needed <= 0 or available <= 0:
            return
        current = ui_scale()
        target = max(self._SCALE_MIN, min(1.0, current * available / needed))
        if abs(target - current) < 0.02:
            return
        set_ui_scale(QApplication.instance(), target)
        self.custom_size_spin.setFixedWidth(round(90 * target))
        self._rebuild_icons()
        self._update_color_swatch()
        # Layout metrics settle after restyling; re-check until converged.
        self._scale_timer.start()

    def _update_preview_counter(self) -> None:
        total = len(self._preview_paths)
        show = total > 1
        self.preview_counter.setText(f"{self._preview_index + 1} / {total}" if show else "")

    def _show_preview_at(self, index: int) -> None:
        if self._processing or not self._preview_paths:
            return
        self._preview_index = index % len(self._preview_paths)
        self._preview_path = self._preview_paths[self._preview_index]
        # Reflect this photo's own remembered rotation in the controls/preview.
        self._rotation_degrees = self._rotation_by_path.get(self._preview_path, 0)
        self._refresh_preview()
        self._update_preview_counter()
        self._update_metadata()

    # --- Drag and drop ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if not self._processing and any(
            url.isLocalFile() and url.toLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
            self.container.setProperty("dropActive", True)
            self.container.style().unpolish(self.container)
            self.container.style().polish(self.container)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.container.setProperty("dropActive", False)
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.container.setProperty("dropActive", False)
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)
        if self._processing:
            event.ignore()
            return
        paths = []
        for url in event.mimeData().urls():
            if not url.isLocalFile() or not url.toLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.exists():
                paths.append(path)
        if paths:
            self._open_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # --- Settings persistence ---

    def _restore_processing_preference(self) -> None:
        pref = load_processing_preference()
        self._set_background_color(pref.background_color)
        self.watermark_input.setText(pref.watermark_text)
        size_btn = self._watermark_size_buttons.get(pref.watermark_size)
        if size_btn:
            size_btn.setChecked(True)
        else:
            self._watermark_size_buttons["medium"].setChecked(True)
        pos_btn = self._watermark_position_buttons.get(pref.watermark_position)
        if pos_btn:
            pos_btn.setChecked(True)
        else:
            self._watermark_position_buttons["bottom-right"].setChecked(True)
        # Rotation is not restored: it is remembered per photo within a
        # session, not carried across sessions (there are no photos loaded yet).
        # Overwrite deliberately always starts OFF (tester feedback): it is
        # destructive, so it must be opted into every session.

    def _save_processing_preference(self) -> None:
        pref = StoredProcessingPreference(
            background_color=self._background_color,
            watermark_text=self.watermark_input.text(),
            watermark_size=self._current_watermark_size(),
            watermark_position=self._current_watermark_position(),
            overwrite=self.overwrite_check.isChecked(),
        )
        save_processing_preference(pref)

    # --- Window geometry ---

    def _center_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _restore_geometry(self) -> None:
        settings = _settings()
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if settings.value("window/maximized", False, type=bool):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._processing:
            self._close_when_finished = True
            self._request_cancel()
            event.ignore()
            return
        settings = _settings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/maximized", self.isMaximized())
        super().closeEvent(event)
