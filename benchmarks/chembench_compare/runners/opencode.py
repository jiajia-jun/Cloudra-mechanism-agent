"""
OpenCode runner for ChemBench comparison.

Calls the OpenCode CLI (`opencode run`) for each question.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Optional

from cloudra.config import get_config

from benchmarks.chembench_compare.runners.base import BaseRunner, BaseRunnerConfig


class OpenCodeRunner(BaseRunner):
    """Runner that invokes the OpenCode CLI for each ChemBench question."""

    name = "OpenCode"

    def __init__(self, config: BaseRunnerConfig, namespace: str, opencode_model: Optional[str] = None):
        super().__init__(config, namespace)
        self.opencode_model = opencode_model

    def _invoke(self, prompt: str) -> str:
        if not shutil.which("opencode"):
            raise RuntimeError("opencode CLI not found in PATH")

        cmd = ["opencode"]
        model = self.opencode_model or _default_opencode_model()
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["run", prompt])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_per_question,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout or ""
        if result.returncode != 0 and not output:
            output = result.stderr or ""
        return _clean_output(output)

    def _config_snapshot(self) -> dict:
        snapshot = super()._config_snapshot()
        snapshot.update(
            {
                "opencode_model": self.opencode_model or _default_opencode_model(),
                "opencode_version": _opencode_version(),
                "cloudra_coordinator_model": get_config().coordinator.model,
            }
        )
        return snapshot


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_HEADER_RE = re.compile(r"^\s*>\s*build.*$", re.MULTILINE)


def _clean_output(text: str) -> str:
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _HEADER_RE.sub("", text)
    return text.strip()


def _default_opencode_model() -> Optional[str]:
    try:
        cfg = get_config()
        model = cfg.coordinator.model
        url = cfg.coordinator.url
    except Exception:
        model = ""
        url = ""

    # Prefer the Xiaomi Token Plan provider when the Cloudra config points to
    # the token-plan endpoint; otherwise fall back to the standard xiaomi
    # provider.
    if model.startswith(("mimo-", "MiMo-")):
        if "token-plan" in url:
            return f"xiaomi-token-plan-cn/{model}"
        return f"xiaomi/{model}"
    if model:
        return model
    return None


def _opencode_version() -> str:
    try:
        result = subprocess.run(
            ["opencode", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return (result.stdout or result.stderr or "").strip()
    except Exception:
        return "unknown"
