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
from pathlib import Path
from typing import Any, Literal, Mapping

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
                else:
                    import difflib
                    matches = difflib.get_close_matches(key_l, sorted(_WRITER_TASK_KEYS), n=1, cutoff=0.35)
                    if matches:
                        suggestion = f" Did you mean {matches[0]!r}?"
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
        geom = orca_directives(str(arguments.get("orca_blocks") or ""))[1].get("geom", [])
        if "scan" in seen or "scan" in geom:
            entries.append(_entry(
                "scan_requires_ts_guess", "task_type" if "scan" in seen else "orca_blocks",
                "Prepare ORCA scans with ts_guess mode='scan_prepare', scans and scan_mode; "
                "qm_input_writer does not generate scans from task_type or raw %geom Scan.",
            ))
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
    "scants": "ts_opt",
    "neb-ts": "ts_opt",
    "loose-neb-ts": "ts_opt",
    "tight-neb-ts": "ts_opt",
    "fast-neb-ts": "ts_opt",
    "zoom-neb-ts": "ts_opt",
    "freq": "frequency",
    "numfreq": "frequency",
    "irc": "irc",
}


def native_tokens(text: str) -> list[str]:
    """Tokenize native directives, keeping parenthesized and quoted values intact."""
    tokens, current = [], []
    quote = ""
    depth = 0
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in ("\"", "'"):
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced native parentheses")
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current).lower())
                current = []
        else:
            current.append(char)
    if quote or depth:
        raise ValueError("unclosed native quote or parentheses")
    if current:
        tokens.append("".join(current).lower())
    joined = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if i + 2 < len(tokens) and tokens[i + 1] == '=':
            token += '=' + tokens[i + 2]
            i += 2
        elif i + 1 < len(tokens) and token.endswith('='):
            token += tokens[i + 1]
            i += 1
        elif i + 1 < len(tokens) and tokens[i + 1].startswith('='):
            token += tokens[i + 1]
            i += 1
        joined.append(token)
        i += 1
    return joined


def _orca_code(text: str) -> str:
    lines = []
    for line in text.splitlines():
        code, quote, comment = [], "", False
        for char in line:
            if quote:
                code.append(char)
                if char == quote:
                    quote = ""
            elif char in ("\"", "'") and not comment:
                quote = char
                code.append(char)
            elif char == "#":
                comment = not comment
                code.append(" ")
            elif not comment:
                code.append(char)
        lines.append("".join(code))
    return "\n".join(lines)


def gaussian_routes(text: str) -> list[list[str]]:
    routes, current = [], []
    awaiting_route = True
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower() == '--link1--':
            if current:
                routes.append(native_tokens(' '.join(current)))
                current = []
            awaiting_route = True
            continue
        if line.startswith("#!"):
            continue
        if awaiting_route and line.startswith("#"):
            awaiting_route = False
            if current:
                routes.append(native_tokens(" ".join(current)))
            line = line[1:]
            head, _, rest = line.partition(" ")
            if head.lower() in {"p", "n", "t"}:
                line = rest
            current = [line]
        elif current and line and line.lower() != "--link1--":
            current.append(line)
        elif current:
            routes.append(native_tokens(" ".join(current)))
            current = []
    if current:
        routes.append(native_tokens(" ".join(current)))
    return routes


def orca_directives(text: str) -> tuple[list[str], dict[str, list[str]]]:
    simple, blocks = [], {}
    active = None
    for line in _orca_code(text).splitlines():
        line = line.strip()
        if line.startswith("!/"):
            continue
        if line.startswith("!"):
            simple.extend(native_tokens(line[1:]))
            active = None
        elif line.startswith("%"):
            tokens = native_tokens(line)
            active = tokens[0][1:]
            blocks.setdefault(active, []).extend(tokens[1:])
        elif line.startswith("*"):
            active = None
        elif active:
            blocks[active].extend(native_tokens(line))
    return simple, blocks


def _native_charges(text: str, engine: str) -> list[tuple[int, int]]:
    values = []
    for raw in text.splitlines():
        tokens = raw.strip().split()
        if engine == "orca":
            if len(tokens) >= 4 and tokens[:2] == ["*", "xyz"]:
                tokens = tokens[2:4]
            else:
                continue
        if len(tokens) == 2:
            try:
                values.append((int(tokens[0]), int(tokens[1])))
            except ValueError:
                pass
    return values


def _inspect_orca(text: str) -> CalculationIntent:
    tokens, blocks = orca_directives(text)
    tasks = {_ORCA_SIMPLE_TASK_TOKENS[t] for t in tokens if t in _ORCA_SIMPLE_TASK_TOKENS}
    geom = blocks.get("geom", [])
    neb = blocks.get("neb", [])
    for i, token in enumerate(neb):
        if token.partition("=")[0] == "neb_ts":
            tail = [token.partition("=")[2]] if "=" in token else [t for t in neb[i + 1:i + 3] if t != "="]
            if tail and tail[0] == "true":
                tasks.add("ts_opt")
            elif tail and tail[0] == "false":
                tasks.discard("ts_opt")
    if "scan" in geom:
        tasks.discard("minimum_opt")
        tasks.add("relaxed_scan")
    if not tasks and tokens:
        tasks.add("single_point")
    constraints = []
    for raw in _orca_code(text).splitlines():
        tokens_c = raw.replace("{", " { ").replace("}", " } ").split()
        if "{" in tokens_c and "}" in tokens_c:
            start, end = tokens_c.index("{"), tokens_c.index("}")
            body = tokens_c[start + 1:end]
            if len(body) >= 4 and body[0].upper() in {"B", "A", "D", "C"} and body[-1].upper() == "C":
                constraints.append(dict(type={"B": "bond", "A": "angle", "D": "dihedral", "C": "cartesian"}[body[0].upper()], atoms=[int(x) for x in body[1:-2]], value=float(body[-2])))
    provider = None
    method_tokens = blocks.get("method", [])
    if "extopt" in tokens and "progext" in method_tokens:
        pos = method_tokens.index("progext")
        if pos + 1 < len(method_tokens):
            provider = Path(method_tokens[pos + 1].strip("\"'")).name.lower()
    charges = _native_charges(text, "orca")
    return CalculationIntent(engine="orca", provider=provider, tasks=tasks,
        frequency_mode="numeric" if "numfreq" in tokens else "analytic" if "freq" in tokens else "auto",
        constraints=constraints, charge=charges[0][0] if charges else None,
        multiplicity=charges[0][1] if charges else None,
        method_signature=f"external:{provider}" if provider else None,
        certainty="known" if tasks else "unknown")


def _inspect_gaussian(text: str) -> CalculationIntent:
    routes = gaussian_routes(text)
    tasks, provider, mode = set(), None, "auto"
    for route in routes:
        for token in route:
            head, opening, options = token.partition("(")
            if opening and head.removesuffix("=") in {"opt", "freq", "irc", "scan"}:
                key = head.removesuffix("=")
                value = options.removesuffix(")")
            else:
                key, _, value = token.partition("=")
            if key == "opt":
                options = set(value.strip("()").replace(" ", "").split(","))
                tasks.add("ts_opt" if options & {"ts", "qst2", "qst3"} else "minimum_opt")
            elif key == "freq":
                tasks.add("frequency")
                if value.strip("()").split(",")[0] in _FREQ_NUMERIC_ALIASES:
                    mode = "numeric"
            elif key in {"irc", "scan"}:
                tasks.add("irc" if key == "irc" else "relaxed_scan")
            elif key == "external" and value:
                provider = Path(value.strip("\"'")).name.lower()
    if not tasks and routes:
        tasks.add("single_point")
    constraints = []
    for line in text.splitlines():
        tokens = line.upper().split()
        if tokens and tokens[0] in {'B','A','D'} and 'S' in tokens:
            if 'minimum_opt' in tasks:
                tasks.remove('minimum_opt')
                tasks.add('relaxed_scan')
        if tokens and tokens[0] in {'B','A','D'} and tokens[-1] == 'F':
            constraints.append(dict(type=tokens[0], atoms=tokens[1:-1]))
    charges = _native_charges(text, "gaussian")
    return CalculationIntent(engine="gaussian", provider=provider, tasks=tasks, constraints=constraints,
        frequency_mode=mode, charge=charges[0][0] if charges else None,
        multiplicity=charges[0][1] if charges else None,
        method_signature=f"external:{provider}" if provider else None,
        certainty="known" if routes else "unknown")


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


def _gaussian_trailing_cards(content):
    cards = []
    segments = [[]]
    for line in content.splitlines():
        if line.strip().lower() == '--link1--':
            segments.append([])
        else:
            segments[-1].append(line)
    for segment in segments:
        charge_index = None
        for index, line in enumerate(segment):
            tokens = line.split()
            if len(tokens) != 2:
                continue
            try:
                int(tokens[0])
                int(tokens[1])
            except ValueError:
                continue
            charge_index = index
            break
        tail = []
        if charge_index is not None:
            after_geometry = False
            for line in segment[charge_index + 1:]:
                if not after_geometry and not line.strip():
                    after_geometry = True
                elif after_geometry and line.strip():
                    tail.extend(native_tokens(line))
        cards.append(tail)
    return cards


def _generated_gaussian_coordinates(tokens):
    i = 0
    while i < len(tokens):
        count = {'b': 2, 'a': 3, 'd': 4}.get(tokens[i])
        if count is None or i + count + 1 >= len(tokens):
            return False
        try:
            for atom in tokens[i+1:i+count+1]:
                int(atom)
            i += count + 1
            if tokens[i] == 'f':
                i += 1
            elif tokens[i] == 's' and i + 2 < len(tokens):
                int(tokens[i+1])
                float(tokens[i+2])
                i += 3
            else:
                return False
        except ValueError:
            return False
    return True


def _writer_orca_controls(name, tokens):
    if name in ('pal', 'maxcore'):
        return True  # Shared admission independently validates resources.
    allowed = {'geom': {'calc_hess','true','inhess','read','inhessname','scan','simul_scan','constraints','b','a','d','c','{','}','=','end'},
        'irc': {'direction','both','inithess','read','calc_numfreq','hess_filename','end'}}.get(name)
    if allowed is None:
        return not tokens
    for i, token in enumerate(tokens):
        if token in allowed:
            continue
        if i and tokens[i - 1] in ('inhessname','hess_filename'):
            continue
        try:
            for value in token.split('='):
                float(value.rstrip(','))
        except ValueError:
            return False
    return True


class MethodDifference(BaseModel):
    field: str
    expected: object
    actual: object
    message: str


def compare_calculation_input(content: str, expected: Mapping[str, object], *, charge: int, multiplicity: int) -> list[MethodDifference]:
    """Compare the complete accepted declaration with every native method card.

    Scheduling resources and writer-owned task/geometry controls are independent
    of the electronic-structure contract. Unrecognized electronic tokens remain
    visible differences, rather than being guessed into an allowed method.
    """
    from cloudra.runtime_v2.method_policy import _norm_basis
    engine = str(expected["engine"]).lower()
    differences = []
    def diff(field, want, got):
        if want != got:
            differences.append(MethodDifference(field=field, expected=want, actual=got, message=f"{field}: expected {want!r}; actual {got!r}"))
    try:
        actual = inspect_input(content, engine=engine)
        diff("certainty", "known", actual.certainty)
        charges = _native_charges(content, engine)
        diff("charge", [charge] * max(1, len(charges)), [c for c, _ in charges])
        diff("multiplicity", [multiplicity] * max(1, len(charges)), [m for _, m in charges])
        family = str(expected["method"]).strip().lower()
        basis = str(expected["basis_set"]).strip()
        want_method = [family] + ([_norm_basis(basis)] if basis else [])
        want_keywords = sorted(t.replace(" ", "") for t in native_tokens(str(expected.get("keywords") or "")))
        if engine == "orca":
            tokens, blocks = orca_directives(content)
            cards = [[t for t in tokens if t not in _ORCA_SIMPLE_TASK_TOKENS and t not in {"sp"}]]
            expected_blocks = orca_directives(str(expected.get("orca_blocks") or ""))[1]
            # These blocks are generated by the writer for the requested task;
            # other blocks must exactly match the explicit native declaration.
            owned = {'pal', 'maxcore', 'geom', 'irc'}
            for name in sorted(set(blocks) | set(expected_blocks)):
                actual_block = list(blocks.get(name, []))
                expected_block = list(expected_blocks.get(name, []))
                if name not in owned:
                    diff('orca_blocks', (name, expected_blocks.get(name)), (name, blocks.get(name)))
                    continue
                if expected_block:
                    position = next((i for i in range(len(actual_block)) if actual_block[i:i+len(expected_block)] == expected_block), None)
                    if position is None:
                        diff('orca_blocks', (name, expected_block), (name, actual_block))
                        continue
                    del actual_block[position:position+len(expected_block)]
                if not _writer_orca_controls(name, actual_block):
                    diff('orca_blocks', (name, 'only explicit settings and writer task controls'), (name, actual_block))
        elif engine == "gaussian":
            trailing = _gaussian_trailing_cards(content)
            expected_tail = native_tokens(str(expected.get('end_setting') or ''))
            for tail in trailing:
                # Generated ModRedundant scan/freeze cards are task coordinates,
                # not extra electronic settings. All other trailing directives
                # must be explicitly declared.
                if 'relaxed_scan' in actual.tasks:
                    remaining_tail = list(tail)
                    if expected_tail:
                        position = next((i for i in range(len(tail)) if tail[i:i+len(expected_tail)] == expected_tail), None)
                        if position is None:
                            diff('end_setting', expected_tail, tail)
                            continue
                        del remaining_tail[position:position+len(expected_tail)]
                    if not _generated_gaussian_coordinates(remaining_tail):
                        diff('end_setting', 'only explicit settings and generated scan coordinates', tail)
                else:
                    diff('end_setting', expected_tail, tail)
            cards = [[t for t in card if t.partition("=")[0] not in {"opt", "freq", "irc", "scan", "sp"}] for card in gaussian_routes(content)]
        else:
            diff("engine", "native ORCA or Gaussian input", engine)
            return differences
        for card in cards:
            remaining = list(card)
            if engine == "gaussian":
                matched = next((t for t in remaining if (t == family if not basis else t == family + '/' + basis.lower() or (t.rpartition('/')[0] == family and _norm_basis(t.rpartition('/')[2]) == _norm_basis(basis)))), None)
                diff("method", family + ("/" + _norm_basis(basis) if basis else ""), (matched.rpartition("/")[0] + "/" + _norm_basis(matched.rpartition("/")[2]) if basis else matched) if matched else None)
                if matched:
                    remaining.remove(matched)
            else:
                for token in want_method:
                    matched = next((t for t in remaining if (t == token if token == family else _norm_basis(t) == token)), None)
                    diff("method", token, (matched if token == family else _norm_basis(matched)) if matched else None)
                    if matched:
                        remaining.remove(matched)
            diff("keywords", want_keywords, sorted(t.replace(" ", "") for t in remaining))
        mode = expected.get("frequency_mode", "auto")
        if "frequency" in actual.tasks and mode != "auto":
            diff("frequency_mode", mode, actual.frequency_mode)
        if expected.get("end_setting"):
            # Native trailing directives remain ordered; require an exact token
            # sequence at the end, including every scientific setting.
            tail = native_tokens(str(expected["end_setting"]))
            diff("end_setting", tail, native_tokens(content)[-len(tail):])
    except (ValueError, TypeError, KeyError) as exc:
        differences.append(MethodDifference(field="parse", expected="determinate native input", actual=str(exc), message=str(exc)))
    return differences


def native_input_geometry(content: str, *, engine: str) -> list[tuple[str, tuple[float, float, float]]]:
    """Read one Cartesian geometry; unsupported/ambiguous cards fail loudly."""
    lines = content.splitlines()
    starts = []
    for i, line in enumerate(lines):
        tokens = line.strip().split()
        if engine == "orca":
            if len(tokens) == 4 and tokens[:2] == ["*", "xyz"]:
                starts.append(i + 1)
        elif len(tokens) == 2:
            try:
                int(tokens[0])
                int(tokens[1])
            except ValueError:
                continue
            starts.append(i + 1)
    if len(starts) != 1:
        raise ValueError("Exactly one explicit Cartesian input geometry is required")
    atoms = []
    for line in lines[starts[0]:]:
        tokens = line.strip().split()
        if not tokens or tokens == ["*"]:
            break
        if len(tokens) != 4:
            raise ValueError("Unsupported native Cartesian geometry card")
        atoms.append((tokens[0], tuple(float(x) for x in tokens[1:])))
    if not atoms:
        raise ValueError("Native input geometry is missing")
    return atoms
