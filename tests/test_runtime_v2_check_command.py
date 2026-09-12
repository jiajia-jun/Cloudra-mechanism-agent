"""Fail-closed read-only gate for schedule check commands."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.check_command import (
    MIN_INTERVAL_SECONDS,
    CheckCommandError,
    validate_check_command,
    validate_interval,
)


def _ok(command: str) -> None:
    validate_check_command(command)


def _bad(command: str, *needles: str) -> None:
    with pytest.raises(CheckCommandError) as exc:
        validate_check_command(command)
    text = str(exc.value)
    for needle in needles:
        assert needle in text


class TestAllow:
    def test_file_exists(self):
        _ok("test -f /tmp/job.done")

    def test_bracket_test(self):
        _ok("[ -f /tmp/job.done ]")

    def test_grep_log(self):
        _ok("grep -q 'Normal termination' job.log")

    def test_pipe_and_connectors(self):
        _ok("test -f job.log && grep -q done job.log")
        _ok("tail job.log | grep -q 'Normal termination'")
        _ok("! test -f /proc/12345")

    def test_stderr_null_and_stdin_redirect(self):
        _ok("grep -q done job.log 2>/dev/null")
        _ok("grep -q done < job.log")

    def test_squeue(self):
        _ok("squeue -j 12345")
        _ok("sacct -j 12345 --format=State -n")

    def test_ps(self):
        _ok("ps -p 12345")

    def test_ssh_remote_test(self):
        _ok("ssh login.cluster 'test -f /job/done'")
        _ok("ssh -p 22 user@node test -f /job/done")
        _ok("ssh -o StrictHostKeyChecking=no login 'squeue -j 12345'")

    def test_curl_get(self):
        _ok("curl -sf https://node.example/status")
        _ok("curl -I https://node.example/status")
        _ok("curl -X GET https://node.example/status")
        _ok("curl -sf https://node.example/status | grep -q ok")


class TestReject:
    def test_empty(self):
        _bad("", "empty")

    def test_writes_and_scripts(self):
        _bad("rm -rf /tmp/x", "not allowed")
        _bad("python -c 'print(1)'", "not allowed")
        _bad("bash -c 'test -f x'", "not allowed")
        _bad("tee out.txt")
        _bad("echo hi > out.txt")

    def test_substitution_and_separators(self):
        _bad("test -f $(cat pidfile)", "$(")
        _bad("test -f `cat pidfile`", "`")
        _bad("test -f a; rm a", ";")
        _bad("test -f $HOME/x", "expand")

    def test_ssh_must_be_read_remote(self):
        _bad("ssh login.cluster", "remote command")
        _bad("ssh -N login.cluster 'test -f x'", "not allowed")
        _bad("ssh -L 8080:localhost:80 login 'test -f x'", "not allowed")
        _bad("ssh login 'rm /job/done'", "not allowed")
        _bad("scp file login:path", "not allowed")

    def test_curl_must_not_write_or_post(self):
        _bad("curl -o out.txt https://example", "-o")
        _bad("curl -O https://example/file", "-O")
        _bad("curl -X POST https://example", "GET or HEAD")
        _bad("curl -d a=b https://example", "-d")
        _bad("wget https://example", "not allowed")

    def test_find_must_not_mutate(self):
        _bad("find . -delete", "-delete")
        _bad("find . -exec rm {} ;", ";")  # semicolon already banned
        _bad("find . -exec rm {} +", "-exec")

    def test_redirect_error_shows_correct_usage(self):
        _bad(
            "tail job.log > copy.log",
            "must not redirect output to a file",
            "grep -q 'Normal termination' job.log",
        )

    def test_unclosed_quote(self):
        _bad("test -f 'oops", "parsed")


class TestInterval:
    def test_floor_and_timeout_cap(self):
        validate_interval(MIN_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS + 1)
        with pytest.raises(CheckCommandError):
            validate_interval(MIN_INTERVAL_SECONDS - 0.1, 60)
        with pytest.raises(CheckCommandError):
            validate_interval(30, 10)


@pytest.mark.asyncio
async def test_run_check_command_exit_codes():
    from cloudra.runtime_v2.check_command import run_check_command

    code, _ = await run_check_command("true", cwd=None, timeout=2)
    assert code == 0
    code, _ = await run_check_command("false", cwd=None, timeout=2)
    assert code != 0
