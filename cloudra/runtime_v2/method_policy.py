"""Method-policy interception: whitelist checking for computational methods.

Only whitelisted methods may run — anything else is blocked. A blacklist can
always be bypassed, so every layer does positive (whitelist) matching:

- `qm_input_writer`: structured tool with an explicit method field — whitelist
  membership at method-family granularity after normalization.
- `submit_compute_job`: submits a prepared `input_file`, so the verdict comes
  from that file's *content* (strict mode: an input that cannot be verified
  as requesting a whitelisted method is blocked). `job_type="xtb"` submissions
  are the exception: a plain .xyz coordinate file carries no method
  information, so the declared job_type's method family is checked instead
  (still fail-closed when `xtb` is not whitelisted).
- `bash`: the verdict comes from the
  *content of QM input files*, never from keyword-matching the command text.
  Heredoc and echo/printf-redirect payloads writing `.gjf`/`.com`/`.inp` files
  are extracted from the command (nested one level when a payload is itself a
  script) and parsed — Gaussian route cards (all of them, across `--Link1--`
  steps) / ORCA keyword lines. A QM program invoked on a pre-existing file
  (`g16 foo.gjf`) is covered by `check_input_files`, which the caller runs with
  sandbox access.

Whitelist matching has two entry shapes: a bare family entry (`xtb`, `mace` —
families with no basis-set concept) matches at family granularity, i.e. any
token containing `xtb` (`xtb2`, `gfn2-xtb`, `xtbff`) matches an `xtb` entry and
any `mace-*` token matches a `mace` entry; a combo entry (`b3lyp/def2svp`)
additionally pins the basis — the request must declare the same basis
(spellings normalized: ORCA `def2-SVP` ≡ Gaussian `def2svp`), and a request
without a basis fails closed against combo entries. Route text cannot
distinguish MLIP model variants (mace-omol25 vs mace-off), so variant-level
enforcement is out of band, at the method-provisioning side. Gaussian MLIP runs go through the
`external="engine"` route keyword; the engine value is the method candidate,
and a bare `external` with no value stays fail-closed. The ORCA equivalent is
`! ExtOpt` + `%method ProgExt "<exe>"`: the executable basename is the method
candidate, and a bare `ExtOpt` with no ProgExt stays fail-closed.

Parsing is done with small deterministic route-card/keyword-line readers. The
obvious library alternative (cclib) parses *output* logs, not input route
cards, so it does not apply here. A file that looks like a QM input but has no
parseable method directive is blocked (fail-closed): under a whitelist,
"cannot verify" means "cannot allow".

This module only computes verdicts; the caller performs the actual blocking.
（GH #25：本模块由 benchmark 上移到 runtime_v2——live pipeline 的
MethodPolicyStage 也要用这套判定，而 runtime_v2 不能反向依赖 benchmark；
`cloudra.benchmark.method_policy` 保留为转引。）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from cloudra.runtime_v2.schemas import MethodPolicy

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
    "noproperty", "d3", "d3bj", "d3zero", "d4", "ri", "rijcosx", "noautostart", "enzym",
    # 波函数类型修饰符，不是方法本身
    "rks", "uks", "roks", "rhf", "uhf", "rohf",
    # 以下为计算控制修饰词，不是方法（本行注释即语义依据）：
    # 优化收敛等级
    "looseopt", "normalopt", "tightopt", "verytightopt",
    # 积分网格
    "grid", "grid0", "grid1", "grid2", "grid3", "grid4", "grid5", "grid6", "grid7",
    "finalgrid", "finalgrid1", "finalgrid2", "finalgrid3", "finalgrid4", "finalgrid5",
    "finalgrid6", "finalgrid7", "nofinalgrid", "gridx", "nogridx",
    # 轨道读取与输出级别
    "moread", "printgap", "noinpop",
}
# basis-set tokens never carry method information; ignored while locating the
# method token. Regex covers prefixed families; the alias set covers ORCA's
# bare aliases (svp/tzvp/qzvpp/lanl2dz/...) that have no prefix. def2 的连字符
# 可选：归一化组合拼写 `def2svp`（Gaussian 风格）与 ORCA 原生 `def2-SVP` 是
# 同一基组，漏识别会把基组当独立方法候选误杀。
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
# 才是方法候选；裸 `external`（无值）保持 fail-closed。引号必须成对——
# `external="mace`（未闭合）不匹配，否则 `external="mace --inject x"` 这类
# 注入会被截断成合法引擎值而 fail-open。


@dataclass
class MethodVerdict:
    allowed: bool
    method: str = ""
    reason: str = ""
    matched_forbidden: list[str] = field(default_factory=list)  # 拦截详情


def _normalize(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _norm_basis(b: str) -> str:
    """基组拼写归一：ORCA `def2-SVP` 与 Gaussian `def2svp` 是同一基组。"""
    return b.strip().lower().replace("-", "")


def _split_method_basis(token: str) -> tuple[str, str]:
    """`functional/basis` 组合拆成 (functional, 归一化基组)；无 slash 时基组为空。"""
    t = token.strip().lower()
    fam, sep, basis = t.partition("/")
    return fam.strip(), _norm_basis(basis) if sep else ""


def _entry_matches(family: str, req_basis: str, entries: Iterable[str]) -> bool:
    """白名单条目两种形态：裸族条目（`xtb`/`mace`，无基组概念，不约束基组）与
    组合条目（`b3lyp/def2svp`，请求必须带同一基组——缺基组即不命中，
    fail-closed）。"""
    for entry in entries:
        efam, ebasis = _split_method_basis(entry)
        if _family(efam) != family:
            continue
        if ebasis and req_basis != ebasis:
            continue
        return True
    return False


def _family(token: str) -> str:
    """方法族归一：白名单按方法族粒度匹配（`xtb2`/`gfn2-xtb`/`xtbff` → `xtb`，
    `mace`/`mace-*` → `mace`）。路线卡文本无法区分 MLIP 模型变体（mace-omol25 vs
    mace-off），变体级管控在带外（方法供给端），不在本层。
    mace 只认确切名字与连字符变体：`macefoo` 之类的前缀撞名不命中（候选是
    外部程序 basename，前缀匹配会让同名恶意二进制过审）。"""
    t = token.lower()
    if "xtb" in t:
        return "xtb"
    if t == "mace" or t.startswith("mace-"):
        return "mace"
    return t


def check_method(method: str, policy: MethodPolicy, basis: str = "") -> MethodVerdict:
    """Structured check for an explicit method string (qm_input_writer path):
    whitelist membership at method-family granularity after normalization.
    `method` 可自带 slash 基组（`b3lyp/def2svp`），或由 `basis` 参数（工具的
    `basis_set` 字段）补上；组合条目要求基组精确一致（拼写归一后），请求缺
    基组时 fail-closed。"""
    fam_raw, inline_basis = _split_method_basis(_normalize(method))
    fam = _family(fam_raw)
    req_basis = _norm_basis(basis) or inline_basis
    if _entry_matches(fam, req_basis, policy.allowed_methods):
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
    head, sep, tail = tok.partition("-")
    numeric_basis = bool(sep and head.isdigit() and tail and tail[0].isdigit())
    return tok in _BASIS_ALIAS or numeric_basis or tok.startswith(("def2", "cc-pv", "aug-", "sto-", "pcseg", "ano", "minao", "ma-", "jun-", "jul-")) or (tok.startswith("pc-") and tok[3:4].isdigit())


def _is_orca_aux_basis_token(tok: str) -> bool:
    """ORCA's /J, /JK, and /C fitting sets are not the orbital basis.

    Keep requiring a recognized basis-family prefix: an arbitrary method-like
    token with a slash must remain a candidate and fail closed.
    """
    head, sep, suffix = tok.rpartition("/")
    return bool(sep and _is_basis_token(head) and suffix in {"j", "jk", "jksmall", "c"})


def valid_external_engine_value(value: str) -> bool:
    return bool(value) and all(c.isascii() and (c.isalnum() or c in '_.-') for c in value)


def _gaussian_route_cards(content: str) -> list[list[str]]:
    """全部路由卡的 token 序列（拼接跨行缠绕；覆盖 --Link1-- 多步输入的
    每一张卡）。每张卡 = 从 `#` 行到空行。"""
    from cloudra.tools.core.calculation_intent import gaussian_routes
    try:
        return gaussian_routes(content)
    except ValueError:
        return [["unparseable_native_route"]]


def _extract_gaussian_methods(content: str) -> list[list[str]]:
    """每张路由卡的方法候选列表。`method/basis` slash 形式是权威声明；无
    slash 时（半经验如 `# am1 opt`）取非作业类型/非 key=value/非基组的裸
    token。`external="engine"` 是 MLIP 外部路由：引擎值（小写）作为方法候选
    计入权威声明位；裸 `external` 与畸形 `external=` 值（不匹配引擎值词法）
    都保留占位候选，白名单外必拦（fail-closed）。"""
    per_card: list[list[str]] = []
    for tokens in _gaussian_route_cards(content):
        slashed: list[str] = []
        bare: list[str] = []
        for tok in tokens:
            t = tok.lower()
            if t == "external" or t.startswith("external="):
                value = t.partition("=")[2]
                if value[:1] in {"'", '"'} and value[-1:] == value[:1] and len(value) >= 2:
                    value = value[1:-1]
                if valid_external_engine_value(value):
                    slashed.append(value)  # group(1) 是引号，group(2) 是引擎值
                elif t == "external":
                    bare.append(t)  # 裸 external：留候选，白名单外 fail-closed
                else:
                    # 畸形 external= 值（空格/引号注入等）：计入占位候选，
                    # 白名单外必拦——静默丢弃会让它在其他合法候选旁 fail-open。
                    slashed.append("external")
                continue
            if "/" in t:
                head, _, bset = t.partition("/")
                if head:
                    # 权威 slash 声明：方法+基组组合候选（`b3lyp/def2svp`）
                    slashed.append(f"{head}/{_norm_basis(bset)}" if bset else head)
                continue
            if "=" in t or "(" in t or _is_basis_token(t) or t in _GAUSSIAN_JOB_TOKENS:
                continue
            bare.append(t)
        # slash 方法存在时只看 slash：防止在禁用方法旁填充白名单裸 token
        per_card.append(slashed if slashed else bare)
    return per_card


def _extract_orca_methods(content: str) -> list[str]:
    """ORCA 关键字行的方法候选：跳过 `%` 块（maxcore/pal 等控制段）。每行
    `!` 上既非作业类型/波函数修饰也非基组形状的 token 是泛函候选；同行的
    基组 token 与泛函配对成组合候选（`b3lyp/def2svp`）——ORCA 每个输入只有
    一个电子结构方法，同行恰好一个基组时配对，零个或多个则泛函保持无基组
    （组合条目下 fail-closed）。

    `! ExtOpt` 是外部 MLIP 路由：能量/梯度由 `%method` 块里 ProgExt 指定的
    外部程序给出，方法候选取该程序的 basename（如 mace）——与 Gaussian
    `external="engine"` 的"引擎值即方法候选"对齐。裸 ExtOpt（无 ProgExt）
    保留 extopt 候选，白名单外必拦（fail-closed）。"""
    from cloudra.tools.core.calculation_intent import orca_directives
    try:
        tokens, blocks = orca_directives(content)
    except ValueError:
        return ["unparseable_native_route"]
    bases = [_norm_basis(t) for t in tokens if _is_basis_token(t) and not _is_orca_aux_basis_token(t)]
    basis = bases[0] if len(bases) == 1 else ""
    candidates = [f"{t}/{basis}" if basis else t for t in tokens if t not in _ORCA_JOB_TOKENS and t != "extopt" and not _is_basis_token(t) and not _is_orca_aux_basis_token(t)]
    if "extopt" in tokens:
        method = blocks.get("method", [])
        if "progext" in method and method.index("progext") + 1 < len(method):
            value = method[method.index("progext") + 1].strip("\"'")
            candidates.append(Path(value).name.lower())
        else:
            candidates.append("extopt")
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
    bad = []
    for c in candidates:
        cfam, cbasis = _split_method_basis(c)
        if not _entry_matches(_family(cfam), cbasis, policy.allowed_methods):
            bad.append(c)
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
      Exception: `job_type="xtb"` submissions take a plain .xyz coordinate
      file that carries no method information — the verdict comes from the
      declared job_type's method family (still fail-closed when `xtb` is
      not whitelisted).
    - bash calls (tool name `bash`) are judged by the
      *content* of QM inputs they write; the raw command text is never
      keyword-scanned. Calls that merely reference an existing on-disk QM
      input (`g16 foo.gjf`) are the caller's responsibility
      via `check_input_files`."""
    layers = set(policy.intercept_layers)
    if tool_name == "qm_input_writer" and "qm_input_writer" in layers:
        # 外部 MLIP 路由：方法候选是外部程序名（ORCA ProgExt 可执行的 basename /
        # Gaussian external="..." 引擎值）；此时 method 字段是工具默认值残留，
        # 不参与判定。
        ext = str(arguments.get("external_program") or "").strip()
        if ext:
            return check_method(Path(ext).name, policy)
        method = str(arguments.get("method") or arguments.get("functional") or "")
        if not method:
            return MethodVerdict(
                allowed=False,
                reason="qm_input_writer call carries no method; whitelist requires an "
                f"explicit whitelisted method {policy.allowed_methods}",
            )
        basis = str(arguments.get("basis_set") or arguments.get("basis") or "")
        return check_method(method, policy, basis=basis)
    if tool_name == "submit_compute_job" and "submit_compute_job" in layers:
        # xtb 作业（GH #26）：输入是纯坐标 .xyz，不携带方法信息——按提交声明的
        # job_type 方法族判定；白名单无 xtb 时依旧 fail-closed，语义不弱化。
        if str(arguments.get("job_type") or "").lower() == "xtb":
            return check_method("xtb", policy)
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
