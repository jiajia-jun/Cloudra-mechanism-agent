"""Quoting shared by Linux source and packaged desktop entries."""

from pathlib import Path


def quote_exec_argument(path: Path) -> str:
    value = str(path).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value.replace("\\", "\\\\") + '"'
