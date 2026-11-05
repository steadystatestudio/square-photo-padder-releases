# Changelog

## 1.4.0 — 2026-11-04

- Follow Linux desktop font, size, light/dark and accent preferences with independent providers and readable fallbacks; appearance detection needs no system Python or PyGObject.
- Add saved app-wide appearance controls, Refresh and appearance-only Reset, with fitted settings dialogs.
- Measure compact window minimums from current controls instead of multiplying a fixed workspace by font size. Preserve useful previews and use scrolling only on constrained screens.
- Style checkbox choices as accent buttons while retaining checkbox state and keyboard behavior. Existing photo processing and output formats are unchanged.
- Use Qt 6.12's fix for stale layout-item pointers, with matching SDK/source notices. Source builds require Python 3.12+; downloaded packages include their own Python runtime.


## 1.3.1 — 2026-11-03

All interface text follows the configured desktop UI size, including headings, Help, tables and status. Document pages, exported captions and watermarks retain their own content typography.

Primary actions, enabled toggles, selections and progress use the system accent, with readable contrasting text. Secondary actions stay neutral. Desktop settings helpers use the host library environment, including in portable packages.

Compact controls preserve more vertical working space. File Renamer keeps its rule controls, Rename and Undo together: Rename shifts horizontally when needed, and resizing stops before the row collides. Layouts adapt to enlarged fonts and constrained monitor work areas.

## 1.2.5 — 2026-11-03

- Restore a useful minimum window size so the preview, everyday controls, task actions and status remain visible together.
- Measure the layout at the system font size; adapt the minimum to the current monitor and use scrolling when its work area is genuinely too small.
- Repair undersized restored windows while keeping the system-font improvements.

## 1.2.4

- Use the operating system UI font family and configured text size, including Linux Mint Cinnamon and Ubuntu GNOME desktop settings. Reopen the app after changing desktop font settings.
- Keep text at that size when the window is narrow. Toolbar controls wrap and configuration scrolls instead of shrinking the font.
- Preserve the chosen desktop font when switching Light, Dark or System appearance.

## 1.2.2

- Keep Save Photo, Process All, progress and the permanent status visible on short desktops. The photo preview and settings scroll when needed without shrinking text to fit the screen height.
- Fit initial and restored windows inside the current screen's available work area, including window decorations.
- Fit corner and centered watermark text plus its halo inside small photos. If the complete text cannot fit, report a per-photo error and preserve the original instead of saving clipped text.

## 1.2.1

- Account for font bearings when placing watermarks, keeping short bottom-corner text and its halo inside small outputs and centering the visible text accurately.
- Keep newly selected photos at zero completed outputs and show an explicit ready message. Remove the timed fill that could look like completed processing before a save.
- Reset stale completion or error messages when replacing the selected photos.
- Add isolated UI checks that require a new destination folder; normal startup is unchanged.
- Expand image fidelity, actual output, and packaged readiness checks.

## 1.2.0

- Align the Studio toolbar, labeled Settings action, spacing and light/dark colors with Studio conventions.
- Keep Process All centered, Save Photo separate, and progress visible in its own read-only bar.
- Add a dedicated Add Folder action and make long status details available on hover.
- Improve selected-control and primary-action contrast.
- Correct marketplace guidance: square padding is not a compliance preset for eBay or Poshmark.
- Require a new folder for synthetic package diagnostics.
- Isolate Windows package builds from unrelated tools on the host DLL search path.
- Stage releases only through an explicit reviewed-commit dispatch, with existing-tag and published-release checks.

## 1.1.2

- Preserve transparency over the chosen background and normalize embedded color profiles.
- Bound large-image memory, contain per-file failures, and safely stop/close batches.
- Reject remote drops, keep repeat-overwrite rotations consistent, and fix zero-ink watermarks.
- Keep the familiar preview and controls; correct displayed version.
- Retain license/source/provenance evidence with unsigned Windows/Linux packages.

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
perfect squares â€” no cropping, no watermarks, no upload required.

### Features
- Batch processing: drag in files or whole folders and process them all at once
- Live square preview of exactly what you'll get, with per-photo 90Â° rotation
- Background color of your choice (black by default), picked from a compact
  built-in color picker that remembers your custom colors
- Optional blended text watermark in any corner, centered, or tiled
- Marketplace resize presets (1000, 1080, 1600, 2048) or a custom size â€”
  images are never upscaled
- Originals are never modified by default; outputs get collision-safe names,
  with an optional Overwrite mode
- Automatic dark/light theme matching your OS
- 100% offline â€” photos never leave your computer
- Windows (portable zip) and Linux (AppImage) builds
