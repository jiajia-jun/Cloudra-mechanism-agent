"""Tool regex is reserved for parsing raw quantum chemistry output logs."""

from __future__ import annotations

import ast
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parent.parent / "cloudra" / "tools"

# These modules parse native Gaussian/ORCA/xTB output, the sole AGENTS.md exception.
RAW_QM_LOG_PARSERS = frozenset({
    "Chemtool/log_parser.py",
    "Chemtool/ts_guess.py",
    "core/gaussian_frames.py",
    "core/orca_frames.py",
    "core/xtb_frames.py",
})


def test_tools_reserve_regex_for_raw_qm_logs():
    violations = []
    for path in sorted(TOOLS_ROOT.rglob("*.py")):
        relative = path.relative_to(TOOLS_ROOT).as_posix()
        if relative in RAW_QM_LOG_PARSERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(module.split(".")[0] in {"re", "regex"} for module in modules):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, (
        "Use explicit tokens, enums, JSON or Pydantic for tool validation; "
        "regex is allowed only for native QM logs:\n" + "\n".join(violations)
    )
