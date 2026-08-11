from __future__ import annotations

import os
import shutil
import sys


def is_windows() -> bool:
    """Return True when running on native Windows."""
    return os.name == "nt"


def is_android() -> bool:
    """Return True when running on Android or inside Termux."""
    if hasattr(sys, "getandroidapilevel"):
        return True
    if os.environ.get("PREFIX", "").endswith("/com.termux"):
        return True
    return False


def is_posix() -> bool:
    """Return True when running on a POSIX OS (Linux, Android, Termux, macOS, ...)."""
    return os.name == "posix"


def get_bash_path() -> str | None:
    """Return the absolute path to a usable ``bash`` executable, or None."""
    return shutil.which("bash")
