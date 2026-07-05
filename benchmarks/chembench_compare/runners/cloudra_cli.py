"""
Cloudra CLI runner for ChemBench comparison.

Calls the Cloudra CLI (`cloudra run --new --yolo`) for each question.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from typing import Optional

from cloudra.config import get_config

from benchmarks.chembench_compare.runners.base import BaseRunner, BaseRunnerConfig


class CloudraCliRunner(BaseRunner):
    """Runner that invokes the Cloudra CLI for each ChemBench question."""

    name = "Cloudra-CLI"

    def _invoke(self, prompt: str) -> str:
        if not shutil.which("cloudra"):
            raise RuntimeError("cloudra CLI not found in PATH")

        cmd = ["cloudra", "run", "--new", "--yolo", prompt]

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
        cfg = get_config()
        snapshot = super()._config_snapshot()
        snapshot.update(
            {
                "coordinator_model": cfg.coordinator.model,
                "follower_model": cfg.follower.model,
            }
        )
        return snapshot


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_BANNER_RE = re.compile(r"^\s*Cloudra -.*$", re.MULTILINE)
_VERSION_RE = re.compile(r"^\s*版本:.*$", re.MULTILINE)
_DIVIDER_RE = re.compile(r"^[-=]{10,}.*$", re.MULTILINE)


def _clean_output(text: str) -> str:
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _BANNER_RE.sub("", text)
    text = _VERSION_RE.sub("", text)
    text = _DIVIDER_RE.sub("", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    # Cloudra sometimes places the final answer only in the stop-tool reason
    # (encoded as JSON on the last line). Try to recover an explicit answer
    # from that JSON so downstream extract_answer() can find it.
    if lines:
        last_line = lines[-1]
        recovered = _recover_answer_from_json(last_line)
        if recovered:
            lines.append(f"[ANSWER]{recovered}[/ANSWER]")

    return "\n".join(lines)


_ANSWER_IN_REASON_RE = re.compile(
    r'[\u4e00-\u9fff\s]*正确答案[是为]?\s*([A-Ea-e])[\u4e00-\u9fff\s，,。.!?]*'
)


def _recover_answer_from_json(last_line: str) -> Optional[str]:
    """
    Parse Cloudra's final JSON line and extract an answer letter if present.

    Looks for patterns like:
      - "正确答案为 D"
      - "正确答案是 C"
      - "正确答案 D"
    Returns None if no clear answer is found.
    """
    import json

    try:
        data = json.loads(last_line)
    except Exception:
        return None

    message = data.get("message") or data.get("reason") or ""
    if not isinstance(message, str):
        return None

    # First try to find an explicit answer letter in the message text.
    match = _ANSWER_IN_REASON_RE.search(message)
    if match:
        return match.group(1).upper()

    # Fallback: look for a standalone option letter near the end.
    # Be conservative: only accept a single capital A-E preceded by Chinese
    # phrases like "选项" or "答案" or "为/是".
    tail = message[-80:]
    fallback = re.search(r'(?:答案|选项|为|是)[\s:：()（）]*([A-Ea-e])(?:\s*[\u4e00-\u9fff，,。.!！?？）)]|\s*$)', tail)
    if fallback:
        return fallback.group(1).upper()

    return None
