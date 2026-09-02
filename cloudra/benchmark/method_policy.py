"""Method-policy interception: whitelist checking for computational methods.

Only whitelisted methods may run — anything else is blocked. A blacklist can
always be bypassed, so every layer does positive (whitelist) matching:

- `qm_input_writer`: structured tool with an explicit method field — whitelist
  membership at method-family granularity after normalization.
- `submit_compute_job`: submits a prepared `input_file`, so the verdict comes
  from that file's *content* (strict mode: an input that cannot be verified
  as requesting a whitelisted method is blocked).
- `bash`: the verdict comes from the
  *content of QM input files*, never from keyword-matching the command text.
  Heredoc and echo/printf-redirect payloads writing `.gjf`/`.com`/`.inp` files
  are extracted from the command (nested one level when a payload is itself a
  script) and parsed — Gaussian route cards (all of them, across `--Link1--`
  steps) / ORCA keyword lines. A QM program invoked on a pre-existing file
  (`g16 foo.gjf`) is covered by `check_input_files`, which the caller runs with
  sandbox access.

Whitelist matching is at method-*family* granularity: any token containing
`xtb` (`xtb2`, `gfn2-xtb`, `xtbff`) matches an `xtb` entry, and any `mace-*`
token matches a `mace` entry. Route text cannot distinguish MLIP model
variants (mace-omol25 vs mace-off), so variant-level enforcement is out of
band, at the method-provisioning side. Gaussian MLIP runs go through the
`external="engine"` route keyword; the engine value is the method candidate,
and a bare `external` with no value stays fail-closed.

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
# basis-set tokens never carry method information; ignored while locating the
# method token. Regex covers prefixed families; the alias set covers ORCA's
# bare aliases (svp/tzvp/qzvpp/lanl2dz/...) that have no prefix.
_BASIS_RE = re.compile(
    r"^(?:def2-|cc-pv|aug-|sto-|pcseg|pc-\d|ano|minao|ma-|jun-|jul-|\d+-\d+)"
)
_BASIS_ALIAS = {
    "sv", "svp", "sv(p)", "dz", "dzp", "tz", "tzp", "tzvp", "tzvpp",
    "qz", "qzvp", "qzvpp", "lanl2dz", "lanl2mb", "minis", "midi",
}
# heredoc opener: `<<EOF` / `<<-EOF` / `<<"EOF"` / `<<'EOF'`
_HEREDOC_OPEN_RE = re.compile(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?")
_REDIRECT_RE = re.compile(r">{1,2}\s*([^\s>;|&]+)")
# 单行 echo/printf 直写重定向：echo 'payload' > file / printf "...\n" > file
_REDIRECT_WRITE_RE = re.compile(
    r"^(?:echo|printf)\s+(?:-[a-zA-Z]+\s+)*(['\"])(.*?)\1\s*>>?\s*([^\s>;|&]+)\s*$"
)
# 算术展开 $((a << b)) 里的位移不是 heredoc
_ARITH_RE = re.compile(r"\$\(\(.*?\)\)")
# 嵌套脚本载荷的递归解析深度上限
_MAX_EMBED_DEPTH = 2
# Gaussian `external="mace"` / `external='mace'` / `external=mace`：外部引擎值
# 才是方法候选；裸 `external`（无值）保持 fail-closed
_EXTERNAL_VALUE_RE = re.compile(r"^external=[\"']?([a-z0-9_.-]+)[\"']?$")


@dataclass
class MethodVerdict:
    allowed: bool
    method: str = ""
    reason: str = ""
    matched_forbidden: list[str] = field(default_factory=list)  # 拦截详情


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _family(token: str) -> str:
    """方法族归一：白名单按方法族粒度匹配（`xtb2`/`gfn2-xtb`/`xtbff` → `xtb`，
    `mace-*` → `mace`）。路线卡文本无法区分 MLIP 模型变体（mace-omol25 vs
    mace-off），变体级管控在带外（方法供给端），不在本层。"""
    t = token.lower()
    if "xtb" in t:
        return "xtb"
    if t.startswith("mace"):
        return "mace"
    return t


def check_method(method: str, policy: MethodPolicy) -> MethodVerdict:
    """Structured check for an explicit method string (qm_input_writer path):
    whitelist membership at method-family granularity after normalization."""
    nm = _family(_normalize(method))
    allowed = {_family(_normalize(a)) for a in policy.allowed_methods}
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
    return tok in _BASIS_ALIAS or bool(_BASIS_RE.match(tok))


def _gaussian_route_cards(content: str) -> list[list[str]]:
    """全部路由卡的 token 序列（拼接跨行缠绕；覆盖 --Link1-- 多步输入的
    每一张卡）。每张卡 = 从 `#` 行到空行。"""
    cards: list[list[str]] = []
    current: list[str] = []
    in_route = False
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("#!"):  # shebang 不是路由卡
            continue
        if s.startswith("#"):
            if current:
                cards.append(current)
            current = []
            in_route = True
            s = s[1:]
            head, _, rest = s.partition(" ")
            if head.lower() in ("p", "n", "t"):
                s = rest  # `#p`/`#n`/`#t` 前缀
            elif not head:
                s = rest
            else:
                s = s  # `#opt ...`：head 即首个有效 token
                current.extend(head.split())
                s = rest
        elif in_route and not s:
            in_route = False
            if current:
                cards.append(current)
                current = []
            continue
        elif not in_route:
            continue
        current.extend(s.split())
    if current:
        cards.append(current)
    return cards


def _extract_gaussian_methods(content: str) -> list[list[str]]:
    """每张路由卡的方法候选列表。`method/basis` slash 形式是权威声明；无
    slash 时（半经验如 `# am1 opt`）取非作业类型/非 key=value/非基组的裸
    token。`external="engine"` 是 MLIP 外部路由：引擎值（小写）作为方法候选
    计入权威声明位；裸 `external` 无引擎值时保留为候选（白名单外必拦）。"""
    per_card: list[list[str]] = []
    for tokens in _gaussian_route_cards(content):
        slashed: list[str] = []
        bare: list[str] = []
        for tok in tokens:
            t = tok.lower()
            if t == "external" or t.startswith("external="):
                m = _EXTERNAL_VALUE_RE.match(t)
                if m is not None:
                    slashed.append(m.group(1))
                elif t == "external":
                    bare.append(t)  # 裸 external：留候选，白名单外 fail-closed
                continue
            if "/" in t:
                head = t.split("/", 1)[0]
                if head:
                    slashed.append(head)
                continue
            if "=" in t or "(" in t or _is_basis_token(t) or t in _GAUSSIAN_JOB_TOKENS:
                continue
            bare.append(t)
        # slash 方法存在时只看 slash：防止在禁用方法旁填充白名单裸 token
        per_card.append(slashed if slashed else bare)
    return per_card


def _extract_orca_methods(content: str) -> list[str]:
    """ORCA 关键字行的方法候选：跳过 `%` 块（maxcore/pal 等控制段），候选 =
    `!` 行上既非作业类型/波函数修饰也非基组形状的 token。ORCA 每个输入只有
    一个电子结构方法，多个候选即异常。"""
    candidates: list[str] = []
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("!/"):  # shebang
            continue
        if not s.startswith("!"):
            continue
        for tok in s[1:].split():
            t = tok.lower()
            if t in _ORCA_JOB_TOKENS or _is_basis_token(t):
                continue
            candidates.append(t)
    return candidates


def _looks_gaussian_route(content: str) -> bool:
    """无后缀内容嗅探：`#` 段需含 method/basis 形 token 或作业关键字才算
    路由卡——脚本里的普通注释行（`# compute barrier with mace`）不算。"""
    for tokens in _gaussian_route_cards(content):
        for tok in tokens:
            t = tok.lower()
            if "/" in t:
                return True
            if t.split("(", 1)[0].split("=", 1)[0] in _GAUSSIAN_JOB_TOKENS:
                return True
    return False


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
            return "gaussian" if _looks_gaussian_route(content) else None
        if s.startswith("!"):
            return None if s.startswith("!/") else "orca"  # shebang 除外
        # 第一有效行既不是路由卡也不是 ORCA 关键字：不像 QM 输入
        return None
    return None


def check_input_content(
    content: str, policy: MethodPolicy, filename: str = "", strict: bool = False
) -> MethodVerdict:
    """Whitelist-check QM input *content* (Gaussian route cards / ORCA keyword
    lines). Content that does not look like a QM input is out of scope
    (allowed) unless `strict` — e.g. `submit_compute_job` submissions, where an
    unverifiable input must be blocked. A QM input without a parseable method
    is always blocked fail-closed. 所有方法候选都必须命中白名单（任一候选
    未命中即拦截），防掺杂绕过。"""
    engine = _detect_input_engine(filename, content)
    if engine is None:
        if strict:
            return MethodVerdict(
                allowed=False,
                reason="input file is not recognizable as a Gaussian/ORCA input; "
                f"whitelist cannot be verified (allowed: {policy.allowed_methods})",
            )
        return MethodVerdict(allowed=True)
    allowed = {_family(_normalize(a)) for a in policy.allowed_methods}
    if engine == "gaussian":
        cards = _extract_gaussian_methods(content)
        if not cards or any(not c for c in cards):
            return MethodVerdict(
                allowed=False,
                reason="gaussian input has route card(s) with no parseable method "
                f"directive; whitelist cannot be verified (allowed: {policy.allowed_methods})",
            )
        candidates = [c for card in cards for c in card]
    else:
        candidates = _extract_orca_methods(content)
        if not candidates:
            return MethodVerdict(
                allowed=False,
                reason="orca input has no parseable method directive; "
                f"whitelist cannot be verified (allowed: {policy.allowed_methods})",
            )
    bad = [c for c in candidates if _family(c) not in allowed]
    if bad:
        return MethodVerdict(
            allowed=False,
            method=bad[0],
            reason=f"{engine} input requests method(s) {bad} not in "
            f"allowed_methods {policy.allowed_methods}; fall back to an allowed "
            f"method (e.g. {policy.allowed_methods[0]})",
            matched_forbidden=bad,
        )
    return MethodVerdict(allowed=True, method=candidates[0])


# bash 命令里对磁盘已有 QM 输入文件的引用（`g16 foo.gjf` / `orca run.inp`）。
# 只按后缀抓路径 token，不判断语义；不存在的路径由 check_input_files 跳过。
_QM_INPUT_REF_RE = re.compile(r"[^\s\"'>;|&()]+\.(?:gjf|com|inp)\b", re.IGNORECASE)


def referenced_input_paths(command: str) -> list[str]:
    """Extract paths of QM input files a bash command *references* (as opposed
    to writes). Callers resolve them against the sandbox and pass the existing
    ones to `check_input_files`. Redirect targets written by this same command
    (`cat > ts.gjf <<EOF`) show up here too, but they do not exist on disk at
    interception time and their content was already checked via
    `extract_embedded_inputs`, so they are harmless duplicates."""
    return _QM_INPUT_REF_RE.findall(command)


def check_input_files(
    paths: Iterable[Path], policy: MethodPolicy
) -> MethodVerdict:
    """Content check for QM inputs already on disk — covers a bash command
    invoking a QM program on a previously written file (`g16 foo.gjf`).
    文件不可读时 fail-closed（白名单语义下"读不了"等于"验不了"）。"""
    for p in paths:
        p = Path(p)
        if p.suffix.lower() not in _QM_INPUT_SUFFIXES or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return MethodVerdict(
                allowed=False,
                reason=f"cannot read QM input {p}: {exc}; whitelist cannot be verified",
            )
        verdict = check_input_content(content, policy, filename=p.name)
        if not verdict.allowed:
            return verdict
    return MethodVerdict(allowed=True)


# ---------------------------------------------------------------------------
# bash layer: embedded QM input payloads
# ---------------------------------------------------------------------------


def extract_embedded_inputs(command: str, _depth: int = 0) -> list[tuple[str, str]]:
    """Extract (filename, content) pairs written by a bash command — heredocs
    (`cat > file <<EOF` / `cat <<EOF > file`) and one-line echo/printf
    redirects. Payloads that are themselves scripts（如 `cat > run.sh <<EOF`
    里再写 QM 输入）递归提取一层。无目标文件名的载荷保留空文件名，由内容
    嗅探兜底。"""
    out: list[tuple[str, str]] = []
    lines = command.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        rw = _REDIRECT_WRITE_RE.match(line.strip())
        if rw is not None:
            payload = rw.group(2).replace("\\n", "\n")  # printf 转义
            out.append((rw.group(3), payload))
            i += 1
            continue
        line_nc = _ARITH_RE.sub("", line)  # 位移运算 $((a << b)) 不是 heredoc
        m = _HEREDOC_OPEN_RE.search(line_nc)
        if m is None:
            i += 1
            continue
        delim = m.group(1)
        target = _REDIRECT_RE.search(line_nc[: m.start()]) or _REDIRECT_RE.search(
            line_nc[m.end():]
        )
        fname = target.group(1).strip("'\"") if target else ""
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        out.append((fname, "\n".join(body)))
        i += 1
    if _depth < _MAX_EMBED_DEPTH:
        for _fname, body in list(out):
            out.extend(extract_embedded_inputs(body, _depth + 1))
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
    - bash calls (tool name `bash`) are judged by the
      *content* of QM inputs they write; the raw command text is never
      keyword-scanned. Calls that merely reference an existing on-disk QM
      input (`g16 foo.gjf`) are the caller's responsibility
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
