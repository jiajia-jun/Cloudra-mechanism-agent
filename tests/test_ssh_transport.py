from types import SimpleNamespace

import pytest

from cloudra.infra.ssh_transport import (
    SshEndpoint,
    SshError,
    check_remote_bins,
    check_remote_environment,
    pull_dir,
    push_dir,
    push_files,
    run_remote,
    run_remote_checked,
    ssh_argv,
)


def _endpoint(**overrides) -> SshEndpoint:
    base = {
        "host": "login.hpc.example.edu",
        "user": "cloudray",
        "port": 22,
        "remote_root": "/scratch/cloudray",
        "identity_file": None,
    }
    base.update(overrides)
    return SshEndpoint(**base)


def test_endpoint_from_connection_validates_shape():
    endpoint = SshEndpoint.from_connection(
        {
            "type": "ssh",
            "host": "h",
            "user": "u",
            "port": "2222",
            "remote_root": "/d",
            "identity_file": "/k",
        }
    )
    assert endpoint.port == 2222
    assert endpoint.identity_file == "/k"
    assert endpoint.job_dir(42) == "/d/cloudra-42"

    with pytest.raises(SshError, match="not ssh"):
        SshEndpoint.from_connection({"type": "local"})
    with pytest.raises(SshError, match="incomplete"):
        SshEndpoint.from_connection({"type": "ssh", "host": "h"})
    with pytest.raises(SshError, match="incomplete"):
        SshEndpoint.from_connection(
            {"type": "ssh", "host": "h", "user": "", "remote_root": "/d"}
        )


def test_ssh_argv_is_pure_argv_batch_mode():
    argv = ssh_argv(_endpoint(identity_file="/home/me/.ssh/id_ed25519", port=2222))
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert argv[-1] == "cloudray@login.hpc.example.edu"
    assert "-i" in argv and "/home/me/.ssh/id_ed25519" in argv
    assert argv[argv.index("-p") + 1] == "2222"
    # 无 identity_file 时不携带 -i（走 ssh 默认密钥解析）
    assert "-i" not in ssh_argv(_endpoint())


def test_run_remote_uses_argv_and_raises_on_transport_failure(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("cloudra.infra.ssh_transport.subprocess.run", fake_run)
    rc, stdout, _ = run_remote(_endpoint(), "hostname")
    assert rc == 0 and stdout == "ok\n"
    assert calls[0][0] == "ssh" and calls[0][-1] == "hostname"
    assert isinstance(calls[0], list)

    def fake_timeout(command, **kwargs):
        import subprocess as real

        raise real.TimeoutExpired(command, 30)

    monkeypatch.setattr("cloudra.infra.ssh_transport.subprocess.run", fake_timeout)
    with pytest.raises(SshError, match="failed"):
        run_remote(_endpoint(), "hostname")


def test_run_remote_checked_raises_on_nonzero_rc(monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=3, stdout="", stderr="boom"
        ),
    )
    with pytest.raises(SshError, match="boom"):
        run_remote_checked(_endpoint(), "false")


def test_push_pull_rsync_argv(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("cloudra.infra.ssh_transport.subprocess.run", fake_run)
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    push_dir(_endpoint(), tmp_path, "/scratch/cloudray/cloudra-7",
             excludes=(".cloudra/", ".g16_scratch/"))
    push_files(_endpoint(), [tmp_path / "a.inp"], "/scratch/cloudray/cloudra-7")
    pull_dir(_endpoint(), "/scratch/cloudray/cloudra-7", tmp_path)

    rsync_calls = [c for c in calls if c[0] == "rsync"]
    assert len(rsync_calls) == 3
    # mkdir 先行（ssh 调用）且目标目录带引号防注入
    assert calls[0][0] == "ssh" and "mkdir -p" in calls[0][-1]
    push_argv = rsync_calls[0]
    assert "--exclude" in push_argv and ".cloudra/" in push_argv
    assert push_argv[-2].endswith("/")
    assert "cloudray@login.hpc.example.edu:'/scratch/cloudray/cloudra-7'/" in push_argv[-1] \
        or push_argv[-1].endswith(":/scratch/cloudray/cloudra-7/")
    assert rsync_calls[2][-2].startswith("cloudray@login.hpc.example.edu:")


def test_push_fails_loud_without_local_rsync(monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.shutil.which", lambda name: None
    )
    with pytest.raises(SshError, match="rsync"):
        push_files(_endpoint(), ["x"], "/d")


def test_check_remote_bins_parses_missing_markers(monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.run_remote",
        lambda endpoint, cmd, **kwargs: (0, "MISSING:orca\nMISSING:sacct\n", ""),
    )
    ok, missing = check_remote_bins(
        _endpoint(), ["orca", "sbatch", "sacct"], refresh=True
    )
    assert not ok
    assert missing == ["orca", "sacct"]


def test_check_remote_bins_caches_per_endpoint(monkeypatch):
    calls = []

    def fake_run(endpoint, cmd, **kwargs):
        calls.append(cmd)
        return (0, "", "")

    monkeypatch.setattr("cloudra.infra.ssh_transport.run_remote", fake_run)
    assert check_remote_bins(_endpoint(), ["orca"], refresh=True) == (True, [])
    assert check_remote_bins(_endpoint(), ["orca"]) == (True, [])
    assert len(calls) == 1  # 第二次命中缓存


def test_check_remote_environment_reports_unreachable(monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    def boom(endpoint, cmd, **kwargs):
        raise SshError("ssh to host failed: timeout")

    monkeypatch.setattr("cloudra.infra.ssh_transport.run_remote", boom)
    ok, message = check_remote_environment(_endpoint(), "orca", slurm=True)
    assert not ok and "unreachable" in message


def test_check_remote_environment_lists_missing(monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.shutil.which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.run_remote",
        lambda endpoint, cmd, **kwargs: (0, "MISSING:sbatch\n", ""),
    )
    ok, message = check_remote_environment(_endpoint(), "orca", slurm=True)
    assert not ok and "sbatch" in message
