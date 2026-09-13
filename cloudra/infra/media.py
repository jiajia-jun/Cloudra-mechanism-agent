"""Image encoding helpers shared by runtime_v2 and legacy LLM paths."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Optional

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def encode_image_base64(path: str) -> str:
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def encode_image_data_url(path: str) -> Optional[str]:
    """Return ``data:<mime>;base64,...`` or None when the file cannot be encoded."""
    if path.startswith("data:"):
        return path
    if not os.path.exists(path):
        return None
    mime = _IMAGE_MIME_TYPES.get(os.path.splitext(path)[1].lower())
    if mime is None:
        return None
    try:
        return f"data:{mime};base64,{encode_image_base64(path)}"
    except OSError:
        return None


def snapshot_image_reference(path: str, *, conv_id: str, fallback: str) -> dict:
    """Freeze image bytes before a message enters durable context."""
    from cloudra.persistence.fs_utils import atomic_write_bytes
    from cloudra.persistence.paths import context_media_dir

    suffix = Path(path).suffix.lower()
    if suffix not in _IMAGE_MIME_TYPES:
        return {"type": "text", "text": fallback}
    try:
        data = Path(path).read_bytes()
    except OSError:
        return {"type": "text", "text": fallback}
    digest = hashlib.sha256(data).hexdigest()
    destination = context_media_dir(conv_id) / f"{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        atomic_write_bytes(str(destination), data)
    return {"type": "image_ref", "path": str(destination), "sha256": digest,
            "fallback": fallback}


def encode_image_reference(part: dict) -> str:
    """Resolve immutable context bytes, refusing missing/corrupt snapshots."""
    path = str(part["path"])
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != part["sha256"]:
        raise ValueError(f"Context image snapshot checksum mismatch: {path}")
    mime = _IMAGE_MIME_TYPES[Path(path).suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"
