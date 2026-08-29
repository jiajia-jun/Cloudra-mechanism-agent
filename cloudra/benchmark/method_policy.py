"""Method-policy interception: whitelist checking for computational methods.

Only whitelisted methods may run — anything else is blocked. A blacklist can
always be bypassed, so every layer does positive (whitelist) matching:

- `qm_input_writer`: structured tool with an explicit method field — exact
  whitelist membership after normalization.
- `submit_compute_job`: submits a prepared `input_file`, so the verdict comes
  from that file's *content* (strict mode: an input that cannot be verified
  as requesting a whitelisted method is blocked).
- `bash`: the verdict comes from the *content of QM input files*, never from
  keyword-matching the command text. Heredoc/redirect payloads writing
  `.gjf`/`.com`/`.inp` files are extracted from the command and parsed
  (Gaussian route card / ORCA keyword lines); a QM program invoked on a
  pre-existing file (`g16 foo.gjf`) is covered by `check_input_files`, which
  the caller runs with sandbox access.

Parsing is done with small deterministic route-card/keyword-line readers. The
obvious library alternative (cclib) parses *output* logs, not input route
cards, so it does not apply here. A file that looks like a QM input but has no
parseable method directive is blocked (fail-closed): under a whitelist,
"cannot verify" means "cannot allow".

This module only computes verdicts; the caller performs the actual blocking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from cloudra.benchmark.schema import MethodPolicy

# suffixes we treat as QM input files
_QM_INPUT_SUFFIXES = {".gjf", ".com", ".inp"}

# job-type / control tokens that may appear on a Gaussian route card or an
# ORCA "!" keyword line and are NOT the method. This is a parsing ignore-list,
# not a security boundary: anything unrecognized is treated as a method
# candidate and must pass the whitelist, so gaps here fail closed.
_GAUSSIAN_JOB_TOKENS = {
    "opt", "freq", "irc", "scan", "sp", "stable", "pop", "force", "volume",
    "density", "symmetry", "symm", "temperature", "pressure",
}
_ORCA_JOB_TOKENS = {
    "opt", "freq", "irc", "scan", "sp", "ts", "optts", "numfreq", "tightscf",
    "verytightscf", "slowconv", "normalprint", "smallprint", "largeprint",
    "noproperty", "d3", "d4", "ri", "rijcosx", "noautostart", "enzym",
    # 波函数类型修饰符，不是方法本身
    "rks", "uks", "roks", "rhf", "uhf", "rohf", "hf",
}
# basis-set shaped tokens (def2-svp, 6-31g(d), cc-pvtz, sto-3g, ...) never
# carry method information; ignored while locating the method token.
_BASIS_RE = re.compile(
    r"^(?:def2|cc-pv|aug-cc-pv|sto|pcseg|pc|ano|minao|ma-def2)-|^\d+-\d+"
)
# heredoc opener: `<<EOF` / `<<-EOF` / `<<"EOF"` / `<<'EOF'`
_HEREDOC_OPEN_RE = re.compile(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?")
_REDIRECT_RE = re.compile(r">{1,2}\s*([^\s>;|&]+)")


@dataclass
class MethodVerdict:
    allowed: bool
    method: str = ""
    reason: str = ""
    matched_forbidden: list[str] = field(default_factory=list)  # 保留字段：拦截详情


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def check_method(method: str, policy: MethodPolicy) -> MethodVerdict:
    """Structured check for an explicit method string (submit_compute_job /
    qm_input_writer path): exact whitelist membership after normalization."""
    nm = _normalize(method)
    allowed = {_normalize(a) for a in policy.allowed_methods}
    if nm in allowed:
        return MethodVerdict(allowed=True, method=method)
    return MethodVerdict(
        allowed=False,
        method=method,
        reason=f"method '{method}' not in allowed_methods {policy.allowed_methods}; "
        f"fall back to an allowed method (e.g. {policy.allowed_methods[0]})",
        matched_forbidden=[method],
    )


# ---------------------------------------------------------------------------
# QM input content parsing
# ---------------------------------------------------------------------------


def _is_basis_token(tok: str) -> bool:
    return bool(_BASIS_RE.match(tok))


def _detect_input_engine(filename: str, content: str) -> Optional[str]:
    """Decide whether the payload is a Gaussian or ORCA input (or neither)."""
    suffix = Path(filename).suffix.lower() if filename else ""
    if suffix in (".gjf", ".com"):
        return "gaussian"
    if suffix == ".inp":
        return "orca"
    for line in content.splitlines():
        s = line.strip()
        # `%` 行有歧义（Gaussian Link0 的 %chk/%mem 与 ORCA 的 %maxcore/%pal
        # 都是 `%` 开头），不能作为引擎判据，跳过继续找决定性行。
        if not s or s.startswith("%"):
            continue
        if s.startswith("#"):
            return "gaussian"
        if s.startswith("!"):
            return "orca"
        # 第一有效行既不是路由卡也不是 ORCA 关键字：不像 QM 输入
        return None
    return None


def _extract_gaussian_methods(content: str) -> list[str]:
    """从 Gaussian 路由卡提取方法候选：`# opt b3lyp/6-31g(d) freq` → [b3lyp]。
    路由卡可跨行缠绕，到空行为止。方法通常是含 `/` 的 token 的左半；无 `/` 时
    （半经验如 `# am1 opt`）取非作业类型/非 key=value 的裸 token。跳过 Link0
    的 `%chk`/`%mem` 行。"""
    lines = content.splitlines()
    route_lines: list[str] = []
    in_route = False
    for line in lines:
        s = line.strip()
        if not in_route:
            if s.startswith("#"):
                in_route = True
                route_lines.append(s)
            continue
        if not s:
            break
        route_lines.append(s)
    if not route_lines:
        return []
    route = " ".join(route_lines)
    tokens = route.split()
    if tokens and tokens[0].startswith("#"):
        tokens = tokens[1:]  # 去掉 # / #p / #n
    slashed: list[str] = []
    bare: list[str] = []
    for tok in tokens:
        t = tok.lower()
        if "/" in t:
            head = t.split("/", 1)[0]
            if head:
                slashed.append(head)
            continue
        if "=" in t or "(" in t or _is_basis_token(t) or t in _GAUSSIAN_JOB_TOKENS:
            continue
        bare.append(t)
    # 路由卡里 method/basis 形式的 token 才是确定的方法声明；存在时只看它们，
    # 裸 token（无 `/` 的半经验写法如 am1）仅在没有 slash 形式时作准——防止在
    # 禁用方法旁填充白名单 token 蒙混过关。
    return slashed if slashed else bare


def _extract_orca_methods(content: str) -> list[str]:
    """从 ORCA 关键字行提取方法候选：`! rks b3lyp def2-svp opt` → [b3lyp]。
    跳过 `%` 块（maxcore/pal 等控制段）；候选 = `!` 行上既非作业类型
    也非基组形状的 token。"""
    candidates: list[str] = []
    for line in content.splitlines():
        s = line.strip()
        if not s.startswith("!"):
            continue
        for tok in s[1:].split():
            t = tok.lower()
            if t in _ORCA_JOB_TOKENS or _is_basis_token(t):
                continue
            candidates.append(t)
    return candidates


def check_input_content(
    content: str, policy: MethodPolicy, filename: str = "", strict: bool = False
) -> MethodVerdict:
    """Whitelist-check QM input *content* (Gaussian route card / ORCA keyword
    lines). Content that does not look like a QM input is out of scope
    (allowed) unless `strict` — e.g. `submit_compute_job` submissions, where an
    unverifiable input must be blocked. A QM input without a parseable method
    is always blocked fail-closed.
    方法候选中任一命中白名单即放行——白名单方法（如 xtb）不会合法出现在
    gaussian/orca 输入里，掺杂 token 绕过在实际场景不成立。"""
    engine = _detect_input_engine(filename, content)
    if engine is None:
        if strict:
            return MethodVerdict(
                allowed=False,
                reason="input file is not recognizable as a Gaussian/ORCA input; "
                "whitelist cannot be verified "
                f"(allowed: {policy.allowed_methods})",
            )
        return MethodVerdict(allowed=True)
    candidates = (
        _extract_gaussian_methods(content)
        if engine == "gaussian"
        else _extract_orca_methods(content)
    )
    if not candidates:
        return MethodVerdict(
            allowed=False,
            reason=f"{engine} input has no parseable method directive; "
            f"whitelist cannot be verified (allowed: {policy.allowed_methods})",
        )
    allowed = {_normalize(a) for a in policy.allowed_methods}
    hit = next((c for c in candidates if c in allowed), None)
    if hit is not None:
        return MethodVerdict(allowed=True, method=hit)
    return MethodVerdict(
        allowed=False,
        method=candidates[0],
        reason=f"{engine} input requests method(s) {candidates} not in "
        f"allowed_methods {policy.allowed_methods}; fall back to an allowed "
        f"method (e.g. {policy.allowed_methods[0]})",
        matched_forbidden=candidates,
    )


def check_input_files(
    paths: Iterable[Path], policy: MethodPolicy
) -> MethodVerdict:
    """Content check for QM inputs already on disk — covers a bash command
    invoking a QM program on a previously written file (`g16 foo.gjf`)."""
    for p in paths:
        p = Path(p)
        if p.suffix.lower() not in _QM_INPUT_SUFFIXES or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        verdict = check_input_content(content, policy, filename=p.name)
        if not verdict.allowed:
            return verdict
    return MethodVerdict(allowed=True)


# ---------------------------------------------------------------------------
# bash layer: embedded QM input payloads
# ---------------------------------------------------------------------------


def extract_embedded_inputs(command: str) -> list[tuple[str, str]]:
    """Extract (filename, content) pairs written by heredocs in a bash command.

    Handles `cat > file <<EOF` and `cat <<EOF > file`; unparseable targets
    keep an empty filename, in which case content sniffing still applies.
    """
    out: list[tuple[str, str]] = []
    lines = command.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEREDOC_OPEN_RE.search(line)
        if m is None:
            i += 1
            continue
        delim = m.group(1)
        target = _REDIRECT_RE.search(line[: m.start()]) or _REDIRECT_RE.search(
            line[m.end():]
        )
        fname = target.group(1).strip("'\"") if target else ""
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        out.append((fname, "\n".join(body)))
        i += 1
    return out


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def intercept(
    tool_name: str,
    arguments: dict,
    policy: MethodPolicy,
    base_dir: Path | str | None = None,
) -> MethodVerdict:
    """Dispatch entry: route a tool call to the right check based on the
    interception layer it belongs to. Returns allowed=True for tools/layers
    not covered by the policy.

    - `qm_input_writer` carries an explicit `method` field → structured
      whitelist check.
    - `submit_compute_job` carries no method field — it submits a prepared
      `input_file`, so the verdict comes from that file's *content*
      (strict: unverifiable input is blocked). Relative paths resolve
      against `base_dir` (the sandbox root the caller runs in).
    - bash calls are judged by the *content* of QM inputs they write; the raw
      command text is never keyword-scanned. Calls that merely reference an
      existing on-disk QM input (`g16 foo.gjf`) are the caller's responsibility
      via `check_input_files`."""
    layers = set(policy.intercept_layers)
    if tool_name == "qm_input_writer" and "qm_input_writer" in layers:
        method = str(arguments.get("method") or arguments.get("functional") or "")
        if not method:
            return MethodVerdict(
                allowed=False,
                reason="qm_input_writer call carries no method; whitelist requires an "
                f"explicit whitelisted method {policy.allowed_methods}",
            )
        return check_method(method, policy)
    if tool_name == "submit_compute_job" and "submit_compute_job" in layers:
        input_file = str(arguments.get("input_file") or "")
        if not input_file:
            return MethodVerdict(
                allowed=False,
                reason="submit_compute_job call carries no input_file; "
                "cannot verify the whitelist",
            )
        p = Path(input_file)
        if not p.is_absolute() and base_dir is not None:
            p = Path(base_dir) / p
        if not p.is_file():
            return MethodVerdict(
                allowed=False,
                reason=f"input file not found: {input_file}; cannot verify the whitelist",
            )
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return MethodVerdict(
                allowed=False,
                reason=f"cannot read input file {input_file}: {exc}",
            )
        return check_input_content(content, policy, filename=p.name, strict=True)
    if tool_name == "bash" and "bash" in layers:
        command = str(arguments.get("command") or arguments.get("script") or "")
        for fname, content in extract_embedded_inputs(command):
            verdict = check_input_content(content, policy, filename=fname)
            if not verdict.allowed:
                return verdict
        return MethodVerdict(allowed=True)
    return MethodVerdict(allowed=True)
