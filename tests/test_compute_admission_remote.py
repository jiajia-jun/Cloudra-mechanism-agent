"""compute_admission 的 node_id 显式选节点与 SSH connection 变换。"""

import json

import pytest

from cloudra.services.compute_admission import admit_job


@pytest.fixture
def remote_registry(tmp_path, monkeypatch):
    """本地节点 + SSH Slurm 登录节点 + SSH 裸服务器，三段式注册表。"""
    local_ws = tmp_path / "local-ws"
    hpc_stage = tmp_path / "hpc-stage"
    bare_stage = tmp_path / "bare-stage"
    for path in (local_ws, hpc_stage, bare_stage):
        path.mkdir()
    registry_file = tmp_path / "nodes.json"
    registry_file.write_text(
        json.dumps(
            {
                "default_node_id": "workstation",
                "nodes": [
                    {
                        "node_id": "workstation",
                        "resources": {"max_concurrent": 2, "cpus": 16, "memory_mb": 32768},
                        "workspaces": [{"workspace_id": "main", "path": str(local_ws)}],
                    },
                    {
                        "node_id": "hpc-login",
                        "scheduler": {"type": "slurm", "partition": "compute"},
                        "connection": {
                            "type": "ssh",
                            "host": "login.hpc.example.edu",
                            "user": "cloudray",
                            "remote_root": "/scratch/cloudray",
                        },
                        "resources": {"max_concurrent": 8, "cpus": 64, "memory_mb": 262144},
                        "workspaces": [{"workspace_id": "staging", "path": str(hpc_stage)}],
                    },
                    {
                        "node_id": "workstation-b",
                        "scheduler": {"type": "local"},
                        "connection": {
                            "type": "ssh",
                            "host": "192.168.1.20",
                            "user": "cloudray",
                            "remote_root": "/home/cloudray/cloudra-jobs",
                        },
                        "resources": {"max_concurrent": 2, "cpus": 16, "memory_mb": 65536},
                        "workspaces": [{"workspace_id": "staging", "path": str(bare_stage)}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUDRA_NODE_REGISTRY_FILE", str(registry_file))
    # 远端环境探测是真实 ssh 子进程——准入测试一律打桩
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.check_remote_environment",
        lambda endpoint, job_type, **kwargs: (True, ""),
    )
    return tmp_path


def _write_input(directory, name="mol.xyz") -> str:
    path = directory / name
    path.write_text("2\n\nH 0 0 0\nH 0 0 1\n", encoding="utf-8")
    return str(path)


def test_admit_with_explicit_ssh_slurm_node(remote_registry):
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path, job_type="xtb", cpus=4, memory_mb=None, node_id="hpc-login"
    )
    assert outcome.ok
    assert outcome.node_id == "hpc-login"
    assert outcome.scheduler == "ssh_slurm"
    assert outcome.scheduler_options["type"] == "ssh_slurm"
    assert outcome.scheduler_options["partition"] == "compute"
    # connection 快照随账本行自包含
    assert outcome.scheduler_options["connection"]["host"] == "login.hpc.example.edu"
    # 账本与物理 Slurm 分配同一口径
    assert outcome.scheduler_options["cpus"] == 4


def test_admit_with_explicit_ssh_local_node(remote_registry):
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path,
        job_type="xtb",
        cpus=2,
        memory_mb=None,
        node_id="workstation-b",
    )
    assert outcome.ok
    assert outcome.scheduler == "ssh_local"
    # 裸远端无 Slurm 分配语义：不把 cpus/memory 写进 options
    assert "cpus" not in outcome.scheduler_options
    assert outcome.scheduler_options["connection"]["host"] == "192.168.1.20"


def test_admit_unknown_node_is_rejected(remote_registry):
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path, job_type="xtb", cpus=1, memory_mb=None, node_id="nope"
    )
    assert not outcome.ok
    assert "Unknown node" in outcome.message


def test_admit_conflicting_backend_and_node_is_rejected(remote_registry):
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path,
        job_type="xtb",
        cpus=1,
        memory_mb=None,
        execution_backend="local",
        node_id="hpc-login",
    )
    assert not outcome.ok
    assert "conflicts" in outcome.message


def test_admit_remote_probe_failure_is_fail_loud(remote_registry, monkeypatch):
    monkeypatch.setattr(
        "cloudra.infra.ssh_transport.check_remote_environment",
        lambda endpoint, job_type, **kwargs: (False, "Remote node is missing: orca"),
    )
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path, job_type="orca", cpus=1, memory_mb=None, node_id="hpc-login"
    )
    assert not outcome.ok
    assert "missing" in outcome.message


def test_admit_auto_routes_ssh_staging_workspace(remote_registry):
    """不配 node_id 时按工作区路由：staging 目录里的输入自动落到 SSH 节点。"""
    f_path = _write_input(remote_registry / "hpc-stage")
    outcome = admit_job(
        input_file=f_path, job_type="xtb", cpus=1, memory_mb=None, execution_backend="auto"
    )
    assert outcome.ok
    assert outcome.node_id == "hpc-login"
    assert outcome.scheduler == "ssh_slurm"


def test_admit_local_node_unaffected(remote_registry):
    import shutil

    if shutil.which("xtb") is None:
        pytest.skip("xtb binary not on PATH")
    f_path = _write_input(remote_registry / "local-ws")
    outcome = admit_job(
        input_file=f_path, job_type="xtb", cpus=1, memory_mb=None, execution_backend="auto"
    )
    assert outcome.ok
    assert outcome.node_id == "workstation"
    assert outcome.scheduler == "local"
    assert "connection" not in outcome.scheduler_options
