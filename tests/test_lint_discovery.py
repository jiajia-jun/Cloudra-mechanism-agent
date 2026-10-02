"""Keep frozen evidence out of lint discovery without hiding maintained code."""

import json
import subprocess
import sys
from pathlib import Path


def test_ruff_skips_only_the_frozen_hard_archive(tmp_path):
    config = Path(__file__).resolve().parents[1] / "pyproject.toml"
    (tmp_path / "pyproject.toml").write_bytes(config.read_bytes())
    active_paths = {
        "cloudra/probe.py",
        "tests/test_probe.py",
        "scripts/probe.py",
        ".deck-work/probe.py",
        "gold_compute/library_audit_20261002/probe.py",
        "gold_compute/organized_data/future_archive/probe.py",
    }
    frozen_path = "gold_compute/organized_data/hard_20261001/probe.py"
    for relative in active_paths | {frozen_path}:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print(undefined_lint_probe)\n", encoding="utf-8")

    notebook_path = "gold_compute/library_audit_20261002/probe.ipynb"
    (tmp_path / notebook_path).write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": ["print(undefined_lint_probe)\n"],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    active_paths.add(notebook_path)

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format=json", "--no-cache"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    diagnostics = json.loads(result.stdout)
    assert {item["code"] for item in diagnostics} == {"F821"}
    assert {str(Path(item["filename"]).relative_to(tmp_path)) for item in diagnostics} == active_paths
