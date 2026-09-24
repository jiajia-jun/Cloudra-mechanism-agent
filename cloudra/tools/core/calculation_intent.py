"""Shared calculation-intent model for QM input generation and inspection.

One semantic model is used by three parties so that "what was requested" and
"what the file actually asks the engine to do" can be compared instead of
trusted:

- ``intent_from_writer`` normalizes qm_input_writer arguments;
- ``validate_writer_request`` lists input conflicts the writer must refuse
  (empty list means *this layer* found no conflict — it is not a scientific
  validity verdict);
- ``inspect_input`` re-reads a generated/input file and reports the intent it
  actually encodes. Fields that cannot be determined stay ``None``/``unknown``;
  an incomplete parse is never guessed into a task type.

Native engine blocks (ORCA ``%`` blocks, Gaussian route syntax) stay native —
this module is not an alternative input DSL.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

TASK_VOCABULARY = frozenset(
    {"minimum_opt", "ts_opt", "frequency", "single_point", "irc", "relaxed_scan"}
)

# task_type keys the writer understands, mapped to intent tasks. ORCA-specific
# rejections (Gaussian-style sub-options etc.) are produced by
# validate_writer_request, not silently dropped. 'sp' is the historical short
# spelling of the canonical 'single_point' (TASK_VOCABULARY); both are accepted
# and normalized to 'single_point'.
_WRITER_TASK_KEYS = frozenset({"opt", "freq", "irc", "scan", "sp", "single_point"})

# writer 键 -> 规范化键（规范化入口：语义等价拼写在进入 seen/tasks 前统一）
_WRITER_KEY_CANONICAL = {"sp": "single_point"}

# Gaussian TS sub-options that have no ORCA simple-keyword translation; the
# ORCA native equivalent is %geom / Hessian source blocks via orca_blocks.
_GAUSSIAN_ONLY_OPT_SUBOPTIONS = {"calcfc", "noeigen", "calcall", "qst2", "qst3"}

_FREQ_NUMERIC_ALIASES = {"num", "numer", "numeric", "numfreq"}

_ORCA_CONSTRAINT_RE = re.compile(
    r"\{\s*([BADC])\s+([\d\s]+?)\s+([\d.+-]+)\s*C\s*\}", re.I
)
_ORCA_PAL_RE = re.compile(r"%pal\s+nprocs\s+(\d+)", re.I)
_ORCA_MAXCORE_RE = re.compile(r"%maxcore\s+(\d+)", re.I)
_ORCA_PROGEXT_RE = re.compile(r'^\s*ProgExt\s+"?([^"\s]+)"?', re.I | re.M)
_ORCA_XYZ_RE = re.compile(r"^\*\s*xyz\s+(-?\d+)\s+(\d+)", re.M)
_GAUSSIAN_CHARGE_RE = re.compile(r"^\s*(-?\d+)\s+(\d+)\s*$", re.M)
_EXTERNAL_ROUTE_RE = re.compile(r'external="?([^"\s]+)"?', re.I)


class CalculationIntent(BaseModel):
    """Normalized calculation intent; unknown fields stay None/unknown."""

    engine: str
    engine_version: str | None = None
    provider: str | None = None
    tasks: set[str] = Field(default_factory=set)
    frequency_mode: Literal["auto", "analytic", "numeric"] = "auto"
    constraints: list[dict] = Field(default_factory=list)
    charge: int | None = None
    multiplicity: int | None = None
    method_signature: str | None = None
    geometry_hash: str | None = None
    certainty: Literal["known", "partial", "unknown"] = "unknown"


def _entry(code: str, field: str, message: str) -> dict:
    return {"code": code, "field": field, "message": message}


# ----------------------------------------------------------------------
# writer arguments -> intent / validation
# ----------------------------------------------------------------------


def _writer_tasks(arguments: dict[str, Any]) -> tuple[set[str], list[str]]:
    """Map writer task_type onto intent tasks plus the raw unknown keys."""
    tasks: set[str] = set()
    unknown: list[str] = []
    for task in arguments.get("task_type") or []:
        if not isinstance(task, dict):
            unknown.append(repr(task))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            params = str(value).lower() if value is not None else ""
            if key_l not in _WRITER_TASK_KEYS:
                unknown.append(key_l)
                continue
            if key_l == "opt":
                if "ts" in {p.strip() for p in params.split(",") if p.strip()}:
                    tasks.add("ts_opt")
                else:
                    tasks.add("minimum_opt")
            elif key_l == "freq":
                tasks.add("frequency")
            elif key_l == "irc":
                tasks.add("irc")
            elif key_l == "scan":
                tasks.add("relaxed_scan")
            elif key_l in ("sp", "single_point"):
                tasks.add("single_point")
    return tasks, unknown


def _writer_frequency_mode(arguments: dict[str, Any], tasks: set[str]) -> str:
    mode = str(arguments.get("frequency_mode") or "auto").lower()
    if mode != "auto":
        return mode
    # Explicit numeric aliases on the freq task count as a numeric request.
    for task in arguments.get("task_type") or []:
        if isinstance(task, dict):
            for key, value in task.items():
                if str(key).lower() == "freq" and value is not None:
                    if str(value).lower().strip() in _FREQ_NUMERIC_ALIASES:
                        return "numeric"
    return "auto"


def intent_from_writer(arguments: dict[str, Any]) -> CalculationIntent:
    """Normalize qm_input_writer arguments into a CalculationIntent."""
    engine = str(arguments.get("engine") or "gaussian").lower()
    tasks, unknown = _writer_tasks(arguments)
    external = arguments.get("external_program")
    provider = Path(str(external)).name.lower() if external else None
    method = str(arguments.get("method") or "").strip()
    basis = str(arguments.get("basis_set") or "").strip()
    if external:
        method_signature = f"external:{provider}"
    elif method and basis:
        method_signature = f"{method}/{basis}"
    elif method:
        method_signature = method
    else:
        method_signature = None
    certainty = "known" if tasks and not unknown else ("partial" if tasks else "unknown")
    return CalculationIntent(
        engine=engine,
        provider=provider,
        tasks=tasks,
        frequency_mode=_writer_frequency_mode(arguments, tasks),  # type: ignore[arg-type]
        charge=arguments.get("charge"),
        multiplicity=arguments.get("multiplicity"),
        method_signature=method_signature,
        certainty=certainty,
    )


def validate_writer_request(arguments: dict[str, Any]) -> list[dict]:
    """Input-conflict entries ({code, field, message}); empty means no conflict
    found at this layer — NOT a scientific validity pass."""
    entries: list[dict] = []
    engine = str(arguments.get("engine") or "gaussian").lower()
    task_type = arguments.get("task_type") or []

    seen: dict[str, Any] = {}
    for task in task_type:
        if not isinstance(task, dict):
            entries.append(_entry(
                "malformed_task", "task_type",
                f"task_type entries must be dicts like {{'opt': None}}; got {task!r}.",
            ))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            if key_l not in _WRITER_TASK_KEYS:
                suggestion = ""
                if key_l == "numfreq":
                    suggestion = " Use {'freq': None} with frequency_mode='numeric' instead."
                entries.append(_entry(
                    "unknown_task_key", "task_type",
                    f"Unknown task key {key_l!r}; supported keys: "
                    f"{sorted(_WRITER_TASK_KEYS)}.{suggestion}",
                ))
                continue
            # 语义等价拼写（sp/single_point）归一后判重，不能借拼写绕过
            canonical = _WRITER_KEY_CANONICAL.get(key_l, key_l)
            if canonical in seen and seen[canonical] != value:
                entries.append(_entry(
                    "conflicting_task", "task_type",
                    f"Task {canonical!r} given twice with conflicting parameters "
                    f"({seen[canonical]!r} vs {value!r}); merge them into one entry.",
                ))
            elif canonical in seen:
                entries.append(_entry(
                    "duplicate_task", "task_type",
                    f"Task {canonical!r} appears more than once; keep a single entry.",
                ))
            seen[canonical] = value

    tasks, _ = _writer_tasks(arguments)
    mode = str(arguments.get("frequency_mode") or "auto").lower()
    if mode not in ("auto", "analytic", "numeric"):
        entries.append(_entry(
            "unknown_frequency_mode", "frequency_mode",
            f"frequency_mode must be one of auto/analytic/numeric; got {mode!r}.",
        ))
    elif mode != "auto" and "frequency" not in tasks:
        entries.append(_entry(
            "frequency_mode_without_frequency", "frequency_mode",
            "frequency_mode was set but no frequency task was requested; "
            "add {'freq': None} or drop frequency_mode.",
        ))

    if engine == "orca":
        for key, value in seen.items():
            params = {p.strip() for p in str(value).lower().split(",") if p.strip()} if value is not None else set()
            if key == "opt":
                bad = sorted(params & _GAUSSIAN_ONLY_OPT_SUBOPTIONS)
                if bad:
                    entries.append(_entry(
                        "gaussian_only_suboption", "task_type",
                        f"ORCA inputs do not accept Gaussian opt sub-options {bad}; "
                        "control the TS Hessian through native orca_blocks "
                        "(%geom Calc_Hess / Hess_Source) instead.",
                    ))
            if key == "freq" and value is not None:
                unknown_freq = sorted(params - _FREQ_NUMERIC_ALIASES)
                if unknown_freq:
                    entries.append(_entry(
                        "unknown_freq_suboption", "task_type",
                        f"Unknown ORCA freq sub-options {unknown_freq}; use "
                        "frequency_mode='numeric' for NumFreq or native orca_blocks.",
                    ))
            if key == "scan":
                blocks = str(arguments.get("orca_blocks") or "")
                if "scan" not in blocks.lower():
                    entries.append(_entry(
                        "scan_requires_orca_blocks", "task_type",
                        "An ORCA relaxed scan needs a native %geom Scan definition in "
                        "orca_blocks (e.g. '%geom Scan B 0 1 = 2.0, 3.0, 10 end end'); "
                        "a bare {'scan': ...} task cannot be translated.",
                    ))
        if str(arguments.get("end_setting") or "").strip():
            entries.append(_entry(
                "gaussian_only_field", "end_setting",
                "end_setting is a Gaussian end-of-file section; ORCA has no such "
                "card — express the setting in orca_blocks instead.",
            ))
    return entries


# ----------------------------------------------------------------------
# generated/input text -> intent
# ----------------------------------------------------------------------

_ORCA_SIMPLE_TASK_TOKENS = {
    "opt": "minimum_opt",
    "optts": "ts_opt",
    "freq": "frequency",
    "numfreq": "frequency",
    "irc": "irc",
}


def _orca_has_geom_scan(text: str) -> bool:
    """Find a native Scan directive inside an ORCA %geom block."""
    in_geom = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        geom_start = re.match(r"^%geom\b", line, re.I)
        if geom_start:
            in_geom = True
            line = line[geom_start.end():].strip()
        elif line.startswith(("%", "*")):
            in_geom = False
        if in_geom and re.match(r"^Scan\b", line, re.I):
            return True
    return False


def _inspect_orca(text: str) -> CalculationIntent:
    tasks: set[str] = set()
    frequency_mode: str = "auto"
    saw_simple_line = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("!/") or not s.startswith("!"):
            continue
        saw_simple_line = True
        for token in s[1:].split():
            mapped = _ORCA_SIMPLE_TASK_TOKENS.get(token.lower())
            if mapped:
                tasks.add(mapped)
                if token.lower() == "numfreq":
                    frequency_mode = "numeric"
                elif token.lower() == "freq" and frequency_mode == "auto":
                    frequency_mode = "analytic"
    if _orca_has_geom_scan(text):
        # Opt enables the constrained optimization at each scan point; it is
        # not a separate minimum optimization in this input.
        tasks.discard("minimum_opt")
        tasks.add("relaxed_scan")
    if not tasks and saw_simple_line:
        tasks.add("single_point")

    constraints = [
        {
            "type": {"B": "bond", "A": "angle", "D": "dihedral", "C": "cartesian"}[m.group(1).upper()],
            "atoms": [int(x) for x in m.group(2).split()],
            "value": float(m.group(3)),
        }
        for m in _ORCA_CONSTRAINT_RE.finditer(text)
    ]

    provider = None
    method_signature = None
    if re.search(r"^!", text, re.M) and "extopt" in text.lower():
        m = _ORCA_PROGEXT_RE.search(text)
        if m is not None:
            provider = Path(m.group(1)).name.lower()
            method_signature = f"external:{provider}"
    charge = multiplicity = None
    m = _ORCA_XYZ_RE.search(text)
    if m is not None:
        charge, multiplicity = int(m.group(1)), int(m.group(2))

    certainty = "known" if tasks else "unknown"
    return CalculationIntent(
        engine="orca",
        provider=provider,
        tasks=tasks,
        frequency_mode=frequency_mode,  # type: ignore[arg-type]
        constraints=constraints,
        charge=charge,
        multiplicity=multiplicity,
        method_signature=method_signature,
        certainty=certainty,
    )


def _inspect_gaussian(text: str) -> CalculationIntent:
    route = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            route = s.lower()
            break
    tasks: set[str] = set()
    frequency_mode = "auto"
    if route:
        if re.search(r"\bopt\b", route):
            if "ts" in route:
                tasks.add("ts_opt")
            else:
                tasks.add("minimum_opt")
        if re.search(r"\bfreq\b", route):
            tasks.add("frequency")
            if re.search(r"freq\s*=\s*\(?\s*(num|numer)", route):
                frequency_mode = "numeric"
        if re.search(r"\birc\b", route):
            tasks.add("irc")
        if re.search(r"\bscan\b", route):
            tasks.add("relaxed_scan")
        if not tasks:
            tasks.add("single_point")
    provider = None
    method_signature = None
    m = _EXTERNAL_ROUTE_RE.search(route)
    if m is not None:
        provider = Path(m.group(1)).name.lower()
        method_signature = f"external:{provider}"
    charge = multiplicity = None
    m = _GAUSSIAN_CHARGE_RE.search(text)
    if m is not None:
        charge, multiplicity = int(m.group(1)), int(m.group(2))
    certainty = "known" if route else "unknown"
    return CalculationIntent(
        engine="gaussian",
        provider=provider,
        tasks=tasks,
        frequency_mode=frequency_mode,  # type: ignore[arg-type]
        charge=charge,
        multiplicity=multiplicity,
        method_signature=method_signature,
        certainty=certainty,
    )


def inspect_input(text: str, *, engine: str) -> CalculationIntent:
    """Re-read an input file's text and report the intent it actually encodes."""
    engine_l = engine.lower()
    if engine_l == "orca":
        return _inspect_orca(text)
    if engine_l == "gaussian":
        return _inspect_gaussian(text)
    return CalculationIntent(engine=engine_l, certainty="unknown")


def geometry_hash_of(xyz_block: str) -> str:
    """Stable hash over coordinate lines (element + xyz), for intent linking."""
    lines = [ln.strip() for ln in xyz_block.splitlines() if ln.strip()]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
