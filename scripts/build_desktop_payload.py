#!/usr/bin/env python3
"""Build a relocatable POSIX desktop runtime; no downloads or builds happen on users' machines."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_VERSION = "22.23.4"


def run(*args: str | Path, cwd: Path | None = None) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def download_node(cache: Path) -> Path:
    system = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}[platform.machine()]
    name = f"node-v{NODE_VERSION}-{system}-{arch}"
    filename = f"{name}.tar.gz"
    base = f"https://nodejs.org/dist/v{NODE_VERSION}/"
    checksum_file = cache / "SHASUMS256.txt"
    archive = cache / filename
    for url, destination in [(base + "SHASUMS256.txt", checksum_file), (base + filename, archive)]:
        run("curl", "--fail", "--location", "--retry", "2", "--connect-timeout", "15",
            "--max-time", "300", "--output", destination, url)
    checksums = dict(line.split()[::-1] for line in checksum_file.read_text().splitlines() if line.strip())
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != checksums[filename]:
        raise RuntimeError(f"Node.js download checksum mismatch: {filename}")
    with tarfile.open(archive) as bundle:
        bundle.extractall(cache, filter="data")
    return cache / name


def build_payload(output: Path, python_root: Path | None = None, node_root: Path | None = None) -> None:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"Build output already exists; choose a clean directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cloudra-build-", dir=output.parent) as temp:
        work = Path(temp)
        if python_root is None:
            run("uv", "python", "install", "3.13", "--install-dir", work / "python-download", "--no-bin")
            python_root = next(path for path in (work / "python-download").iterdir() if (path / "bin/python3").exists())
        if node_root is None:
            node_root = download_node(work)
        shutil.copytree(python_root, output / "python", symlinks=True)
        shutil.copytree(node_root, output / "node", symlinks=True)
        python = output / "python/bin/python3"
        site = Path(subprocess.check_output(
            [str(python), "-c", 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True,
        ).strip())
        run("uv", "pip", "install", "--python", python, "--target", site, ROOT, "pip")
        shutil.rmtree(site / "bin", ignore_errors=True)
        for command in ("cloudra", "pip"):
            wrapper = output / "python/bin" / command
            wrapper.write_text(f'#!/bin/sh\nexec "$(dirname "$0")/python3" -m {command} "$@"\n')
            wrapper.chmod(0o755)
        for metadata_dir in site.glob("cloudra-*.dist-info"):
            (metadata_dir / "direct_url.json").unlink(missing_ok=True)
        host = site / "cloudra/runtime_v2/js_host"
        run("npm", "ci", "--prefix", host, "--ignore-scripts", "--no-audit", "--no-fund")
        frontend = work / "frontend"
        shutil.copytree(ROOT / "frontend", frontend, ignore=shutil.ignore_patterns("node_modules", "dist", "*.tsbuildinfo"))
        run("npm", "ci", "--prefix", frontend, "--no-audit", "--no-fund")
        run("npm", "run", "build", "--prefix", frontend)
        shutil.copytree(frontend / "dist", output / "frontend/dist")
        shutil.copyfile(frontend / "package.json", output / "frontend/package.json")
        shutil.copyfile(ROOT / "LICENSE", output / "LICENSE")
        shutil.copytree(ROOT / "docs/licenses", output / "licenses")
        run(sys.executable, ROOT / "scripts/collect_frontend_licenses.py",
            "--frontend", frontend, "--output", output / "licenses/frontend")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        metadata = {
            "version": project["project"]["version"],
            "source": "https://github.com/yyywaa/Cloudra-mechanism-agent",
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": subprocess.check_output([str(python), "--version"], text=True).strip(),
            "node": subprocess.check_output([str(output / "node/bin/node"), "--version"], text=True).strip(),
        }
        (output / "VERSION.json").write_text(json.dumps(metadata, indent=2) + "\n")
        run(python, "-m", "cloudra", "--version")
        print(f"Desktop payload ready: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-root", type=Path)
    parser.add_argument("--node-root", type=Path)
    args = parser.parse_args()
    build_payload(args.output, args.python_root, args.node_root)
