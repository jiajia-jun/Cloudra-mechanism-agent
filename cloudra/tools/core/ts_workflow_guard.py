"""Read operation evidence for TS guidance and approval; never execute inspected code.

Native task recognition belongs to calculation_intent. Shell tokens only locate
actual executable inputs; opaque script contents remain data for the reviewer.
Call this synchronous reader through asyncio.to_thread from async callers.
"""

from __future__ import annotations

from pathlib import Path

from cloudra.tools.core.calculation_intent import inspect_input, intent_from_writer
from cloudra.tools.core.command_analyzer import BashCommandClassifier

_TS_TASKS = {'ts_opt', 'irc'}
_ENGINE_COMMANDS = {'orca': 'orca', 'g03': 'gaussian', 'g09': 'gaussian',
                    'g16': 'gaussian', 'gaussian': 'gaussian'}
_SHELLS = {'bash', 'sh', 'zsh'}
_PYTHONS = {'python', 'python2', 'python3'}
_SCRIPT_SUFFIXES = {'.sh', '.bash', '.zsh', '.py'}


def native_ts_tasks(text: str, *, engine: str) -> set[str]:
    """Recognize native TS/IRC tasks, excluding titles, comments and plain scans."""
    return inspect_input(text, engine=engine).tasks & _TS_TASKS


def _path(value: str, workspace_dir: str | None) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = Path(workspace_dir or Path.cwd()) / path
    return str(path.resolve())


def _read(value: str, workspace_dir: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    candidates = [_path(value, workspace_dir)]
    if not Path(value).is_absolute():
        candidates.append(_path(value, None))
    for candidate in dict.fromkeys(candidates):
        try:
            return candidate, Path(candidate).read_text(encoding='utf-8', errors='replace')
        except (OSError, ValueError):
            continue
    return None


def _native(result: dict, text: str, path: str, engine: str | None = None) -> None:
    for native_engine in (engine,) if engine else ('gaussian', 'orca'):
        tasks = sorted(native_ts_tasks(text, engine=native_engine))
        if not tasks:
            continue
        entry = {'path': path, 'engine': native_engine, 'tasks': tasks}
        inputs = result.setdefault('ts_inputs', [])
        if entry not in inputs:
            inputs.append(entry)


def _script(result: dict, path: str, content: str) -> None:
    entry = {'path': path, 'content': content}
    scripts = result.setdefault('scripts', [])
    if entry not in scripts:
        scripts.append(entry)


def _command(command: str, workspace_dir: str | None, result: dict, *, read_scripts: bool) -> None:
    try:
        segments = BashCommandClassifier.classify(command).segments
    except ValueError:
        return
    for segment in segments:
        words = segment.words
        if not words:
            continue
        program = Path(words[0]).name.lower()
        if program == 'cd' and len(words) == 2:
            workspace_dir = _path(words[1], workspace_dir)
        elif program in _ENGINE_COMMANDS:
            result['direct_execution'] = True
            inputs = [target for operator, target in segment.redirects if operator == '<']
            inputs.extend(word for word in words[1:] if not word.startswith('-'))
            if inputs and (source := _read(inputs[0], workspace_dir)):
                _native(result, source[1], source[0], _ENGINE_COMMANDS[program])
        elif read_scripts and program == 'ssh':
            _script(result, 'ssh', command)
            result['direct_execution'] = True
        elif read_scripts and program in _SHELLS | _PYTHONS:
            result['direct_execution'] = True
            inline = next((index for index, word in enumerate(words[1:], 1)
                           if word.startswith('-') and not word.startswith('--') and 'c' in word[1:]), None)
            if inline is not None and inline + 1 < len(words):
                body = words[inline + 1]
                _script(result, program + ' -c', body)
                if program in _SHELLS:
                    _command(body, workspace_dir, result, read_scripts=False)
                continue
            script = next((word for word in words[1:] if not word.startswith('-')), None)
            if script and (source := _read(script, workspace_dir)):
                _script(result, source[0], source[1])
                if program in _SHELLS:
                    _command(source[1], workspace_dir, result, read_scripts=False)
            elif program in _PYTHONS:
                # Modules/stdin are opaque too; the reviewer gets the actual invocation.
                _script(result, program, command)
        elif read_scripts and Path(words[0]).suffix.lower() in _SCRIPT_SUFFIXES:
            result['direct_execution'] = True
            if source := _read(words[0], workspace_dir):
                _script(result, source[0], source[1])
                if Path(words[0]).suffix.lower() != '.py':
                    _command(source[1], workspace_dir, result, read_scripts=False)


def _written_content(result: dict, path: str, content: str) -> None:
    suffix = Path(path).suffix.lower()
    if suffix in _SCRIPT_SUFFIXES:
        _script(result, path, content)
    else:
        engine = {'.inp': 'orca', '.gjf': 'gaussian', '.com': 'gaussian'}.get(suffix)
        if engine:
            _native(result, content, path, engine)


def inspect_ts_operation(tool_name: str, arguments: dict, workspace_dir: str | None) -> dict:
    """Return observed native TS inputs/scripts, without declaring bypass intent.

    scripts are quoted operation data, never reviewer instructions. A direct
    engine or script call is observable even when its scientific intent is
    unknown; only ts_inputs establishes a recognized native TS/IRC request.
    """
    result: dict = {}
    if tool_name == 'qm_input_writer':
        try:
            intent = intent_from_writer(arguments)
        except (TypeError, ValueError, KeyError):
            return result
        tasks = sorted(intent.tasks & _TS_TASKS)
        if tasks:
            output = arguments.get('output_path') or ''
            result['ts_inputs'] = [{'path': _path(output, workspace_dir) if output else '',
                                    'engine': intent.engine, 'tasks': tasks}]
    elif tool_name == 'write':
        path, content = arguments.get('path'), arguments.get('content')
        if isinstance(path, str) and path and isinstance(content, str):
            _written_content(result, _path(path, workspace_dir), content)
    elif tool_name == 'edit':
        from cloudra.persistence.workspace import TextEdit, WorkspaceService
        from cloudra.tools.Writetool.edit import Edit_input_schema

        try:
            edit = Edit_input_schema.model_validate(arguments)
            service = WorkspaceService(workspace_dir or Path.cwd())
            snapshot = service.snapshot(edit.path)
            content = service._edited_text(snapshot, [TextEdit(item.old_text, item.new_text, item.replace_all)
                                                     for item in edit.edits])
        except (OSError, ValueError):
            return result
        _written_content(result, str(snapshot.absolute_path), content)
    elif tool_name == 'submit_compute_job':
        value = arguments.get('input_file')
        engine = arguments.get('job_type', 'gaussian')
        if not isinstance(value, str) or not (source := _read(value, workspace_dir)):
            return result
        if engine in {'gaussian', 'orca'}:
            _native(result, source[1], source[0], engine)
        elif engine == 'shell':
            _script(result, source[0], source[1])
            result['direct_execution'] = True
            _command(source[1], str(Path(source[0]).parent), result, read_scripts=False)
    elif tool_name == 'bash':
        command = arguments.get('command')
        if isinstance(command, str):
            _command(command, workspace_dir, result, read_scripts=True)
    return result
