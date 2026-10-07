"""Fail-closed read-only gate for schedule check commands.

A check command is a shell snippet the reminder broker polls until it exits 0.
The gate is the security boundary; the runner is ``bash -c``. Unknown commands,
writes, scripts, substitution, and interactive ssh are rejected. ``ssh`` / ``curl``
are allowed only as constrained read wrappers for remote-node status.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex

from cloudra.tools.core.bash_habit_guard import bash_file_write_warning, is_substantive_bash_command

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 5.0
CHECK_RUN_TIMEOUT_SECONDS = 30.0
MAX_CHECK_OUTPUT_CHARS = 4_000
MAX_WRAP_DEPTH = 4

CHECK_READ_CMDS = frozenset({
    "test", "[",
    "ls", "pwd", "cat", "head", "tail",
    "grep", "egrep", "fgrep",
    "find", "wc", "stat", "file",
    "ps", "pgrep",
    "squeue", "sacct", "qstat",
    "true", "false", "echo",
    "ssh", "curl",
})

_SPLITTERS = frozenset({"|", "||", "&&", "|&"})
_ALLOWED_REDIRECTS = frozenset({"2>/dev/null", "2>&1"})
_WRITE_REDIRECTS = frozenset({">>", ">", "&>", "&>>", "<>", ">&", ">>&"})
_FORBIDDEN_RAW = ("\n", "\r", "`", "$(", "${")

_SSH_FORBIDDEN_FLAGS = frozenset({"-L", "-R", "-D", "-W", "-N", "-f", "-s"})
_SSH_FLAGS_WITH_ARG = frozenset({
    "-b", "-c", "-E", "-e", "-F", "-I", "-i", "-J", "-l", "-m",
    "-O", "-o", "-p", "-Q", "-S", "-w",
})
_FIND_FORBIDDEN_FLAGS = frozenset({
    "-delete", "-exec", "-execdir", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls",
})
_CURL_FORBIDDEN_FLAGS = frozenset({
    "-o", "--output", "-O", "--remote-name", "--remote-name-all",
    "-T", "--upload-file",
    "-d", "--data", "--data-raw", "--data-ascii", "--data-binary", "--data-urlencode",
    "-F", "--form", "--form-string",
    "-J", "--remote-header-name",
    "-a", "--append", "--output-dir",
    "-K", "--config",
    "--url-query",
})
_CURL_FLAGS_WITH_ARG = frozenset({
    "-H", "--header", "-m", "--max-time", "--connect-timeout",
    "-e", "--referer", "-A", "--user-agent", "-u", "--user",
    "-x", "--proxy", "-w", "--write-out", "-Y", "--speed-limit",
    "-C", "--continue-at", "--retry", "--retry-delay",
    "-X", "--request",
})
_CURL_OK_METHODS = frozenset({"GET", "HEAD"})


class CheckCommandError(ValueError):
    """Raised when a schedule check command fails the read-only gate."""


def validate_interval(interval_seconds: float, timeout_seconds: float) -> None:
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise CheckCommandError(
            f"interval_seconds must be >= {MIN_INTERVAL_SECONDS:g} (got {interval_seconds:g})."
        )
    if timeout_seconds <= 0:
        raise CheckCommandError("timeout must be positive.")
    if interval_seconds > timeout_seconds:
        raise CheckCommandError("interval_seconds must be <= timeout.")


def validate_check_command(command: str) -> None:
    """Raise CheckCommandError unless ``command`` is a fail-closed read-only check."""
    _validate(command, depth=0)


def _validate(command: str, *, depth: int) -> None:
    if depth > MAX_WRAP_DEPTH:
        raise CheckCommandError("check command nesting is too deep.")
    text = (command or "").strip()
    if not text:
        raise CheckCommandError("check_command is empty.")
    for token in _FORBIDDEN_RAW:
        if token in text:
            raise CheckCommandError(f"check_command must not contain {token!r}.")
    if ";" in text:
        raise CheckCommandError("check_command must not contain ';'.")
    try:
        tokens = shlex.split(text, comments=False, posix=True)
    except ValueError as exc:
        raise CheckCommandError(f"check_command could not be parsed: {exc}") from exc
    if not tokens:
        raise CheckCommandError("check_command is empty.")
    try:
        substantive = bash_file_write_warning(text) or is_substantive_bash_command({"command": text})
    except ValueError as exc:
        raise CheckCommandError(f"check_command could not be parsed: {exc}") from exc
    if substantive:
        raise CheckCommandError("check_command must be read-only (no file writes or compute programs).")
    if "&" in tokens:
        raise CheckCommandError("check_command must not background jobs.")
    for seg in _segments(tokens):
        _validate_segment(seg, depth=depth)


def _segments(tokens: list[str]) -> list[list[str]]:
    segs: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in _SPLITTERS:
            if not current:
                raise CheckCommandError("check_command has an empty pipeline segment.")
            segs.append(current)
            current = []
        else:
            current.append(tok)
    if not current:
        raise CheckCommandError("check_command ends with a pipe or connector.")
    segs.append(current)
    return segs


def _validate_segment(raw: list[str], *, depth: int) -> None:
    seg = list(raw)
    while seg and seg[0] == "!":
        seg = seg[1:]
    if not seg:
        raise CheckCommandError("check_command has a bare '!'.")
    args = _strip_redirects(seg)
    primary = _primary_command(args)
    if primary is None:
        raise CheckCommandError("check_command segment has no command.")
    name = _cmd_base(primary)
    if name not in CHECK_READ_CMDS:
        raise CheckCommandError(f"command {name!r} is not allowed in a read-only check.")
    rest = _args_after_primary(args)
    if name == "ssh":
        _validate_ssh(rest, depth=depth)
    elif name == "curl":
        _validate_curl(rest)
    elif name == "find":
        _validate_find(rest)


def _strip_redirects(seg: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(seg):
        tok = seg[i]
        if tok in _ALLOWED_REDIRECTS:
            i += 1
            continue
        operator = tok.lstrip("0123456789")
        if operator == "<":
            if i + 1 >= len(seg):
                raise CheckCommandError("read redirect is missing a file.")
            i += 2
            continue
        if tok in {"2>", "2>>"} and i + 1 < len(seg) and seg[i + 1] == "/dev/null":
            i += 2
            continue
        if operator in _WRITE_REDIRECTS:
            raise CheckCommandError(
                "check_command must not redirect output to a file. "
                "Use a plain read-only check instead, e.g. grep -q 'Normal termination' job.log."
            )
        if ">" in tok and tok not in _ALLOWED_REDIRECTS:
            raise CheckCommandError(
                "check_command must not redirect output to a file. "
                "Use a plain read-only check instead, e.g. grep -q 'Normal termination' job.log."
            )
        if "$" in tok:
            raise CheckCommandError("check_command must not expand variables or substitutions; bake values in at create.")
        out.append(tok)
        i += 1
    return out


def _primary_command(args: list[str]) -> str | None:
    for tok in args:
        if "=" in tok and not tok.startswith("="):
            name, _, _ = tok.partition("=")
            if name.isidentifier():
                continue
        return tok
    return None


def _args_after_primary(args: list[str]) -> list[str]:
    primary = _primary_command(args)
    if primary is None:
        return []
    idx = args.index(primary)
    return args[idx + 1 :]


def _cmd_base(token: str) -> str:
    name = token.replace("\\", "/").split("/")[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def _validate_ssh(args: list[str], *, depth: int) -> None:
    i = 0
    remote: list[str] | None = None
    while i < len(args):
        tok = args[i]
        if tok == "--":
            remote = args[i + 1 :]
            break
        if tok.startswith("-") and tok != "-":
            flag = _ssh_flag(tok)
            if flag in _SSH_FORBIDDEN_FLAGS or any(
                tok == forbidden or tok.startswith(forbidden) and len(tok) > 2
                for forbidden in _SSH_FORBIDDEN_FLAGS
            ):
                raise CheckCommandError(f"ssh flag {tok!r} is not allowed on a read-only check.")
            if flag in _SSH_FLAGS_WITH_ARG:
                if len(tok) > 2 and not tok.startswith("--"):
                    i += 1
                    continue
                if i + 1 >= len(args):
                    raise CheckCommandError(f"ssh flag {tok!r} is missing its argument.")
                i += 2
                continue
            i += 1
            continue
        remote = args[i + 1 :]
        break
    if remote is None:
        raise CheckCommandError("ssh check must include a destination host.")
    if not remote:
        raise CheckCommandError("ssh check must include a remote command (interactive login is not allowed).")
    _validate(" ".join(remote), depth=depth + 1)


def _ssh_flag(tok: str) -> str:
    if tok.startswith("--"):
        return tok.split("=", 1)[0]
    if tok.startswith("-") and len(tok) >= 2:
        return tok[:2]
    return tok


def _validate_curl(args: list[str]) -> None:
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in _CURL_FORBIDDEN_FLAGS or _curl_forbidden_attached(tok):
            raise CheckCommandError(f"curl flag {tok!r} is not allowed on a read-only check.")
        if tok in {"-X", "--request"}:
            if i + 1 >= len(args):
                raise CheckCommandError("curl -X is missing a method.")
            method = args[i + 1].upper()
            if method not in _CURL_OK_METHODS:
                raise CheckCommandError("curl check may only use GET or HEAD.")
            i += 2
            continue
        if tok.startswith("-X") and tok != "-X" and not tok.startswith("--"):
            if tok[2:].upper() not in _CURL_OK_METHODS:
                raise CheckCommandError("curl check may only use GET or HEAD.")
            i += 1
            continue
        if tok in _CURL_FLAGS_WITH_ARG:
            if i + 1 >= len(args):
                raise CheckCommandError(f"curl flag {tok!r} is missing its argument.")
            i += 2
            continue
        if tok.startswith("--") and "=" in tok:
            flag, _, _ = tok.partition("=")
            if flag in _CURL_FORBIDDEN_FLAGS:
                raise CheckCommandError(f"curl flag {flag!r} is not allowed on a read-only check.")
            i += 1
            continue
        i += 1


def _curl_forbidden_attached(tok: str) -> bool:
    if tok.startswith("--"):
        flag = tok.split("=", 1)[0]
        return flag in _CURL_FORBIDDEN_FLAGS
    if not tok.startswith("-") or tok.startswith("--"):
        return False
    # Attached short form: -ooutfile (but not -s / -I / -f / …).
    if tok.startswith("-o") or tok.startswith("-O") or tok.startswith("-T") or tok.startswith("-d") or tok.startswith("-F"):
        return tok not in {"-s", "-S", "-f", "-I", "-i", "-k", "-L", "-g", "-G", "-v", "-n"}
    return False


def _validate_find(args: list[str]) -> None:
    for tok in args:
        if tok in _FIND_FORBIDDEN_FLAGS or tok.startswith("-exec") or tok.startswith("-ok"):
            raise CheckCommandError("find may not use -delete/-exec/-ok or print-to-file predicates.")


async def run_check_command(
    command: str,
    *,
    cwd: str | None,
    timeout: float = CHECK_RUN_TIMEOUT_SECONDS,
) -> tuple[int, str]:
    """Run a previously-validated check. Non-zero / timeout is 'not ready yet'."""
    env = os.environ.copy()
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd or None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        try:
            await process.wait()
        except Exception:
            pass
        return 124, "check command timed out"
    except Exception as exc:
        logger.exception("check command failed to run")
        return 1, f"check command failed: {exc}"
    code = process.returncode if process.returncode is not None else 1
    text = _decode(stdout)
    err = _decode(stderr)
    if err:
        text = f"{text}\n{err}" if text else err
    if len(text) > MAX_CHECK_OUTPUT_CHARS:
        text = text[:MAX_CHECK_OUTPUT_CHARS]
    return int(code), text


def _decode(data: bytes | None) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")
