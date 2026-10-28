## 1.1.2

- Preserve transparency over the chosen background and normalize embedded color profiles.
- Bound large-image memory, contain per-file failures, and safely stop/close batches.
- Reject remote drops, keep repeat-overwrite rotations consistent, and fix zero-ink watermarks.
- Keep the familiar preview and controls; correct displayed version.
- Retain license/source/provenance evidence with unsigned Windows/Linux packages.

# Changelog

## 1.1.1

- Double-clicking a photo in Add Photos now loads it immediately
- Enter and Open use the same file and folder selection handler
- Folder double-click navigation and mixed selections remain supported

## 1.1.0

- Resizable and maximizable window with an expanding centered square preview
- Settings with System/Dark/Light appearance, tooltips, and Save/Cancel
- Left/Right rotate, Up/Down browse, and Enter saves the displayed photo
- Save Photo action alongside existing batch processing
- Minimal source metadata: filename, dimensions, format, and file size

## 1.0.0

Initial public release.

Square Photo Padder is a free, open-source desktop app that pads photos into
perfect squares — no cropping, no watermarks, no upload required.

### Features
- Batch processing: drag in files or whole folders and process them all at once
- Live square preview of exactly what you'll get, with per-photo 90° rotation
- Background color of your choice (black by default), picked from a compact
  built-in color picker that remembers your custom colors
- Optional blended text watermark in any corner, centered, or tiled
- Marketplace resize presets (1000, 1080, 1600, 2048) or a custom size —
  images are never upscaled
- Originals are never modified by default; outputs get collision-safe names,
  with an optional Overwrite mode
- Automatic dark/light theme matching your OS
- 100% offline — photos never leave your computer
- Windows (portable zip) and Linux (AppImage) builds
