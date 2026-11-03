"""Exercise download-quarantine removal only on temporary Cloudra fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "packaging/macos/Unblock-Cloudra.command"
ATTRIBUTE = "com.apple.quarantine"
pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS extended attributes")


def _quarantine(path: Path) -> None:
    subprocess.run(["/usr/bin/xattr", "-w", ATTRIBUTE, "0081;00000000;CloudraTest;", str(path)], check=True)


def _has_quarantine(path: Path) -> bool:
    return subprocess.run(["/usr/bin/xattr", "-p", ATTRIBUTE, str(path)], capture_output=True).returncode == 0


@pytest.mark.parametrize("name", ["Cloudra-0.1.0-macos-arm64.pkg", "Cloudra.app"])
def test_unblock_removes_quarantine_but_keeps_other_metadata(tmp_path, name):
    assert SCRIPT.is_file(), "Cloudra unblock script is missing"
    target = tmp_path / name
    if name.endswith(".app"):
        target.mkdir()
        child = target / "Contents"
        child.mkdir()
        _quarantine(child)
    else:
        target.touch()
        child = None
    _quarantine(target)
    subprocess.run(["/usr/bin/xattr", "-w", "cloudra.test.keep", "keep", str(target)], check=True)
    result = subprocess.run(["/bin/bash", str(SCRIPT), str(target)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not _has_quarantine(target)
    if child:
        assert not _has_quarantine(child)
    assert subprocess.check_output(["/usr/bin/xattr", "-p", "cloudra.test.keep", str(target)]).strip() == b"keep"
    # Running again is a no-op, without an unnecessary administrator prompt.
    assert subprocess.run(["/bin/bash", str(SCRIPT), str(target)], capture_output=True, timeout=10).returncode == 0


def test_unblock_rejects_other_apps_before_changing_any_target(tmp_path):
    assert SCRIPT.is_file(), "Cloudra unblock script is missing"
    cloudra = tmp_path / "Cloudra.app"
    other = tmp_path / "Other.app"
    for path in (cloudra, other):
        path.mkdir()
        _quarantine(path)
    result = subprocess.run(["/bin/bash", str(SCRIPT), str(cloudra), str(other)], capture_output=True, timeout=10)
    assert result.returncode != 0
    assert _has_quarantine(cloudra)
    assert _has_quarantine(other)
