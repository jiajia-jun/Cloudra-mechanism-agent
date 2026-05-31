"""
Command Analyzer for BashTools.

Replaces the fragile substring matching with proper shlex-based token parsing.
"""

import re
import shlex
from dataclasses import dataclass, field

from .permission_model import Permission


@dataclass
class CommandAnalysis:
    """Analysis result for a shell command."""
    primary_cmd: str = ""
    pipe_commands: list[str] = field(default_factory=list)
    has_redirect: bool = False
    has_pipe: bool = False
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
    Classifies shell commands into permission categories using shlex parsing.
    """

    # Command name -> Permission mapping
    READ_CMDS = {
        'ls', 'pwd', 'cat', 'head', 'tail', 'grep', 'find', 'wc',
        'id', 'whoami', 'curl', 'top', 'ps', 'ifconfig', 'netstat',
        'lsof', 'ping', 'df', 'du', 'file', 'stat', 'which', 'whereis',
        'uname', 'free', 'uptime', 'date', 'echo', 'printenv', 'env',
        'git', 'hg', 'svn',
        'cd', 'nproc',
        # Windows equivalents
        'dir', 'type', 'findstr', 'ver', 'systeminfo', 'hostname', 'ipconfig',
        'tasklist', 'sc', 'set', 'where', 'assoc', 'ftype', 'vol', 'label',
    }

    WRITE_CMDS = {
        'awk', 'sed', 'tee', 'truncate', 'touch', 'mkdir',
        # Windows equivalents
        'copy', 'xcopy', 'robocopy', 'move', 'ren', 'rename', 'md', 'rd', 'attrib', 'setx',
    }

    SCRIPT_CMDS = {
        'python', 'python3', 'python2', 'bash', 'sh', 'zsh', 'fish',
        'cargo', 'yarn', 'go', 'g16', 'g09', 'perl', 'ruby', 'node', 'nodejs',
        'npm', 'npx', 'conda', 'pip', 'pip3',
        # Windows equivalents
        'powershell', 'pwsh', 'cmd', 'cscript', 'wscript', 'batch',
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
        # Windows equivalents
        'del', 'erase', 'rd', 'rmdir', 'move', 'ren', 'rename', 'format', 'taskkill', 'net',
        'icacls', 'takeown', 'cipher',
    }

    # Shell metacharacters that indicate write/destructive behavior
    REDIRECT_PATTERNS = [
        re.compile(r'\d*[<>]'),        # >, >>, <, 2>, etc.
        re.compile(r'\d*>&'),          # >&
    ]

    @classmethod
    def classify(cls, command: str) -> CommandAnalysis:
        """
        Parse and classify a shell command.

        Handles pipes, redirects, variable assignments, and quoted strings.
        """
        import platform
        is_windows = platform.system() == 'Windows'
        
        analysis = CommandAnalysis()

        if not command or not command.strip():
            return analysis

        # 1. Tokenize with shlex
        try:
            # On Windows, posix=False is usually better for cmd.exe
            tokens = shlex.split(command, comments=False, posix=not is_windows)
        except ValueError:
            # Unclosed quotes or other shlex failures: fall back to string analysis
            return cls._fallback_classify(command)

        # 2. Detect redirects at token level
        for tok in tokens:
            for pattern in cls.REDIRECT_PATTERNS:
                if pattern.fullmatch(tok):
                    analysis.has_redirect = True
                    break
            # Pipes in Windows are also |
            if tok in ('|', '|&'):
                analysis.has_pipe = True

        # 3. Split by pipes to get individual command segments
        pipe_indices = [-1]
        for i, tok in enumerate(tokens):
            if tok == '|' or tok == '|&':
                pipe_indices.append(i)
        pipe_indices.append(len(tokens))

        commands = []
        for start, end in zip(pipe_indices[:-1], pipe_indices[1:]):
            segment = tokens[start + 1:end]
            if not segment:
                continue

            # Strip leading variable assignments (Unix style)
            cmd_idx = 0
            if not is_windows:
                for idx, tok in enumerate(segment):
                    if '=' in tok and not tok.startswith('=') and not tok.endswith('='):
                        parts = tok.split('=', 1)
                        if parts[0].isidentifier():
                            continue
                    cmd_idx = idx
                    break

            if cmd_idx >= len(segment):
                continue

            cmd_name = segment[cmd_idx]
            
            # Handle absolute paths: /usr/bin/python or C:\Python39\python.exe
            # Replace backslashes for uniform processing
            cmd_name_clean = cmd_name.replace('\\', '/')
            cmd_base = cmd_name_clean.split('/')[-1]
            
            # Remove .exe suffix if present
            if cmd_base.lower().endswith('.exe'):
                cmd_base = cmd_base[:-4]
                
            commands.append(cmd_base)

        if not commands:
            return analysis

        analysis.primary_cmd = commands[0]
        analysis.pipe_commands = commands

        # 4. Classify each command in the pipeline
        perms = Permission.NONE
        for cmd in commands:
            cmd_lower = cmd.lower()
            # Remove common version suffixes for matching
            cmd_core = cmd_lower.rstrip('0123456789.')

            if cmd_lower in cls.READ_CMDS or cmd_core in cls.READ_CMDS:
                perms |= Permission.READ
            if cmd_lower in cls.WRITE_CMDS or cmd_core in cls.WRITE_CMDS:
                perms |= Permission.WRITE
            if cmd_lower in cls.SCRIPT_CMDS or cmd_core in cls.SCRIPT_CMDS:
                perms |= Permission.SCRIPT
            if cmd_lower in cls.DESTRUCTIVE_CMDS or cmd_core in cls.DESTRUCTIVE_CMDS:
                perms |= Permission.DESTRUCTIVE

        # 5. Redirects imply write + destructive (can overwrite files)
        if analysis.has_redirect:
            perms |= Permission.WRITE | Permission.DESTRUCTIVE

        analysis.permissions = perms
        return analysis

    @classmethod
    def _fallback_classify(cls, command: str) -> CommandAnalysis:
        """
        Fallback when shlex fails (e.g. unclosed quotes).
        Uses regex-based word-boundary matching.
        """
        import platform
        is_windows = platform.system() == 'Windows'
        
        analysis = CommandAnalysis()

        # Detect redirects with regex
        if re.search(r'\d*[<>]', command):
            analysis.has_redirect = True

        # Extract the first "word" that looks like a command
        # Windows command regex needs to handle backslashes and drive letters
        if is_windows:
            # Matches C:\foo\bar.exe or just command
            first_word_match = re.search(r'^[\s]*([^\s|;&]+)', command)
        else:
            # Unix: handles variable assignments FOO=bar command
            first_word_match = re.search(r'^[\s]*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]*[\s]+)*([^\s|;&]+)', command)
            
        if first_word_match:
            cmd_full = first_word_match.group(1)
            # Clean up Windows paths
            cmd_clean = cmd_full.replace('\\', '/')
            cmd = cmd_clean.split('/')[-1].lower()
            
            # Remove .exe
            if cmd.endswith('.exe'):
                cmd = cmd[:-4]
                
            analysis.primary_cmd = cmd
            analysis.pipe_commands = [cmd]

            perms = Permission.NONE
            cmd_core = cmd.rstrip('0123456789.')

            for pool, perm in [
                (cls.READ_CMDS, Permission.READ),
                (cls.WRITE_CMDS, Permission.WRITE),
                (cls.SCRIPT_CMDS, Permission.SCRIPT),
                (cls.DESTRUCTIVE_CMDS, Permission.DESTRUCTIVE),
            ]:
                if cmd in pool or cmd_core in pool:
                    perms |= perm

            if analysis.has_redirect:
                perms |= Permission.WRITE | Permission.DESTRUCTIVE

            analysis.permissions = perms

        return analysis
