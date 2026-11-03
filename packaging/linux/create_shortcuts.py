"""Create the Linux menu and desktop entries once, including for a portable copy."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from cloudra.infra.desktop_entries import quote_exec_argument


def desktop_entry(app: Path) -> str:
    icon = str(app / "cloudra.svg").replace("\\", "\\\\")
    return (app / "cloudra.desktop.in").read_text().replace("@EXEC@", quote_exec_argument(app / "Cloudra")).replace("@ICON@", icon)


def create_shortcuts(app: Path) -> None:
    home = Path.home()
    # The .deb already installs a system entry. Portable installs need a user entry.
    if app != Path("/opt/cloudra"):
        menu = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "applications/cloudra.desktop"
        menu.parent.mkdir(parents=True, exist_ok=True)
        menu.write_text(desktop_entry(app))
    desktop = home / "Desktop"
    xdg = shutil.which("xdg-user-dir")
    if xdg:
        result = subprocess.run([xdg, "DESKTOP"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            desktop = Path(result.stdout.strip())
    if desktop.is_dir() and desktop != home:
        shortcut = desktop / "Cloudra.desktop"
        shortcut.write_text(desktop_entry(app))
        shortcut.chmod(0o755)


if __name__ == "__main__":
    create_shortcuts(Path(sys.argv[1]).resolve())
