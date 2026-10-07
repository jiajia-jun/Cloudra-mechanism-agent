"""
Command Analyzer for BashTools.

Uses quote-aware POSIX tokens for executable segments and redirections.
"""

from dataclasses import dataclass, field

from .permission_model import Permission

_REDIRECTS = frozenset({">", ">>", "<", "<<", "<<-", "<<<", "<>", ">&", "<&", ">|", "&>", "&>>"})
_OPERATORS = ("&>>", "<<-", "<<<", "&&", "||", "|&", ">>", "<<", ">&", "<&", "<>", ">|", "&>",
              ";", "&", "|", "<", ">", "(", ")")
_SEPARATORS = frozenset({";", "&", "|", "|&", "&&", "||", "(", ")"})


@dataclass(frozen=True)
class _ShellToken:
    value: str
    raw: str
    start: int
    end: int
    operator: bool = False


@dataclass
class ShellCommand:
    """One executable segment and its shell redirections."""

    words: list[str] = field(default_factory=list)
    redirects: list[tuple[str, str]] = field(default_factory=list)


def _is_assignment(raw: str) -> bool:
    name, separator, _ = raw.partition("=")
    return bool(separator and name and (name[0].isascii() and (name[0].isalpha() or name[0] == "_"))
                and all(char.isascii() and (char.isalnum() or char == "_") for char in name))


def _substitution_end(command: str, start: int) -> int:
    """Locate a balanced command substitution without treating its text as outer shell tokens."""
    backtick = command[start] == "`"
    index = start + (1 if backtick else 2)
    depth = 1
    quote = ""
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote:
            if char == quote:
                quote = ""
        elif backtick and char == "`":
            return index + 1
        elif char in ("'", '"'):
            quote = char
        elif not backtick:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index + 1
        index += 1
    raise ValueError("Invalid shell command: unclosed command substitution")


def _shell_tokens(command: str) -> tuple[list[_ShellToken], bool]:
    """Lex POSIX words/operators, preserving quote boundaries and heredoc data."""
    tokens: list[_ShellToken] = []
    pending_heredocs: list[tuple[str, bool]] = []
    expect_heredoc: str | None = None
    has_substitution = False
    index = 0
    while index < len(command):
        char = command[index]
        if char in " \t":
            index += 1
            continue
        if char == "\n":
            tokens.append(_ShellToken(";", "\n", index, index + 1, True))
            index += 1
            for delimiter, strip_tabs in pending_heredocs:
                while index < len(command):
                    end = command.find("\n", index)
                    if end < 0:
                        end = len(command)
                    line = command[index:end]
                    index = end + (end < len(command))
                    if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                        break
                else:
                    raise ValueError("Invalid shell command: unclosed heredoc")
            pending_heredocs.clear()
            continue
        if char == "#":
            end = command.find("\n", index)
            index = len(command) if end < 0 else end
            continue
        operator = next((item for item in _OPERATORS if command.startswith(item, index)), None)
        if operator:
            tokens.append(_ShellToken(operator, operator, index, index + len(operator), True))
            index += len(operator)
            if operator in {"<<", "<<-"}:
                expect_heredoc = operator
            continue
        start = index
        quote = ""
        value: list[str] = []
        while index < len(command):
            char = command[index]
            if not quote and (char in " \t\n" or any(command.startswith(item, index) for item in _OPERATORS)):
                break
            if char == "\\" and quote != "'":
                if index + 1 == len(command):
                    raise ValueError("Invalid shell command: trailing escape")
                escaped = command[index + 1]
                if escaped != "\n":
                    if quote == '"' and escaped not in '$`"\\':
                        value.append("\\")
                    value.append(escaped)
                index += 2
                continue
            if char in ("'", '"') and (not quote or char == quote):
                quote = "" if quote else char
                index += 1
                continue
            if quote != "'" and (command.startswith("$(", index) or char == "`"):
                end = _substitution_end(command, index)
                value.append(command[index:end])
                has_substitution = True
                index = end
                continue
            value.append(char)
            index += 1
        if quote:
            raise ValueError("Invalid shell command: unclosed quote")
        token = _ShellToken("".join(value), command[start:index], start, index)
        tokens.append(token)
        if expect_heredoc is not None:
            pending_heredocs.append((token.value, expect_heredoc == "<<-"))
            expect_heredoc = None
    if pending_heredocs or expect_heredoc is not None:
        raise ValueError("Invalid shell command: unclosed heredoc")
    return tokens, has_substitution


def _executable_words(tokens: list[_ShellToken]) -> list[str]:
    """Remove shell assignments and the explicit env command wrapper."""
    index = 0
    while index < len(tokens) and _is_assignment(tokens[index].raw):
        index += 1
    tokens = tokens[index:]
    words = [token.value for token in tokens]
    while words and words[0].rsplit("/", 1)[-1] == "env":
        index = 1
        options_enabled = True
        while index < len(words):
            word = words[index]
            if word == "--" and options_enabled:
                index += 1
                options_enabled = False
                continue
            if options_enabled and word in {"-i", "--ignore-environment"}:
                index += 1
                continue
            if options_enabled and word in {"-u", "--unset", "-C", "--chdir"}:
                if index + 1 >= len(words):
                    raise ValueError("Invalid shell command: env option requires an argument")
                index += 2
                continue
            if options_enabled and word.startswith(("--unset=", "--chdir=")):
                index += 1
                continue
            if options_enabled and word.startswith("-"):
                raise ValueError(f"Invalid shell command: unsupported env option {word!r}")
            name, separator, _ = word.partition("=")
            if separator and name:
                index += 1
                continue
            break
        if index < len(words):
            words = words[index:]
        else:
            break
    return words


def _command_segments(tokens: list[_ShellToken]) -> list[ShellCommand]:
    segments: list[ShellCommand] = []
    words: list[_ShellToken] = []
    redirects: list[tuple[str, str]] = []
    last_operator = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.operator and token.value in _REDIRECTS:
            if words and words[-1].raw.isascii() and words[-1].raw.isdigit() and words[-1].end == token.start:
                words.pop()  # Attached file descriptor, e.g. the 2 in 2>err.log.
            if index + 1 == len(tokens) or tokens[index + 1].operator:
                raise ValueError("Invalid shell command: redirection requires a target")
            redirects.append((token.value, tokens[index + 1].value))
            last_operator = ""
            index += 2
            continue
        if token.operator and token.value in _SEPARATORS:
            if words or redirects:
                segments.append(ShellCommand(_executable_words(words), redirects))
            elif token.value in {"|", "|&", "&&", "||"}:
                raise ValueError("Invalid shell command: missing command before operator")
            words, redirects = [], []
            if token.raw != "\n":
                last_operator = token.value
        else:
            words.append(token)
            last_operator = ""
        index += 1
    if last_operator in {"|", "|&", "&&", "||", "("}:
        raise ValueError("Invalid shell command: missing command after operator")
    if words or redirects:
        segments.append(ShellCommand(_executable_words(words), redirects))
    return segments


@dataclass
class CommandAnalysis:
    """Analysis result for a shell command."""
    primary_cmd: str = ""
    pipe_commands: list[str] = field(default_factory=list)
    has_redirect: bool = False
    has_pipe: bool = False
    has_substitution: bool = False
    segments: list[ShellCommand] = field(default_factory=list)
    permissions: Permission = Permission.NONE

    def permission_dict(self) -> dict[str, bool]:
        """Return a dict matching the old interface."""
        return {
            'is_read': bool(self.permissions & Permission.READ),
            'is_write': bool(self.permissions & Permission.WRITE),
            'is_manage': bool(self.permissions & Permission.MANAGE),
            'is_script': bool(self.permissions & Permission.SCRIPT),
            'is_destructive': bool(self.permissions & Permission.DESTRUCTIVE),
        }


class BashCommandClassifier:
    """
    Classifies shell commands into permission categories using explicit tokens.
    """

    # Command name -> Permission mapping
    READ_CMDS = {
        'ls', 'pwd', 'cat', 'head', 'tail', 'grep', 'find', 'wc',
        'id', 'whoami', 'curl', 'top', 'ps', 'ifconfig', 'netstat',
        'lsof', 'ping', 'df', 'du', 'file', 'stat', 'which', 'whereis',
        'uname', 'free', 'uptime', 'date', 'echo', 'printenv', 'env',
        'git', 'hg', 'svn',
        'cd', 'nproc',
    }

    WRITE_CMDS = {
        'awk', 'sed', 'tee', 'truncate', 'touch', 'mkdir',
    }

    SCRIPT_CMDS = {
        'python', 'python3', 'python2', 'bash', 'sh', 'zsh', 'fish',
        'cargo', 'yarn', 'go', 'g16', 'g09', 'perl', 'ruby', 'node', 'nodejs',
        'npm', 'npx', 'conda', 'pip', 'pip3', 'xtb',
    }

    DESTRUCTIVE_CMDS = {
        'rm', 'mv', 'cp', 'rmdir', 'unlink',
        'docker', 'docker-compose', 'podman',
        'kubectl', 'kubectx', 'kubens',
        'ssh', 'scp', 'sftp', 'rsync',
        'wget', 'curl',
        'chmod', 'chown', 'chgrp',
        'mkfs', 'dd', 'fdisk', 'parted',
        'kill', 'pkill', 'killall',
        'shutdown', 'reboot', 'poweroff',
        'tar', 'zip', 'unzip', 'gzip', 'gunzip',
        'source', 'export',
        'pip', 'pip3', 'conda', 'npm', 'npx', 'yarn',
        'mkdir', 'touch', 'sed',
    }

    @classmethod
    def classify(cls, command: str) -> CommandAnalysis:
        """Classify explicit executable and operator tokens; malformed input raises ValueError."""
        analysis = CommandAnalysis()
        if command is None or command == "":
            return analysis
        if not isinstance(command, str):
            raise ValueError("Invalid shell command: expected a string")
        if not command.strip(" \t\n"):
            return analysis
        tokens, analysis.has_substitution = _shell_tokens(command)
        analysis.segments = _command_segments(tokens)
        analysis.has_redirect = any(segment.redirects for segment in analysis.segments)
        analysis.has_pipe = any(token.operator and token.value in {"|", "|&"} for token in tokens)
        analysis.pipe_commands = [segment.words[0].rsplit("/", 1)[-1]
                                  for segment in analysis.segments if segment.words]
        if analysis.pipe_commands:
            analysis.primary_cmd = analysis.pipe_commands[0]
        known = cls.READ_CMDS | cls.WRITE_CMDS | cls.SCRIPT_CMDS | cls.DESTRUCTIVE_CMDS
        for command_name in analysis.pipe_commands:
            lowered = command_name.lower()
            for pool, permission in (
                (cls.READ_CMDS, Permission.READ),
                (cls.WRITE_CMDS, Permission.WRITE),
                (cls.SCRIPT_CMDS, Permission.SCRIPT),
                (cls.DESTRUCTIVE_CMDS, Permission.DESTRUCTIVE),
            ):
                if lowered in pool:
                    analysis.permissions |= permission
            if lowered not in known:
                analysis.permissions |= Permission.SCRIPT
        if analysis.has_redirect:
            analysis.permissions |= Permission.WRITE | Permission.DESTRUCTIVE
        if analysis.has_substitution or any(
            token.operator and token.value in {";", "&", "&&", "||", "(", ")"} for token in tokens
        ):
            analysis.permissions |= Permission.SCRIPT | Permission.DESTRUCTIVE
        return analysis
