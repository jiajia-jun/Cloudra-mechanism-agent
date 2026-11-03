"""Exercise the packaged launcher without downloading runtimes or opening a browser."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LauncherTest(unittest.TestCase):
    def test_bundled_runtime_shortcuts_and_startup_failure(self):
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="Cloudra launch test ") as directory:
            root = Path(directory).resolve()
            app = root / "Cloudra app"
            app.mkdir()
            shutil.copyfile(source / "launch-cloudra.sh", app / "launch-cloudra.sh")
            shutil.copyfile(source / "cloudra.desktop.in", app / "cloudra.desktop.in")
            shutil.copyfile(source / "create_shortcuts.py", app / "create_shortcuts.py")
            (app / "Cloudra").touch()
            (app / "python/bin").mkdir(parents=True)
            (app / "node/bin").mkdir(parents=True)
            (app / "frontend").mkdir()
            (app / "node/bin/node").symlink_to(shutil.which("true"))
            fake_cloudra = app / "python/bin/cloudra.py"
            fake_cloudra.write_text(
                "import json, os, pathlib, shutil, sys\n"
                "pathlib.Path(os.environ['CAPTURE']).write_text(json.dumps({"
                "'argv': sys.argv[1:], 'node': shutil.which('node'), "
                "'python': shutil.which('python3'), 'frontend': os.environ['CLOUDRA_FRONTEND_DIR'], "
                "'pythonhome': os.environ.get('PYTHONHOME'), 'pythonpath': os.environ.get('PYTHONPATH'), "
                "'nousersite': os.environ.get('PYTHONNOUSERSITE')}))\n"
                "sys.exit(int(os.environ.get('FAIL_START', '0')))\n"
            )
            python = app / "python/bin/python3"
            python.write_text(
                f"#!{sys.executable}\nimport os, sys\n"
                "args = sys.argv[1:]\n"
                f"if args[:2] == ['-m', 'cloudra']: args = [{str(fake_cloudra)!r}, *args[2:]]\n"
                f"os.execv({sys.executable!r}, [{sys.executable!r}, *args])\n"
            )
            python.chmod(0o755)
            home = root / "user"
            desktop = home / "桌面"
            desktop.mkdir(parents=True)
            tools = root / "tools"
            tools.mkdir()
            xdg = tools / "xdg-user-dir"
            xdg.write_text(f"#!/bin/sh\nprintf '%s' '{desktop}'\n")
            xdg.chmod(0o755)
            zenity = tools / "zenity"
            zenity.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$DIALOG"\n')
            zenity.chmod(0o755)
            capture = root / "capture.json"
            dialog = root / "dialog.txt"
            env = {
                **os.environ, "HOME": str(home), "XDG_STATE_HOME": str(home / "state"),
                "XDG_DATA_HOME": str(home / "data"), "PATH": f"{tools}:/usr/bin:/bin",
                "CAPTURE": str(capture), "DIALOG": str(dialog),
                "PYTHONHOME": str(root / "unrelated Python"),
                "PYTHONPATH": str(root / "unrelated modules"), "PYTHONNOUSERSITE": "0",
            }
            first = subprocess.run(["/bin/bash", str(app / "launch-cloudra.sh")], cwd=root, env=env, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr.decode())
            self.assertEqual(json.loads(capture.read_text()), {
                "argv": ["web", "--skip-build"], "node": str(app / "node/bin/node"),
                "python": str(app / "python/bin/python3"), "frontend": str(app / "frontend"),
                "pythonhome": None, "pythonpath": None, "nousersite": "1",
            })
            menu = home / "data/applications/cloudra.desktop"
            shortcut = desktop / "Cloudra.desktop"
            self.assertEqual(shortcut.read_bytes(), menu.read_bytes())
            self.assertIn(f'Exec="{app}/Cloudra"', menu.read_text())
            shortcut.unlink()
            second = subprocess.run(
                ["/bin/bash", str(app / "launch-cloudra.sh")], env={**env, "FAIL_START": "9"},
                cwd=root, capture_output=True,
            )
            self.assertEqual(second.returncode, 9)
            self.assertIn("desktop.log", dialog.read_text())
            self.assertFalse(shortcut.exists(), "a deleted desktop shortcut must not be recreated on every launch")
            stop = subprocess.run(
                ["/bin/bash", str(app / "launch-cloudra.sh"), "--stop"], cwd=root, env=env, capture_output=True,
            )
            self.assertEqual(stop.returncode, 0)
            self.assertEqual(json.loads(capture.read_text())["argv"], ["stop"])
            version = subprocess.run(
                ["/bin/bash", str(app / "launch-cloudra.sh"), "--version"], cwd=root, env=env, capture_output=True,
            )
            self.assertEqual(version.returncode, 0)
            self.assertEqual(json.loads(capture.read_text())["argv"], ["--version"])
            dialog.unlink()
            for exit_code in (143, 241):
                stopped = subprocess.run(
                    ["/bin/bash", str(app / "launch-cloudra.sh")], cwd=root,
                    env={**env, "FAIL_START": str(exit_code)}, capture_output=True,
                )
                self.assertEqual(stopped.returncode, exit_code)
                self.assertFalse(dialog.exists(), "an intentional service stop must not show a startup error")


if __name__ == "__main__":
    unittest.main()
