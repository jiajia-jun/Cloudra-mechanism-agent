"""Packaged launchers must run their bundled environment without source-build steps."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
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


def test_macos_package_keeps_its_applications_install_location(tmp_path, monkeypatch):
    tools = ("osacompile", "sips", "iconutil", "codesign", "pkgbuild", "productbuild", "pkgutil")
    if sys.platform != "darwin" or any(shutil.which(tool) is None for tool in tools):
        pytest.skip("requires native macOS packaging tools")
    # A tiny payload exercises the real package builder without downloading runtimes.
    payload = tmp_path / "runtime"
    payload.mkdir()
    (payload / "runtime.txt").write_text("test runtime")
    build = tmp_path / "build with spaces"
    output = tmp_path / "packages"
    monkeypatch.setenv("CLOUDRA_DESKTOP_PAYLOAD", str(payload))
    monkeypatch.setenv("CLOUDRA_PACKAGE_BUILD", str(build))
    monkeypatch.setenv("CLOUDRA_PACKAGE_OUTPUT", str(output))
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/build-macos-package.sh")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    expanded = tmp_path / "expanded"
    subprocess.run(
        ["pkgutil", "--expand", str(build / "Cloudra-component.pkg"), str(expanded)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    info = ET.parse(expanded / "PackageInfo").getroot()
    assert info.attrib["install-location"] == "/Applications"
    assert not info.findall("relocate/bundle"), "Installer can relocate Cloudra.app into the build directory"
    assert Path(info.find("bundle").attrib["path"]) == Path("Cloudra.app")
