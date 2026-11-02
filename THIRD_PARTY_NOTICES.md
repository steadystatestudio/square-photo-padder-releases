# Third-party notices

Square Photo Padder is copyright © 2026 Steady State Studio and MIT-licensed.
Release packaging/source-retention helpers are adapted from the Studio's
MIT-licensed Contact Sheet Maker. Application and third-party licenses are separate.

- Python: PSF license; complete license retained in `licenses/Python-LICENSE.txt`.
- Pillow: MIT-CMU and bundled component licenses, retained under `licenses/Pillow`.
- Qt / PySide6 / Shiboken 6.11.2: LGPLv3 alternative. QtCore, QtGui and QtWidgets
  remain dynamically linked and separately replaceable in the one-folder bundle.
  There is no restriction on reverse engineering to debug modifications to these
  libraries. See `LIBRARY-REPLACEMENT.txt`, included LGPL/GPL texts and retained
  `QT-THIRD-PARTY-NOTICES.txt`. Complete matching source archives, including build
  scripts and notices, must accompany public binary releases; exact pins are in
  `SOURCE-INDEX.json`. No Studio patches are applied to Qt/PySide/Shiboken.
  https://doc.qt.io/qtforpython-6/licenses.html
- PyInstaller: GPLv2-or-later with bootloader exception; notice retained.
- AppImage runtime 20251108 / commit dd6cebedcbddde9c82f89b011e8e1d40b6e43868:
  MIT, plus static-library notices for musl, libfuse, squashfuse, zstd, zlib,
  and mimalloc under `licenses/appimage`. Matching runtime, libfuse and
  squashfuse sources accompany public releases. The upstream recipe uses Alpine
  packages without exact package revisions; this is not a reproducible-build claim.
  https://github.com/AppImage/type2-runtime/tree/dd6cebedcbddde9c82f89b011e8e1d40b6e43868

`LICENSE-INDEX.json` hashes retained notices. `NATIVE-LIBRARIES.json` inventories
replaceable binaries. `BUILD-INFO.json` identifies exact source and dependencies.
The broader Qt notice set does not imply every optional Qt module is bundled.
Unused Qt PDF, Quick/QML, WebEngine, networking, VNC and software OpenGL fallback
components are excluded and rejected if they return. System-owned Linux libraries
remain on the host; `LINUX-SYSTEM-DEPENDENCIES.json` records package prerequisites.

Keep notices, source assets and replacement instructions available with every
redistribution. These records are engineering evidence, not a general legal opinion.
