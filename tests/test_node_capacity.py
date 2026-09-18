"""多节点容量池：按节点生效容量、认领分池、控制面容量视图。

契约（容量池解耦）：
- 只有跑在本机的 local 节点受 OS 实时余量约束；远端/集群节点用注册声明。
- 在用量按节点分组：本地作业不占云端额度，反之亦然。
- 作业归属节点不在注册表里 → 调度器跳过不认领（绝不改投别的机器跑），
  容量视图把这条原因讲清楚。
"""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from cloudra.infra.config import _reset_for_tests
from cloudra.persistence.database import ComputeDB
from cloudra.services import host_capacity as hc
from cloudra.services.api_v2 import create_v2_app
from cloudra.services.compute_store import (
    claim_ready_compute_job_with_capacity,
    insert_compute_job,
)
from cloudra.services.node_capacity import node_capacities, node_capacity_views
from cloudra.services.nodes import NodeRegistry


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    hc._reset_probe_cache_for_tests()
    yield
    hc._reset_probe_cache_for_tests()


def _registry_file(tmp_path, *, os_probe):
    """两个节点的注册表：本机 local（受 OS 余量约束）+ 远端 slurm（用声明值）。"""
    local_ws = tmp_path / "local-ws"
    hpc_ws = tmp_path / "hpc-ws"
    local_ws.mkdir()
    hpc_ws.mkdir()
    path = tmp_path / "nodes.json"
    path.write_text(
        json.dumps(
            {
                "default_node_id": "workstation",
                "nodes": [
                    {
                        "node_id": "workstation",
                        "display_name": "Workstation",
                        "resources": {"max_concurrent": 2, "cpus": 16, "memory_mb": 32768},
                        "workspaces": [{"workspace_id": "main", "path": str(local_ws)}],
                    },
                    {
                        "node_id": "hpc-login",
                        "display_name": "HPC Login",
                        "scheduler": {
                            "type": "slurm",
                            "partition": "compute",
                            "cpus": 8,
                            "memory": "32G",
                        },
                        "resources": {"max_concurrent": 8, "cpus": 64, "memory_mb": 262144},
                        "workspaces": [{"workspace_id": "burst", "path": str(hpc_ws)}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path, local_ws, hpc_ws


def _use_registry(monkeypatch, path):
    monkeypatch.setenv("CLOUDRA_NODE_REGISTRY_FILE", str(path))


def _insert(db: ComputeDB, *, node_id: str | None, state: str = "ready") -> int:
    return insert_compute_job(
        db,
        conversation_id="prj-test",
        session_id=None,
        path="/tmp/input.gjf",
        state=state,
        jobtype="gaussian",
        node_id=node_id,
        scheduler="local",
    )


def _running(
    db: ComputeDB,
    *,
    node_id: str,
    req_cpus: int = 1,
    req_memory_mb: int | None = None,
    scheduler: str = "local",
) -> int:
    """在跑作业 + 有效租约（容量记账只认租约有效的 running 行）。"""
    job_id = insert_compute_job(
        db,
        conversation_id="prj",
        session_id=None,
        path=f"/tmp/run-{node_id}-{req_cpus}.gjf",
        state="running",
        jobtype="gaussian",
        node_id=node_id,
        scheduler=scheduler,
        req_cpus=req_cpus,
        req_memory_mb=req_memory_mb,
    )
    with db.connect() as con:
        con.execute(
            "UPDATE compute_jobs SET lease_expires_at=? WHERE id=?",
            (time.time() + 3600, job_id),
        )
        con.commit()
    return job_id


def test_capacities_split_local_and_remote(tmp_path, monkeypatch):
    """本地节点取 min(声明, OS 余量)；远端节点不受本机读数影响。"""
    path, _local_ws, _hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)

    capacities, default_node_id = node_capacities()

    assert default_node_id == "workstation"
    assert capacities == {
        "workstation": {"max_concurrent": 2, "cpus": 3, "memory_mb": 4096},
        "hpc-login": {"max_concurrent": 8, "cpus": 64, "memory_mb": 262144},
    }


def test_capacity_views_report_per_node_usage(tmp_path, monkeypatch):
    path, _local_ws, _hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)

    db = ComputeDB().init()
    # 云端一个 8 核作业在跑；本地一个未声明内存的作业在跑
    _running(db, node_id="hpc-login", req_cpus=8, req_memory_mb=8192, scheduler="slurm")
    _running(db, node_id="workstation", req_cpus=2)

    views, default_node_id = node_capacity_views(db)
    assert default_node_id == "workstation"
    by_id = {view["node_id"]: view for view in views}

    local = by_id["workstation"]
    assert local["capacity"]["effective"] == {"max_concurrent": 2, "cpus": 3, "memory_mb": 4096}
    # 未声明内存 → 公平份额 4096 // 2
    assert local["in_flight"] == {"slots": 1, "cpus": 2, "memory_mb": 2048}
    assert local["free"] == {"slots": 1, "cpus": 1, "memory_mb": 2048}

    remote = by_id["hpc-login"]
    assert remote["scheduler"] == "slurm"
    assert remote["capacity"]["effective"] == {"max_concurrent": 8, "cpus": 64, "memory_mb": 262144}
    assert remote["in_flight"] == {"slots": 1, "cpus": 8, "memory_mb": 8192}
    assert remote["free"]["cpus"] == 56


def test_claim_pools_are_independent_under_registry(tmp_path, monkeypatch):
    """本地额度被占满时，云端作业照常认领；本地作业不会被改投到云端。"""
    path, _local_ws, _hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)

    db = ComputeDB().init()
    # 本地：2 个槽位全占（声明 2 槽）
    _running(db, node_id="workstation", req_cpus=1, req_memory_mb=1024)
    _running(db, node_id="workstation", req_cpus=1, req_memory_mb=1024)
    local_job = _insert(db, node_id="workstation")
    cloud_job = _insert(db, node_id="hpc-login")

    capacities, default_node_id = node_capacities()
    claimed = claim_ready_compute_job_with_capacity(
        db, worker_id="w", capacities=capacities, default_node_id=default_node_id
    )
    assert claimed == cloud_job
    # 本地槽位仍满：本地作业继续排队，不会被改投
    assert claim_ready_compute_job_with_capacity(
        db, worker_id="w", capacities=capacities, default_node_id=default_node_id
    ) is None
    assert claim_ready_compute_job_with_capacity(
        db, worker_id="w", capacities=capacities, default_node_id=default_node_id
    ) is None
    with db.connect() as con:
        rows = dict(con.execute("SELECT id, state FROM compute_jobs").fetchall())
    assert rows[local_job] == "ready"


def test_legacy_rows_without_node_column_upgrade_to_default_node(tmp_path):
    """旧中央库补列：node_id 允许为空 → 视为默认节点归属（升级路径不丢作业）。"""
    from cloudra.persistence.database import _CREATE_COMPUTE_JOBS

    path = tmp_path / "compute.db"
    import sqlite3

    # 模拟旧库：建表语句里完全没有 node_id（含注释行）
    legacy_ddl = "\n".join(
        line for line in _CREATE_COMPUTE_JOBS.splitlines() if "node_id" not in line
    )
    con = sqlite3.connect(path)
    con.execute(legacy_ddl)
    con.execute(
        """INSERT INTO compute_jobs
        (conversation_id, session_id, path, state, jobtype, scheduler)
        VALUES ('prj','sess','/tmp/old.gjf','ready','gaussian','local')"""
    )
    con.commit()
    con.close()

    db = ComputeDB.from_path(str(path)).init()
    with db.connect() as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(compute_jobs)").fetchall()}
        assert "node_id" in columns
        assert con.execute("SELECT node_id FROM compute_jobs").fetchone()[0] is None

    # 二次 init 幂等（重复 ALTER 不炸）
    db.init()
    # 旧行归属默认节点：默认节点槽位满时它照样排队
    claimed = claim_ready_compute_job_with_capacity(
        db,
        worker_id="w",
        capacities={"node-local": {"max_concurrent": 1, "cpus": 4, "memory_mb": 4096}},
        default_node_id="node-local",
    )
    assert claimed == 1


def test_capacity_views_without_db_create_nothing(tmp_path, monkeypatch):
    """读路径不建库：从没提交过作业的机器上查容量视图，不落空 compute.db。"""
    path, _local_ws, _hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)

    db = ComputeDB()
    assert not os.path.exists(db.path)

    views, _default_node_id = node_capacity_views(db)

    assert {view["node_id"] for view in views} == {"workstation", "hpc-login"}
    assert all(view["in_flight"] == {"slots": 0, "cpus": 0, "memory_mb": 0} for view in views)
    assert not os.path.exists(db.path)


def test_nodes_endpoint_returns_capacity_views(tmp_path, monkeypatch):
    path, _local_ws, _hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)
    try:
        client = TestClient(create_v2_app())
        assert client.get("/api/v2/compute/nodes").status_code == 401

        resp = client.get(
            "/api/v2/compute/nodes",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        assert resp.status_code == 200
        nodes = resp.json()
        assert {node["node_id"] for node in nodes} == {"workstation", "hpc-login"}
        local = next(node for node in nodes if node["node_id"] == "workstation")
        assert local["capacity"]["effective"]["cpus"] == 3
        remote = next(node for node in nodes if node["node_id"] == "hpc-login")
        assert remote["scheduler"] == "slurm"
        assert remote["capacity"]["effective"]["cpus"] == 64
    finally:
        _reset_for_tests()


def test_job_rows_carry_node_id_from_admission(tmp_path, monkeypatch):
    """提交路径写入的 node_id 来自准入解析的归属节点（按工作区路由）。"""
    from cloudra.services.compute_admission import admit_job

    # 引擎可用性是本机探测：测试机未必装了 g16/sbatch，换成确定性放行
    monkeypatch.setattr(
        "cloudra.services.compute_admission.check_job_type", lambda *a, **k: (True, "")
    )
    monkeypatch.setattr("cloudra.infra.slurm.check_slurm_tools", lambda: (True, ""))

    path, local_ws, hpc_ws = _registry_file(tmp_path, os_probe=True)
    _use_registry(monkeypatch, path)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 4096)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 3)

    local_input = local_ws / "a.gjf"
    local_input.write_text("%nprocshared=2\n%mem=1GB\n#p hf/sto-3g\n\nH 0 0 0\n\n", encoding="utf-8")
    hpc_input = hpc_ws / "b.gjf"
    hpc_input.write_text("%nprocshared=2\n%mem=1GB\n#p hf/sto-3g\n\nH 0 0 0\n\n", encoding="utf-8")

    local = admit_job(
        input_file=str(local_input), job_type="gaussian", cpus=2, memory_mb=1024,
        execution_backend="auto",
    )
    assert local.ok is True, local.message
    assert local.node_id == "workstation"
    assert local.scheduler == "local"

    # 云端工作区路由到 slurm 节点（引擎可用性是本机 sbatch 检查，测试环境缺工具即拒收）
    remote = admit_job(
        input_file=str(hpc_input), job_type="gaussian", cpus=2, memory_mb=1024,
        execution_backend="auto",
    )
    assert remote.ok is True, remote.message
    assert remote.node_id == "hpc-login"
    assert remote.scheduler == "slurm"
    assert remote.node_resources == {"max_concurrent": 8, "cpus": 64, "memory_mb": 262144}


def test_registry_workspace_paths_are_required(tmp_path):
    """注册表里的 workspace 必须在本机存在（远端目录注册不进来）——远端节点走 slurm 路径。"""
    from cloudra.services.nodes import NodeRegistryError

    with pytest.raises(NodeRegistryError):
        NodeRegistry.from_dict(
            {
                "nodes": [
                    {
                        "node_id": "cloud",
                        "scheduler": {"type": "slurm"},
                        "workspaces": [
                            {"workspace_id": "remote", "path": "/definitely/not/here"}
                        ],
                    }
                ]
            }
        )
