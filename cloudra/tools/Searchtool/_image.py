"""png/jpg/jpeg/webp workspace images for `read`."""

from __future__ import annotations

from cloudra.persistence.workspace import WorkspaceError, WorkspaceService
from cloudra.tools.Searchtool._text import IMAGE_EXTS


def read_image(root: str, path: str) -> str:
    """Resolve a workspace-relative image to an absolute filesystem path."""
    service = WorkspaceService(root)
    absolute = service.resolve_path(path)
    if not absolute.is_file():
        raise WorkspaceError(f"File does not exist: {path}")
    ext = absolute.suffix.lower()
    if ext not in IMAGE_EXTS:
        raise WorkspaceError(
            f"Unsupported image format {ext}. Only PNG, JPG, JPEG, WEBP are supported."
        )
    return str(absolute)
