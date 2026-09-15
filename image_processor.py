"""Upload-time image optimisation using Qt (no extra dependency).

Resizes oversized images and re-encodes them to WebP when that reduces size,
returning a temporary file path. Falls back to the original path on any error,
so callers can always upload something.
"""

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

_enabled = True
_max_width = 1600
_quality = 85
_SKIP_SUFFIXES = {".gif", ".svg"}
_MIN_RECODE_BYTES = 300 * 1024


def configure(enabled: bool = True, max_width: int = 1600, quality: int = 85):
    global _enabled, _max_width, _quality
    _enabled = bool(enabled)
    _max_width = int(max_width) if max_width else 1600
    _quality = int(quality) if quality else 85


def is_enabled() -> bool:
    return _enabled


def optimize(local_path: str) -> str:
    """Return a path ready for upload (possibly a temp WebP), or the original."""
    if not _enabled:
        return local_path

    path = Path(local_path)
    if not path.exists() or path.suffix.lower() in _SKIP_SUFFIXES:
        return local_path

    img = QImage(str(path))
    if img.isNull():
        return local_path

    changed = False
    if img.width() > _max_width:
        img = img.scaledToWidth(_max_width, Qt.SmoothTransformation)
        changed = True

    original_size = path.stat().st_size
    if not changed and original_size < _MIN_RECODE_BYTES:
        return local_path

    out = Path(tempfile.gettempdir()) / f"blogc_{os.getpid()}_{path.stem}.webp"
    try:
        saved = img.save(str(out), "WEBP", _quality)
    except Exception:
        saved = False

    if saved and out.exists() and out.stat().st_size > 0:
        if changed or out.stat().st_size < original_size:
            return str(out)
        out.unlink(missing_ok=True)

    return local_path
