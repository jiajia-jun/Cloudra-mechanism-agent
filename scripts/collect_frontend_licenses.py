#!/usr/bin/env python3
"""Carry production frontend packages' actual license notices into desktop distributions."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def collect(frontend: Path, output: Path) -> None:
    lock = json.loads((frontend / "package-lock.json").read_text())
    manifest = []
    for location, metadata in lock["packages"].items():
        if not location.startswith("node_modules/") or metadata.get("dev", False):
            continue
        package = frontend / location
        info = json.loads((package / "package.json").read_text())
        destination = output / location.removeprefix("node_modules/")
        destination.mkdir(parents=True, exist_ok=True)
        for source in package.iterdir():
            name = source.name.lower()
            if name.startswith(("license", "licence", "notice", "copying")) or name.startswith("readme"):
                if source.is_dir():
                    shutil.copytree(source, destination / source.name, dirs_exist_ok=True)
                else:
                    shutil.copyfile(source, destination / source.name)
        manifest.append({"name": info["name"], "version": info["version"], "license": info.get("license")})
    output.mkdir(parents=True, exist_ok=True)
    (output / "packages.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.frontend, args.output)
