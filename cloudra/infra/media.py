"""Image encoding helpers shared by runtime_v2 and legacy LLM paths."""

from __future__ import annotations

import base64
import os
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
