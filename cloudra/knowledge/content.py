"""Complete source knowledge text, grouped by the graph's existing source ids."""

from __future__ import annotations

import json
import threading
from typing import Any

from cloudra.persistence import paths

_CACHE: dict[str, list[dict[str, Any]]] | None = None
_LOCK = threading.Lock()


def _reset_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def load_sources() -> dict[str, list[dict[str, Any]]]:
    """Load the static corpus once; graph sources are card ids without the section suffix."""
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        path = paths.knowledge_cards_path()
        if not path.is_file():
            raise FileNotFoundError(f'Knowledge source content is missing: {path}')
        sources: dict[str, list[dict[str, Any]]] = {}
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                source, separator, section = row["card_id"].rpartition(":")
                if not source or not separator or not section.isdecimal():
                    raise ValueError(f"Invalid knowledge card id: {row['card_id']!r}")
                sources.setdefault(source, []).append(row)
        _CACHE = sources
        return sources
