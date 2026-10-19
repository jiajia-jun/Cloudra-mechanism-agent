"""Shared calculation-intent model for QM input generation and inspection.

One semantic model is used by three parties so that "what was requested" and
"what the file actually asks the engine to do" can be compared instead of
trusted:

- ``intent_from_writer`` normalizes qm_input_writer arguments;
- ``validate_writer_request`` returns visible advice about calculation options;
  malformed structured task entries have ``severity='error'``;
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

# These aliases support classification, never an engine capability whitelist.
_WRITER_TASK_KEYS = frozenset({"opt", "freq", "irc", "scan", "sp", "single_point"})

# writer 键 -> 规范化键（规范化入口：语义等价拼写在进入 seen/tasks 前统一）
_WRITER_KEY_CANONICAL = {"sp": "single_point"}

_GAUSSIAN_ONLY_OPT_SUBOPTIONS = {"calcfc", "noeigen", "calcall", "qst2", "qst3"}

_FREQ_NUMERIC_ALIASES = {"num", "numer", "numeric", "numfreq"}

# Native tasks outside Cloudra's canonical task vocabulary remain unclassified.
# Recognizing them prevents a workflow default from adding an unrelated task.
_NATIVE_UNCLASSIFIED_TASK_TOKENS = {
    'orca': {'engrad', 'gradient', 'md', 'eprnmr', 'nmr', 'polar', 'neb', 'neb-ci'},
    'gaussian': {'force', 'gradient', 'nmr', 'polar', 'bomd', 'admp', 'stable', 'volume'},
}



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


def _entry(code: str, field: str, message: str, *, severity: str = 'warning') -> dict:
    return {"code": code, "field": field, "message": message, "severity": severity}


# ----------------------------------------------------------------------
# writer arguments -> intent / validation
# ----------------------------------------------------------------------


def _gaussian_keyword(token: str) -> tuple[str, str]:
    head, opening, options = token.partition('(')
    if opening and head.removesuffix('=') in {'opt', 'freq', 'irc', 'scan'}:
        return head.removesuffix('='), options.removesuffix(')')
    key, _, value = token.partition('=')
    return key, value


def _gaussian_tasks(tokens: list[str]) -> set[str]:
    tasks = set()
    for token in tokens:
        key, value = _gaussian_keyword(token)
        if key == 'opt':
            options = set(value.strip('()').replace(' ', '').split(','))
            tasks.add('ts_opt' if options & {'ts', 'qst2', 'qst3'} else 'minimum_opt')
        elif key == 'freq':
            tasks.add('frequency')
        elif key in {'irc', 'scan', 'sp'}:
            tasks.add({'irc': 'irc', 'scan': 'relaxed_scan', 'sp': 'single_point'}[key])
    return tasks


def _gaussian_modredundant(tokens: list[str]) -> bool:
    return any(key == 'opt' and 'modredundant' in value.strip('()').replace(' ', '').split(',')
               for key, value in map(_gaussian_keyword, tokens))


def _gaussian_scan_cards(tokens: list[str]) -> bool:
    """Recognize typed ModRedundant S cards, not letters in a title or basis."""
    for index, token in enumerate(tokens):
        count = {'b': 2, 'a': 3, 'd': 4}.get(token)
        if count is None or index + count + 3 >= len(tokens):
            continue
        try:
            for atom in tokens[index + 1:index + count + 1]:
                if atom != '*':
                    int(atom)
            action = index + count + 1
            if tokens[action] != 's':
                float(tokens[action])  # An optional explicit coordinate value.
                action += 1
            if tokens[action] == 's' and action + 2 < len(tokens):
                int(tokens[action + 1])
                float(tokens[action + 2])
                return True
        except (ValueError, IndexError):
            continue
    return False


def declared_native_tasks(arguments: Mapping[str, Any]) -> tuple[set[str], list[str]]:
    """Normalize declared tasks and native keywords independently of rendering."""
    tasks: set[str] = set()
    unknown: list[str] = []
    engine = str(arguments.get('engine') or 'gaussian').lower()
    opt_tokens = []
    for task in arguments.get("task_type") or []:
        if not isinstance(task, dict):
            unknown.append(repr(task))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            params = str(value).lower() if value is not None else ""
            if key_l not in _WRITER_TASK_KEYS:
                if engine == 'orca' and key_l in _ORCA_SIMPLE_TASK_TOKENS:
                    tasks.add(_ORCA_SIMPLE_TASK_TOKENS[key_l])
                else:
                    unknown.append(key_l)
                continue
            if key_l == "opt":
                opt_tokens.append('opt=' + params)
                ts_options = {'ts', 'qst2', 'qst3'} if engine == 'gaussian' else {'ts'}
                if ts_options & {p.strip(' ()') for p in params.split(",") if p.strip()}:
                    tasks.add("ts_opt")
                else:
                    tasks.add("minimum_opt")
            elif key_l == "freq":
                tasks.add("frequency")
            elif key_l == "irc":
                tasks.add("irc")
            elif key_l == "scan":
                if engine == 'gaussian':
                    tasks.add("relaxed_scan")
                else:
                    unknown.append(key_l)
            elif key_l in ("sp", "single_point"):
                tasks.add("single_point")
    try:
        tokens = native_tokens(str(arguments.get('keywords') or ''))
        if engine == 'gaussian':
            tasks.update(_gaussian_tasks(tokens))
            if ('minimum_opt' in tasks and _gaussian_modredundant(opt_tokens + tokens)
                    and _gaussian_scan_cards(native_tokens(str(arguments.get('end_setting') or '')))):
                tasks.remove('minimum_opt')
                tasks.add('relaxed_scan')
        elif engine == 'orca':
            tasks.update(_ORCA_SIMPLE_TASK_TOKENS[token] for token in tokens if token in _ORCA_SIMPLE_TASK_TOKENS)
            geom = orca_directives(str(arguments.get('orca_blocks') or ''))[1].get('geom', [])
            if 'scan' in geom:
                tasks.discard('minimum_opt')
                tasks.add('relaxed_scan')
        unknown.extend(token for token in tokens
                       if token.partition('=')[0].partition('(')[0] in _NATIVE_UNCLASSIFIED_TASK_TOKENS.get(engine, set()))
    except ValueError as exc:
        unknown.append(str(exc))
    return tasks, unknown


def _frequency_declarations(arguments: dict[str, Any]) -> list[tuple[str, str]]:
    declarations = []
    mode = str(arguments.get('frequency_mode') or 'auto').lower()
    if mode in {'numeric', 'analytic'}:
        declarations.append(('frequency_mode', mode))
    for task in arguments.get('task_type') or []:
        if isinstance(task, dict):
            for key, value in task.items():
                if str(key).lower() == 'freq' and value is not None:
                    for option in str(value).strip(' ()').lower().split(','):
                        if option in _FREQ_NUMERIC_ALIASES or option == 'analytic':
                            declarations.append(('task_type', 'numeric' if option in _FREQ_NUMERIC_ALIASES else 'analytic'))
    tokens = native_tokens(str(arguments.get('keywords') or ''))
    if str(arguments.get('engine') or 'gaussian').lower() == 'gaussian':
        for key, value in map(_gaussian_keyword, tokens):
            if key == 'freq':
                options = set(value.strip('()').split(','))
                declarations.append(('keywords', 'numeric' if options & _FREQ_NUMERIC_ALIASES else 'analytic'))
    else:
        declarations.extend(('keywords', 'numeric' if token == 'numfreq' else 'analytic')
                            for token in tokens if token in {'numfreq', 'freq'})
    return declarations


def _writer_frequency_mode(arguments: dict[str, Any]) -> str:
    mode = str(arguments.get("frequency_mode") or "auto").lower()
    if mode != "auto":
        return mode
    try:
        declarations = _frequency_declarations(arguments)
    except ValueError:
        return 'auto'  # validate_writer_request reports the malformed native field.
    if declarations:
        return declarations[0][1]
    return "auto"


def intent_from_writer(arguments: dict[str, Any]) -> CalculationIntent:
    """Normalize qm_input_writer arguments into a CalculationIntent."""
    engine = str(arguments.get("engine") or "gaussian").lower()
    tasks, unknown = declared_native_tasks(arguments)
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
        frequency_mode=_writer_frequency_mode(arguments),  # type: ignore[arg-type]
        charge=arguments.get("charge"),
        multiplicity=arguments.get("multiplicity"),
        method_signature=method_signature,
        certainty=certainty,
    )


def validate_writer_request(arguments: dict[str, Any]) -> list[dict]:
    """Return model-visible option advice and structural syntax errors.

    Engine-specific settings are preserved even when questionable. Only an
    ``error`` entry means the request cannot be structurally interpreted.
    """
    entries: list[dict] = []
    engine = str(arguments.get("engine") or "gaussian").lower()
    task_type = arguments.get("task_type") or []
    from cloudra.tools.core.qm_keywords import is_basis_keyword

    method = str(arguments.get('method') or '')
    basis = str(arguments.get('basis_set') or '')
    _, separator, suffix = method.partition('/')
    if any(character.isspace() for character in method) or is_basis_keyword(method) or (separator and is_basis_keyword(suffix)):
        entries.append(_entry('native_method_layout', 'method',
            'method contains a basis or multiple native tokens. Its text is preserved; use separate method, basis_set and keywords fields to make the declaration unambiguous.'))
    if any(character.isspace() for character in basis):
        entries.append(_entry('native_basis_layout', 'basis_set',
            'basis_set contains multiple native tokens. Its text is preserved; check the engine basis syntax.'))
    for token in str(arguments.get('keywords') or '').split():
        head, slash, tail = token.rpartition('/')
        auxiliary = slash and is_basis_keyword(head) and tail.lower() in {'j', 'jk', 'jksmall', 'c'}
        if not auxiliary and (is_basis_keyword(token) or (slash and is_basis_keyword(tail))):
            entries.append(_entry('orbital_basis_in_keywords', 'keywords',
                f'Native keywords contain orbital basis {token!r}; its text is preserved. Review it together with basis_set.'))
    for field in ('method', 'basis_set', 'orca_blocks', 'end_setting'):
        try:
            native_tokens(str(arguments.get(field) or ''))
        except ValueError as exc:
            entries.append(_entry('malformed_native_' + field, field, str(exc)))

    seen: dict[str, Any] = {}
    for task in task_type:
        if not isinstance(task, dict):
            entries.append(_entry(
                "malformed_task", "task_type",
                f"task_type entries must be dicts like {{'opt': None}}; got {task!r}.",
                severity='error',
            ))
            continue
        for key, value in task.items():
            key_l = str(key).lower()
            try:
                native_tokens(str(key) + ('=' + str(value) if value is not None else ''))
            except ValueError as exc:
                entries.append(_entry('malformed_native_task', 'task_type', str(exc)))
            if key_l not in _WRITER_TASK_KEYS and not (engine == 'orca' and key_l in _ORCA_SIMPLE_TASK_TOKENS):
                entries.append(_entry(
                    "unknown_task_key", "task_type",
                    f"Task {key!r} is outside Cloudra's task classification; its native spelling "
                    "and value are preserved. Check the engine's task syntax.",
                ))
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

    tasks, _ = declared_native_tasks(arguments)
    try:
        tokens = native_tokens(str(arguments.get('keywords') or ''))
        declarations = _frequency_declarations(arguments)
    except ValueError as exc:
        entries.append(_entry('malformed_native_keywords', 'keywords', str(exc)))
        tokens, declarations = [], []
    if len({mode for _, mode in declarations}) > 1:
        entries.append(_entry('conflicting_frequency_mode', 'keywords' if any(field == 'keywords' for field, _ in declarations) else 'frequency_mode',
            'Conflicting frequency evaluation settings: ' + ', '.join(f'{field}={mode}' for field, mode in declarations)
            + '; declare one consistent analytic/numeric evaluation.'))
    if engine == 'gaussian':
        opt_tasks = _gaussian_tasks(tokens) & {'minimum_opt', 'ts_opt'}
        if 'opt' in seen:
            opt_tasks.update(_gaussian_tasks(['opt=' + str(seen['opt'] or '').lower()]))
    else:
        opt_tasks = {_ORCA_SIMPLE_TASK_TOKENS[token] for token in tokens
                     if token in _ORCA_SIMPLE_TASK_TOKENS} & {'minimum_opt', 'ts_opt'}
        if 'opt' in seen:
            opt_tasks.add('ts_opt' if 'ts' in str(seen['opt']).lower().split(',') else 'minimum_opt')
    if len(opt_tasks) > 1:
        entries.append(_entry('conflicting_task', 'keywords',
            'task_type and keywords declare conflicting minimum and TS optimizations; keep one consistent opt declaration.'))
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
        try:
            raw_blocks = str(arguments.get('orca_blocks') or '')
            block_tokens = native_tokens(raw_blocks)
            for index, token in enumerate(block_tokens):
                if token.startswith('%') and token != '%maxcore':
                    following = next((i for i in range(index + 1, len(block_tokens)) if block_tokens[i].startswith('%')), len(block_tokens))
                    if 'end' not in block_tokens[index + 1:following] and token not in {'%base', '%moinp', '%pointcharges'}:
                        entries.append(_entry('malformed_native_blocks', 'orca_blocks',
                            f'Native block {token} has no closing end; the original block text is preserved.'))
        except ValueError as exc:
            entries.append(_entry('malformed_native_blocks', 'orca_blocks', str(exc)))
        _, malformed_constraints = _orca_constraints(str(arguments.get('orca_blocks') or ''))
        for message in malformed_constraints:
            entries.append(_entry('native_constraint_parameters', 'orca_blocks', message))
        if "scan" in seen:
            entries.append(_entry(
                "scan_requires_ts_guess", "task_type",
                "ORCA scans need native %geom Scan coordinates, or ts_guess mode='scan_prepare'. "
                "The declared native text is preserved; a task label alone does not define a scan.",
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
                remaining = sorted(params - {'ts'} - _GAUSSIAN_ONLY_OPT_SUBOPTIONS)
                if remaining:
                    entries.append(_entry('native_task_parameters', 'task_type',
                        f"ORCA opt parameters {remaining} are passed through unchanged after the task keyword; "
                        "use native keywords (for example TightOpt) or orca_blocks for engine-specific controls."))
            if key == "freq" and value is not None:
                unknown_freq = sorted(params - _FREQ_NUMERIC_ALIASES - {'analytic'})
                if unknown_freq:
                    entries.append(_entry(
                        "unknown_freq_suboption", "task_type",
                        f"Unknown ORCA freq sub-options {unknown_freq}; use "
                        "frequency_mode='numeric' for NumFreq or native orca_blocks.",
                    ))
            if key in {'irc', 'scan', 'single_point'} and value is not None:
                entries.append(_entry('native_task_parameters', 'task_type',
                    f"ORCA {key} parameters {value!r} are preserved verbatim; check native keyword/% block syntax."))
        if str(arguments.get("end_setting") or "").strip():
            entries.append(_entry(
                "gaussian_only_field", "end_setting",
                "end_setting is a Gaussian end-of-file section; ORCA has no such "
                "card — express the setting in orca_blocks instead.",
            ))
    elif engine == 'gaussian':
        from cloudra.tools.core.native_input_sections import gaussian_coordinate_units

        if gaussian_coordinate_units(tokens) == 'unknown':
            entries.append(_entry('unknown_coordinate_units', 'keywords',
                'Gaussian coordinate units are unknown or conflicting; the native declaration is preserved. Coordinate conversion cannot be determined.'))
        if arguments.get('orca_blocks'):
            entries.append(_entry('orca_only_field', 'orca_blocks',
                'orca_blocks is not Gaussian syntax; its text is preserved in the trailing section.'))
        if 'scan' in seen and str(seen['scan']).lower() != 'rigid':
            entries.append(_entry('gaussian_scan_semantics', 'task_type',
                "Gaussian scan is RIGID; RELAXED scans use opt=modredundant and trailing coordinates. "
                "The original task and parameters are preserved."))
        hessian_options = {'calcfc', 'calcall', 'readfc', 'rcfc'}
        task_tokens = [str(key) + '=' + str(value or '').lower() for key, value in seen.items() if key in {'opt', 'irc'}]
        for token in tokens + task_tokens:
            key, value = _gaussian_keyword(token)
            options = set(value.strip('()').replace(' ', '').split(','))
            if key == 'opt' and 'ts' in options and not options & hessian_options:
                entries.append(_entry('initial_hessian_unspecified', 'task_type' if 'opt' in seen else 'keywords',
                    'Gaussian TS optimization has no explicit initial-Hessian setting; review the native engine defaults for this calculation. No solver option was added.'))
            elif key == 'irc' and not options & hessian_options:
                entries.append(_entry('initial_hessian_unspecified', 'keywords',
                    'Gaussian IRC has no explicit initial-Hessian setting; review the native engine defaults for this calculation. No solver option was added.'))
    return entries


# ----------------------------------------------------------------------
# generated/input text -> intent
# ----------------------------------------------------------------------

_ORCA_SIMPLE_TASK_TOKENS = {
    "sp": "single_point",
    "opt": "minimum_opt",
    "tightopt": "minimum_opt",
    "verytightopt": "minimum_opt",
    "looseopt": "minimum_opt",
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
    from cloudra.tools.core.native_input_sections import gaussian_sections

    return [native_tokens(' '.join(section.route)) for section in gaussian_sections(text)]


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
    from cloudra.tools.core.native_input_sections import gaussian_sections, orca_xyz_sections

    if engine == 'orca':
        return [charge for charge, _ in orca_xyz_sections(text)]
    return [section.charge for section in gaussian_sections(text) if section.charge is not None]


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
    constraints, _ = _orca_constraints(text)
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


def _orca_constraints(text: str) -> tuple[list[dict], list[str]]:
    constraints, messages = [], []
    for raw in _orca_code(text).splitlines():
        tokens_c = raw.replace("{", " { ").replace("}", " } ").split()
        if "{" in tokens_c and "}" in tokens_c:
            start, end = tokens_c.index("{"), tokens_c.index("}")
            body = tokens_c[start + 1:end]
            if len(body) >= 4 and body[0].upper() in {"B", "A", "D", "C"} and body[-1].upper() == "C":
                try:
                    constraints.append(dict(type={"B": "bond", "A": "angle", "D": "dihedral", "C": "cartesian"}[body[0].upper()], atoms=[int(x) for x in body[1:-2]], value=float(body[-2])))
                except ValueError as exc:
                    messages.append(f'Native constraint {raw.strip()!r} could not be interpreted ({exc}); its original text is preserved.')
    return constraints, messages


def _inspect_gaussian(text: str) -> CalculationIntent:
    routes = gaussian_routes(text)
    tasks, provider, mode = set(), None, "auto"
    trailing = _gaussian_trailing_cards(text)
    for index, route in enumerate(routes):
        route_tasks = _gaussian_tasks(route)
        if ('minimum_opt' in route_tasks and _gaussian_modredundant(route)
                and index < len(trailing) and _gaussian_scan_cards(trailing[index])):
            route_tasks.remove('minimum_opt')
            route_tasks.add('relaxed_scan')
        tasks.update(route_tasks)
        for token in route:
            key, value = _gaussian_keyword(token)
            if key == "freq":
                mode = 'numeric' if set(value.strip('()').split(',')) & _FREQ_NUMERIC_ALIASES else 'analytic'
            elif key == "external" and value:
                provider = Path(value.strip("\"'")).name.lower()
    constraints = []
    for line in text.splitlines():
        tokens = line.upper().split()
        if tokens and tokens[0] in {'B','A','D'} and tokens[-1] == 'F':
            constraints.append(dict(type=tokens[0], atoms=tokens[1:-1]))
    charges = _native_charges(text, "gaussian")
    return CalculationIntent(engine="gaussian", provider=provider, tasks=tasks, constraints=constraints,
        frequency_mode=mode, charge=charges[0][0] if charges else None,
        multiplicity=charges[0][1] if charges else None,
        method_signature=f"external:{provider}" if provider else None,
        certainty="known" if tasks else "unknown")


def inspect_input(text: str, *, engine: str) -> CalculationIntent:
    """Re-read an input file's text and report the intent it actually encodes."""
    engine_l = engine.lower()
    try:
        if engine_l == "orca":
            return _inspect_orca(text)
        if engine_l == "gaussian":
            return _inspect_gaussian(text)
    except ValueError:
        return CalculationIntent(engine=engine_l, certainty='unknown')
    return CalculationIntent(engine=engine_l, certainty="unknown")


def geometry_hash_of(xyz_block: str) -> str:
    """Stable hash over coordinate lines (element + xyz), for intent linking."""
    lines = [ln.strip() for ln in xyz_block.splitlines() if ln.strip()]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def _gaussian_trailing_cards(content):
    from cloudra.tools.core.native_input_sections import gaussian_sections

    return [native_tokens(' '.join(section.trailing)) for section in gaussian_sections(content)]


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
    allowed = {'geom': {'scan','simul_scan','constraints','b','a','d','c','{','}','=','end'}}.get(name)
    if allowed is None:
        return not tokens
    for token in tokens:
        if token in allowed:
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
        charges = _native_charges(content, engine)
        diff("charge", [charge] * max(1, len(charges)), [c for c, _ in charges])
        diff("multiplicity", [multiplicity] * max(1, len(charges)), [m for _, m in charges])
        family = str(expected["method"]).strip().lower()
        basis = str(expected["basis_set"]).strip()
        want_method = [family] + ([_norm_basis(basis)] if basis else [])
        want_keywords = sorted(t.replace(" ", "") for t in native_tokens(str(expected.get("keywords") or "")))
        if engine == "orca":
            tokens, blocks = orca_directives(content)
            native_cards = [tokens]
            cards = [[t for t in tokens if t not in _ORCA_SIMPLE_TASK_TOKENS and t not in {"sp"}]]
            declared_tasks = [t for t in want_keywords if t in _ORCA_SIMPLE_TASK_TOKENS or t == 'sp']
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
            expected_tail = native_tokens('\n'.join(filter(None, [str(expected.get('end_setting') or ''), str(expected.get('orca_blocks') or '')])))
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
            native_cards = gaussian_routes(content)
            cards = [[t for t in card if _gaussian_keyword(t)[0] not in {"opt", "freq", "irc", "scan", "sp"}] for card in native_cards]
            declared_tasks = [t for t in want_keywords if _gaussian_keyword(t)[0] in {'opt', 'freq', 'irc', 'scan', 'sp'}]
        else:
            diff("engine", "native ORCA or Gaussian input", engine)
            return differences
        # Writer-owned task controls may be added independently, but a task
        # explicitly present in keywords must survive with its exact options.
        for native_card, card in zip(native_cards, cards, strict=True):
            available = [token.replace(' ', '') for token in native_card]
            for token in declared_tasks:
                if token in available:
                    card.append(token)
                    available.remove(token)
        for card in cards:
            remaining = list(card)
            if engine == "gaussian":
                if family == 'external':
                    matched = next((token for token in remaining if _gaussian_keyword(token)[0] == 'external'), None)
                    actual_method = 'external' if matched else None
                elif basis:
                    matched = next((token for token in remaining if token == family + '/' + basis.lower()
                        or (token.rpartition('/')[0] == family and _norm_basis(token.rpartition('/')[2]) == _norm_basis(basis))), None)
                    actual_method = matched.rpartition('/')[0] + '/' + _norm_basis(matched.rpartition('/')[2]) if matched else None
                else:
                    matched = next((token for token in remaining if token == family), None)
                    actual_method = matched
                diff("method", family + ("/" + _norm_basis(basis) if basis else ""), actual_method)
                if matched and family != 'external':
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
        if engine == 'orca' and expected.get("end_setting"):
            # Native trailing directives remain ordered; require an exact token
            # sequence at the end, including every scientific setting.
            tail = native_tokens(str(expected["end_setting"]))
            diff("end_setting", tail, native_tokens(content)[-len(tail):])
    except (ValueError, TypeError, KeyError) as exc:
        differences.append(MethodDifference(field="parse", expected="determinate native input", actual=str(exc), message=str(exc)))
    return differences


def native_input_geometry(content: str, *, engine: str) -> list[tuple[str, tuple[float, float, float]]]:
    """Read one explicit Cartesian geometry in Angstrom, preserving atom order."""
    from cloudra.tools.core.molecule import _cartesian_atoms, _read_gaussian_structure
    from cloudra.tools.core.native_input_sections import orca_xyz_sections

    if engine.lower() == 'gaussian':
        atoms, _, _, _ = _read_gaussian_structure(content)
    elif engine.lower() == 'orca':
        sections = orca_xyz_sections(content)
        if len(sections) != 1:
            raise ValueError("Exactly one explicit Cartesian input geometry is required")
        atoms = _cartesian_atoms(sections[0][1], source='ORCA')
    else:
        raise ValueError(f"Unsupported native geometry engine: {engine}")
    return [(symbol, tuple(map(float, point))) for symbol, point in zip(
        atoms.get_chemical_symbols(), atoms.get_positions(), strict=True,
    )]
