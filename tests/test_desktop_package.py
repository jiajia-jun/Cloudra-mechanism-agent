"""Packaged launchers must run their bundled environment without source-build steps."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("arguments", [[], ["--version"]])
def test_macos_bundle_uses_embedded_runtime_and_prebuilt_ui(tmp_path, arguments):
    launcher_source = ROOT / "packaging/macos/Cloudra"
    assert launcher_source.is_file(), "native app launcher is missing"
    app = tmp_path / "Cloudra demo.app"
    resources = app / "Contents/Resources"
    (app / "Contents/MacOS").mkdir(parents=True)
    (resources / "python/bin").mkdir(parents=True)
    (resources / "node/bin").mkdir(parents=True)
    home_dir = tmp_path / "user"
    (home_dir / "Desktop").mkdir(parents=True)
    record = tmp_path / "launch.json"
    python = resources / "python/bin/python3"
    python.write_text(
        f"#!{sys.executable}\nimport os, sys, json, shutil\nfrom pathlib import Path\n"
        f"Path({str(record)!r}).write_text(json.dumps(dict("
        "args=sys.argv[1:], cwd=os.getcwd(), "
        "node=shutil.which('node'), python3=shutil.which('python3'), lsof=shutil.which('lsof'), "
        "frontend=os.environ.get('CLOUDRA_FRONTEND_DIR'))))\n"
    )
    python.chmod(0o755)
    node = resources / "node/bin/node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    launcher = app / "Contents/MacOS/Cloudra"
    shutil.copyfile(launcher_source, launcher)
    launcher.chmod(0o755)
    result = subprocess.run(
        [str(launcher), *arguments], env={**os.environ, "HOME": str(home_dir), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    captured = json.loads(record.read_text())
    lsof = captured.pop("lsof")
    if sys.platform == "darwin":
        assert lsof == "/usr/sbin/lsof"
    assert captured == {
        "args": ["-m", "cloudra", *(arguments or ["web", "--skip-build"])],
        "cwd": str(resources), "node": str(node), "python3": str(python),
        "frontend": str(resources / "frontend"),
    }
    if not arguments:
        assert (home_dir / "Desktop/Cloudra.app").resolve() == app
