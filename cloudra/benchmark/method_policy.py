"""Method-policy interception: whitelist checking for computational methods.

A pure validator that decides whether a requested computational method is
allowed under a task's `MethodPolicy`. The harness wires this in at two
layers (declared in `MethodPolicy.intercept_layers`):
- `submit_compute_job` / `qm_input_writer`: the structured computation entry
  tools, where the method/basis are explicit fields.
- `bash`: free-form shell commands, where a heuristic scan looks for
  high-level method keywords in QM input text being written.

An intercepted (forbidden) method is *blocked*, never penalized: the agent is
told to fall back to an allowed method. This module only computes the verdict;
the actual blocking is done by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from cloudra.benchmark.schema import MethodPolicy

# canonical method keywords that signal a forbidden high level of theory when
# they appear in free-form text (QM input files, bash heredocs).
_FORBIDDEN_KEYWORDS = [
    "ccsd(t)", "ccsd", "dlpno", "wb97m-v", "w1", "cbs-qb3", "g4", "g3",
    "def2-tzvpd", "def2-qzvpp", "cc-pvtz", "cc-pvqz", "casscf", "mrci",
]
# basis-set tokens above the allowed ceiling get flagged too
_HIGH_BASIS = ["def2-tzvp", "def2-qzvp", "tzvpd", "qzvpp", "cc-pvtz", "cc-pvqz", "aug-cc"]

# 构成“词内”的字符类；关键词两侧若紧邻这类字符则不视为独立 token。
# 否则 "w1"/"g3"/"g4" 这类短词会误伤 "new1.xyz"/"log4.out"/"scan_g4.log"。
_WORD_CHAR = r"[a-z0-9_]"


@dataclass
class MethodVerdict:
    allowed: bool
    method: str = ""
    reason: str = ""
    matched_forbidden: list[str] = field(default_factory=list)


def _normalize(s: str) -> str:
    # 折叠（而非删除）空白，避免相邻词粘连后边界失效（"def2-tzvpd opt" 若删空白
    # 会变成 "def2-tzvpdopt"，连 def2-tzvpd 本身都匹配不上）。
    return re.sub(r"\s+", " ", s.lower())


def _contains_token(text: str, token: str) -> bool:
    """True if `token` appears in normalized `text` as a delimited token."""
    tok = _normalize(token)
    pattern = rf"(?<!{_WORD_CHAR}){re.escape(tok)}(?!{_WORD_CHAR})"
    return re.search(pattern, text) is not None


def check_method(method: str, policy: MethodPolicy) -> MethodVerdict:
    """Structured check for an explicit method string (submit_compute_job /
    qm_input_writer path)."""
    nm = _normalize(method)
    allowed = {_normalize(a) for a in policy.allowed_methods}
    if nm in allowed:
        return MethodVerdict(allowed=True, method=method)
    return MethodVerdict(
        allowed=False,
        method=method,
        reason=f"method '{method}' not in allowed_methods {policy.allowed_methods}; "
        f"fall back to an allowed method (e.g. {policy.allowed_methods[0]})",
    )


def scan_text_for_forbidden(text: str, policy: MethodPolicy) -> MethodVerdict:
    """Heuristic free-text scan (bash path): flag forbidden method/basis
    keywords appearing in QM input being written. 匹配按词边界进行，避免
    "w1"/"g4" 这类短词命中普通文件名。"""
    nt = _normalize(text)
    matched = [k for k in _FORBIDDEN_KEYWORDS if _contains_token(nt, k)]
    matched += [b for b in _HIGH_BASIS if _contains_token(nt, b)]
    # explicitly declared forbid list from the task
    matched += [f for f in policy.forbid if _contains_token(nt, f)]
    matched = sorted(set(matched))
    if matched:
        return MethodVerdict(
            allowed=False,
            reason=f"forbidden computational method/basis detected: {matched}; "
            f"allowed methods are {policy.allowed_methods}",
            matched_forbidden=matched,
        )
    return MethodVerdict(allowed=True)


def intercept(tool_name: str, arguments: dict, policy: MethodPolicy) -> MethodVerdict:
    """Dispatch entry: route a tool call to the right check based on the
    interception layer it belongs to. Returns allowed=True for tools/layers
    not covered by the policy."""
    layers = set(policy.intercept_layers)
    if tool_name in ("submit_compute_job", "qm_input_writer") and (
        "submit_compute_job" in layers or "qm_input_writer" in layers
    ):
        method = str(arguments.get("method") or arguments.get("functional") or "")
        basis = str(arguments.get("basis") or "")
        if method:
            v = check_method(method, policy)
            if not v.allowed:
                return v
        if basis:
            nb = _normalize(basis)
            if any(_normalize(h) in nb for h in _HIGH_BASIS):
                return MethodVerdict(
                    allowed=False,
                    reason=f"basis '{basis}' exceeds allowed ceiling '{policy.allowed_basis_max}'",
                    matched_forbidden=[basis],
                )
        return MethodVerdict(allowed=True, method=method)
    if tool_name == "bash" and "bash" in layers:
        text = str(arguments.get("command") or arguments.get("script") or "")
        return scan_text_for_forbidden(text, policy)
    return MethodVerdict(allowed=True)
