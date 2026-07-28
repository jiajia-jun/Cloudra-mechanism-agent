"""Runtime capability profiles.

Desktop Cloudra can delegate work to subprocesses and expose tools backed by
local executables.  Embedded Python on Android cannot.  Keep that distinction
in one place so the LLM schema and the actual dispatcher enforce the same
capability boundary.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import TypeVar

from cloudra.platform_utils import is_android

_Entry = TypeVar("_Entry")

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Tools in this set are implemented entirely in the embedded Python process or
# through network APIs.  In particular, none of them launches a shell or an
# external executable.
ANDROID_TOOL_ALLOWLIST = frozenset(
    {
        "SubAgentLauncher",
        "chemrxiv_searcher",
        "edit_file",
        "get_subagent_report",
        "getskill",
        "image_reader",
        "paper_searcher",
        "schedule",
        "stop",
        "text_reader",
        "text_writer",
        "update_memory",
        "web_fetcher",
    }
)


def is_mobile_runtime() -> bool:
    """Return whether Cloudra must use its Android-safe runtime profile.

    ``CLOUDRA_MOBILE_MODE`` is deliberately supported on desktop so CI can
    exercise the Android path without an emulator.
    """

    override = os.environ.get("CLOUDRA_MOBILE_MODE", "")
    # Android can never be forced into the subprocess profile; the environment
    # override only enables mobile-mode testing on another platform.
    return is_android() or override.strip().lower() in _TRUTHY


def filter_tools_for_runtime(entries: Iterable[_Entry]) -> list[_Entry]:
    """Filter tool entries to those executable in the current runtime."""

    entries = list(entries)
    if not is_mobile_runtime():
        return entries
    return [
        entry
        for entry in entries
        if getattr(entry, "tool_name", "") in ANDROID_TOOL_ALLOWLIST
    ]
