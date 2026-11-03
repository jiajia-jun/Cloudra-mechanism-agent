"""Installation entrypoints tested without downloads or changing the user's desktop."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "create_desktop_shortcut.py"


def _load_shortcuts():
    assert SCRIPT.is_file(), "desktop shortcut creator is missing"
    spec = importlib.util.spec_from_file_location("cloudra_shortcuts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_shortcut_launches_project_python_with_node_path(tmp_path, monkeypatch, system):
    """A desktop launch must not pick the desktop session's unrelated Python/Node."""
    shortcuts = _load_shortcuts()
    project = tmp_path / "Cloudra project"
    project.mkdir()
    shutil.copyfile(ROOT / "web.sh", project / "web.sh")
    home_dir = tmp_path / "user"
    desktop = home_dir / "Desktop"
    desktop.mkdir(parents=True)
    node_dir = tmp_path / "node bin"
    node_dir.mkdir()
    node = _executable(node_dir / "node", "#!/bin/sh\nprintf 'node-from-install'\n")
    capture = tmp_path / "launch.json"
    _executable(
        project / ".venv/bin/python",
        f"#!{sys.executable}\nimport json, os, shutil, subprocess, sys\n"
        "from pathlib import Path\n"
        f"Path({str(capture)!r}).write_text(json.dumps({{"
        "'args': sys.argv[1:], 'cwd': os.getcwd(), "
        "'node': subprocess.check_output(['node'], text=True), 'python3': shutil.which('python3')}))\n",
    )
    (project / ".venv/bin/python3").symlink_to("python")
    monkeypatch.setattr(shortcuts.platform, "system", lambda: system)
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: str(node) if name == "node" else None)
    monkeypatch.setenv("XDG_DATA_HOME", str(home_dir / ".local/share"))
    shortcuts.create_shortcut(project)

    if system == "Darwin":
        launcher = desktop / "Cloudra.command"
    else:
        entry = home_dir / ".local/share/applications/cloudra.desktop"
        assert entry.is_file()
        assert (desktop / "Cloudra.desktop").read_bytes() == entry.read_bytes()
        assert "Terminal=true" in entry.read_text()
        launcher = project / ".venv/bin/cloudra-ui"
    assert os.access(launcher, os.X_OK)
    result = subprocess.run(
        [str(launcher), "--skip-build"], cwd=tmp_path,
        env={**os.environ, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text()) == {
        "args": ["-m", "cloudra", "web", "--skip-build"],
        "cwd": str(project), "node": "node-from-install",
        "python3": str(project / ".venv/bin/python3"),
    }


def test_linux_uses_localized_desktop_and_has_no_fake_headless_desktop(tmp_path, monkeypatch):
    shortcuts = _load_shortcuts()
    project = tmp_path / "project"
    project.mkdir()
    home_dir = tmp_path / "user"
    home_dir.mkdir()
    desktop = home_dir / "桌面"
    desktop.mkdir()
    node = _executable(tmp_path / "bin/node", "#!/bin/sh\nexit 0\n")
    xdg = _executable(tmp_path / "bin/xdg-user-dir", f"#!/bin/sh\nprintf '%s' '{desktop}'\n")
    monkeypatch.setattr(shortcuts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setenv("XDG_DATA_HOME", str(home_dir / "apps"))
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: {"node": str(node), "xdg-user-dir": str(xdg)}.get(name))
    shortcuts.create_shortcut(project)
    assert (desktop / "Cloudra.desktop").is_file()
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: str(node) if name == "node" else None)
    shortcuts.create_shortcut(project)
    assert (home_dir / "apps/applications/cloudra.desktop").is_file()
    assert not (home_dir / "Desktop").exists()


@pytest.mark.parametrize("fail_install", [False, True])
def test_installer_builds_both_js_components_and_stops_on_failure(tmp_path, fail_install):
    """A Python-only success must not be reported as a complete UI installation."""
    project = tmp_path / "Cloudra project"
    project.mkdir()
    shutil.copyfile(ROOT / "install.sh", project / "install.sh")
    if SCRIPT.exists():
        (project / "scripts").mkdir()
        shutil.copyfile(SCRIPT, project / "scripts/create_desktop_shortcut.py")
    for component in ["frontend", "cloudra/runtime_v2/js_host"]:
        (project / component).mkdir(parents=True)
    home_dir = tmp_path / "user"
    home_dir.mkdir()
    log = tmp_path / "steps.jsonl"
    bin_dir = tmp_path / "bin"
    python = _executable(
        bin_dir / "python3",
        f"#!{sys.executable}\nimport json, os, pathlib, shutil, subprocess, sys\n"
        "args = sys.argv[1:]\n"
        f"with open({str(log)!r}, 'a') as f: f.write(json.dumps(['python', *args]) + '\\n')\n"
        "if args[0] == '-c': exec(args[1])\n"
        "elif args[:2] == ['-m', 'venv']:\n"
        "    dest = pathlib.Path(args[2]) / 'bin/python'\n"
        "    dest.parent.mkdir(parents=True)\n"
        "    shutil.copyfile(sys.argv[0], dest); dest.chmod(0o755)\n"
        "    (dest.parent / 'activate').write_text('')\n"
        "elif args[:2] == ['-m', 'pip']:\n"
        "    sys.exit(1 if os.environ.get('FAIL_INSTALL') and '-e' in args else 0)\n"
        "elif args[0].endswith('create_desktop_shortcut.py'):\n"
        f"    sys.exit(subprocess.call([{sys.executable!r}, *args]))\n",
    )
    _executable(bin_dir / "cloudra", "#!/bin/sh\nexit 0\n")
    _executable(bin_dir / "node", "#!/bin/sh\nexit 0\n")
    _executable(
        bin_dir / "npm",
        f"#!{sys.executable}\nimport json, pathlib, sys\n"
        f"with open({str(log)!r}, 'a') as f: f.write(json.dumps(['npm', *sys.argv[1:]]) + '\\n')\n",
    )
    result = subprocess.run(
        ["/bin/bash", str(project / "install.sh")], input="\n" * 5,
        env={**os.environ, "HOME": str(home_dir), "CLOUDRA_PYTHON": str(python),
             "PATH": f"{bin_dir}:/usr/bin:/bin", "FAIL_INSTALL": "1" if fail_install else ""},
        text=True, capture_output=True, timeout=20,
    )
    steps = [json.loads(line) for line in log.read_text().splitlines()]
    npm_steps = [step[1:] for step in steps if step[0] == "npm"]
    if fail_install:
        assert result.returncode != 0
        assert npm_steps == []
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert ["ci", "--prefix", str(project / "cloudra/runtime_v2/js_host"),
                "--ignore-scripts", "--no-audit", "--no-fund"] in npm_steps
        assert ["ci", "--prefix", str(project / "frontend"), "--no-audit", "--no-fund"] in npm_steps
        assert ["run", "build", "--prefix", str(project / "frontend")] in npm_steps
        assert (project / ".venv/bin/cloudra-ui").is_file()
