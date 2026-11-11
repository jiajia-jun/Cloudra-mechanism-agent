"""Task 1（P0）：沙箱文件路径一致性。

C1（batch_875bb46d76014ea7）确认缺陷：qm_input_writer 的相对输出落到进程
cwd、submit_compute_job 直接 exists(input_file) 读进程 cwd 的同名文件。本
文件用生产 LegacyToolExecutor 在项目内创建 agent（不经 os.chdir 改变生产
调用环境；测试进程 cwd 由 fixture 设置一次），验证相对路径统一解析到项目
工作区，并以注册表盘点其余工具的路径字段语义。

断言四个事实源中的磁盘与 DB：文件落在目标沙箱、server cwd 无同名产物、
引擎实际读到的输入 sha256 与沙箱一致、compute_jobs 归属正确。
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

from cloudra.persistence.workspace import resolve_tool_path
from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.services.nodes import default_resources
from tests.fixtures.benchmark_engines.engine import install_engine

_WATER_XYZ = (
    "3\nwater\n"
    "O  0.000000  0.000000  0.117300\n"
    "H  0.000000  0.757200 -0.469200\n"
    "H  0.000000 -0.757200 -0.469200\n"
)
_METHANE_XYZ = (
    "5\nmethane\n"
    "C  0.000000  0.000000  0.000000\n"
    "H  0.631000  0.631000  0.631000\n"
    "H -0.631000 -0.631000  0.631000\n"
    "H  0.631000 -0.631000 -0.631000\n"
    "H -0.631000  0.631000 -0.631000\n"
)


_RDKIT_AVAILABLE = importlib.util.find_spec("rdkit") is not None

# 计算资源由 agent 显式申请、节点按容量硬校验：CI runner 只 2 核，写死 cpus=4
# 会在 2 核 runner 上被合法拒收（同 tests/test_xtb_channel.py 的口径）。
_TEST_CPUS = max(1, min(2, os.cpu_count() or 1))
# submit 从输入推导内存；引擎替身无需 writer 默认 4GB（超过 CI 的 3968MB 额度）。
# 最多用 512MB，并留一半节点额度给并发测试中的另一条作业。
_TEST_MEMORY_MB = max(1, min(512, default_resources()["memory_mb"] // 2))
# qm_input_writer 在缺 RDKit 时整体拒工（工具首个前置检查），因此走 writer 的
# 用例需要 chem extra；盘点类/原语类用例不依赖 RDKit，始终运行。
_REQUIRES_RDKIT = pytest.mark.skipif(
    not _RDKIT_AVAILABLE,
    reason="qm_input_writer requires RDKit (install the chem extra: pip install -e .[chem])",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def server_cwd(tmp_path, monkeypatch):
    """固定测试进程 cwd 一次；期间不 os.chdir。"""
    cwd = tmp_path / "server-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


@pytest.fixture
def core():
    return RuntimeCore(strict_events=True)


async def _spawn(core: RuntimeCore, workspace: Path) -> tuple[Any, Any]:
    """在项目内创建 agent，返回 (project, agent)。"""
    bus = CommandBus(core)
    project = (
        await bus.execute(
            Command(
                type="project.create",
                payload={"name": f"benchmark:{workspace.name}", "workspace_dir": str(workspace)},
            )
        )
    ).data
    agent = (
        await bus.execute(
            Command(
                type="agent.spawn",
                target={"project_id": project.id},
                payload={"role_id": "coordinator"},
            )
        )
    ).data
    return project, agent


async def _execute(executor: LegacyToolExecutor, agent, name: str, arguments: dict) -> Any:
    result = await executor.execute(agent, ToolCall(id="c", name=name, arguments=arguments))
    assert result.error is None, result
    return result


@pytest.mark.asyncio
@_REQUIRES_RDKIT
async def test_writer_relative_output_uses_project_workspace(core, server_cwd, tmp_path):
    """已确认缺陷：绝对合法 XYZ + 相对输出。成功后文件必须在 workspace，
    且 server cwd 不存在同名文件（旧行为把 calc/input.gjf 写到进程 cwd）。"""
    workspace = tmp_path / "ws A"
    workspace.mkdir()
    (workspace / "water.xyz").write_text(_WATER_XYZ, encoding="utf-8")
    _, agent = await _spawn(core, workspace)
    executor = LegacyToolExecutor(core)

    result = await _execute(
        executor,
        agent,
        "qm_input_writer",
        {
            "source_type": "xyz_file",
            "source_value": str(workspace / "water.xyz"),
            "engine": "gaussian",
            "method": "HF", "basis_set": "STO-3G", "charge": 0,
            "output_path": "calc/input.gjf",
        },
    )

    assert result.is_success, result.summary
    written = workspace / "calc" / "input.gjf"
    assert written.is_file()
    assert result.data["input_path"] == str(written.resolve())
    assert not (server_cwd / "calc" / "input.gjf").exists()


@pytest.mark.asyncio
@_REQUIRES_RDKIT
async def test_writer_relative_source_reads_workspace_not_cwd(core, server_cwd, tmp_path):
    """相对源路径解析到沙箱；server cwd 预放内容不同的同名 xyz 不被读取。"""
    workspace = tmp_path / "ws B"
    workspace.mkdir()
    (workspace / "xyz" / "water.xyz").parent.mkdir(parents=True)
    (workspace / "xyz" / "water.xyz").write_text(_WATER_XYZ, encoding="utf-8")
    # 诱饵：进程 cwd 下同相对路径、不同物种
    decoy = server_cwd / "xyz" / "water.xyz"
    decoy.parent.mkdir(parents=True)
    decoy.write_text(_METHANE_XYZ, encoding="utf-8")
    _, agent = await _spawn(core, workspace)
    executor = LegacyToolExecutor(core)

    result = await _execute(
        executor,
        agent,
        "qm_input_writer",
        {
            "source_type": "xyz_file",
            "source_value": "xyz/water.xyz",
            "engine": "gaussian",
            "method": "HF", "basis_set": "STO-3G", "charge": 0,
            "output_path": "calc/input.gjf",
        },
    )

    assert result.is_success, result.summary
    content = (workspace / "calc" / "input.gjf").read_text(encoding="utf-8")
    # 坐标来自沙箱水分子；诱饵甲烷坐标（0.63100000）绝不出现
    assert "O " in content
    assert "0.63100000" not in content


@pytest.mark.parametrize(
    "workspace",
    [
        pytest.param("ws plain", id="plain"),
        pytest.param("Application Support/中文 C1", id="spaces_and_cjk"),
    ],
)
@pytest.mark.asyncio
@_REQUIRES_RDKIT
async def test_writer_relative_output_parametrized_dirs(core, server_cwd, tmp_path, workspace):
    """含空格与中文的目录同样走 workspace 语义。"""
    ws = tmp_path / workspace
    ws.mkdir(parents=True)
    (ws / "water.xyz").write_text(_WATER_XYZ, encoding="utf-8")
    _, agent = await _spawn(core, ws)
    executor = LegacyToolExecutor(core)

    result = await _execute(
        executor,
        agent,
        "qm_input_writer",
        {
            "source_type": "xyz_file",
            "source_value": str(ws / "water.xyz"),
            "engine": "gaussian",
            "method": "HF", "basis_set": "STO-3G", "charge": 0,
            "output_path": "nested/calc/input.gjf",
        },
    )

    assert result.is_success, result.summary
    assert (ws / "nested" / "calc" / "input.gjf").is_file()
    assert result.data["input_path"] == str((ws / "nested" / "calc" / "input.gjf").resolve())
    assert not (server_cwd / "nested" / "calc" / "input.gjf").exists()


@pytest.mark.asyncio
@_REQUIRES_RDKIT
async def test_relative_source_and_submit_use_same_workspace(core, server_cwd, tmp_path, monkeypatch):
    """写入 → writer → submit（同步）→ query → parser 全用同一沙箱相对路径；
    server cwd 预放内容不同的同名输入，检查引擎实际读到的 sha256 防假成功。"""
    workspace = tmp_path / "ws chain"
    workspace.mkdir()
    (workspace / "xyz" / "water.xyz").parent.mkdir(parents=True)
    (workspace / "xyz" / "water.xyz").write_text(_WATER_XYZ, encoding="utf-8")
    decoy = server_cwd / "xyz" / "water.xyz"
    decoy.parent.mkdir(parents=True)
    decoy.write_text(_METHANE_XYZ, encoding="utf-8")

    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    _, agent = await _spawn(core, workspace)
    executor = LegacyToolExecutor(core)

    writer = await _execute(
        executor,
        agent,
        "qm_input_writer",
        {
            "source_type": "xyz_file",
            "source_value": "xyz/water.xyz",
            "engine": "gaussian", "nproc": _TEST_CPUS,
            "method": "HF", "basis_set": "STO-3G", "charge": 0,
            "mem": f"{_TEST_MEMORY_MB}MB",
            "output_path": "calc/input.gjf",
        },
    )
    assert writer.is_success, writer.summary

    submitted = await _execute(
        executor,
        agent,
        "submit_compute_job",
        {"input_file": "calc/input.gjf", "job_type": "gaussian", "is_async": False, "cpus": _TEST_CPUS},
    )
    assert submitted.is_success, submitted.summary
    assert submitted.data["state"] == "done"
    assert submitted.data["job_id"] > 0
    assert submitted.data["job_dir"] == str((workspace / "calc").resolve())

    # 引擎读到的确实是沙箱文件而非进程 cwd 诱饵
    runs = engine.runs()
    assert len(runs) == 1, runs
    assert runs[0]["input"] == str((workspace / "calc" / "input.gjf").resolve())
    assert runs[0]["input_sha256"] == _sha256(workspace / "calc" / "input.gjf")
    assert runs[0]["cwd"] == str((workspace / "calc").resolve())

    # 同一编号 query 得相同终态与日志路径
    queried = await _execute(
        executor,
        agent,
        "query_compute_job",
        {"job_id": submitted.data["job_id"]},
    )
    assert queried.is_success
    job = queried.data["jobs"][0]
    assert job["state"] == "done"
    assert job["path"] == str((workspace / "calc" / "input.gjf").resolve())
    frozen_log = Path(job["log_path"])
    assert frozen_log.is_relative_to(workspace / "calc" / ".cloudra")
    assert frozen_log.read_bytes() == (workspace / "calc" / "input.log").read_bytes()

    # 相对 log 路径同样走沙箱
    parsed = await _execute(
        executor,
        agent,
        "log_parser",
        {"log_path": str(frozen_log.relative_to(workspace))},
    )
    assert parsed.is_success, parsed.summary
    assert parsed.data["engine"] == "gaussian"
    assert parsed.data["scf_energy_hartree"] is not None


@pytest.mark.asyncio
@_REQUIRES_RDKIT
async def test_concurrent_projects_do_not_cross_write(core, server_cwd, tmp_path, monkeypatch):
    """C1/C2 并发生成 calc/input.gjf（不同固定源内容）：文件、引擎输入与
    compute_jobs 归属各自隔离，互不污染。"""
    ws1 = tmp_path / "ws C1"
    ws2 = tmp_path / "ws C2 中文"
    for ws, xyz in ((ws1, _WATER_XYZ), (ws2, _METHANE_XYZ)):
        ws.mkdir()
        (ws / "src.xyz").write_text(xyz, encoding="utf-8")

    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    project1, agent1 = await _spawn(core, ws1)
    project2, agent2 = await _spawn(core, ws2)
    executor = LegacyToolExecutor(core)
    # 两条同步作业须同时放进 2 核 CI 节点；每条只申请 1 核。
    job_cpus = 1

    async def write_and_submit(agent, workspace: Path):
        writer = await _execute(
            executor,
            agent,
            "qm_input_writer",
            {
                "source_type": "xyz_file",
                "source_value": str(workspace / "src.xyz"),
                "engine": "gaussian", "nproc": job_cpus,
                "method": "HF", "basis_set": "STO-3G", "charge": 0,
                "mem": f"{_TEST_MEMORY_MB}MB",
                "output_path": "calc/input.gjf",
            },
        )
        assert writer.is_success, writer.summary
        submitted = await _execute(
            executor,
            agent,
            "submit_compute_job",
            {"input_file": "calc/input.gjf", "job_type": "gaussian", "is_async": False, "cpus": job_cpus},
        )
        assert submitted.is_success, submitted.summary
        return submitted

    import asyncio

    sub1, sub2 = await asyncio.gather(
        write_and_submit(agent1, ws1),
        write_and_submit(agent2, ws2),
    )

    # 各自文件内容正确（水/甲烷互不混入）
    content1 = (ws1 / "calc" / "input.gjf").read_text(encoding="utf-8")
    content2 = (ws2 / "calc" / "input.gjf").read_text(encoding="utf-8")
    assert "O " in content1 and "0.63100000" not in content1
    assert "0.63100000" in content2 and "O " not in content2
    assert not (server_cwd / "calc" / "input.gjf").exists()

    # 引擎侧：两条运行记录各读各的沙箱输入（calculator cd 到输入目录）
    runs = {r["cwd"]: r for r in engine.runs()}
    assert set(runs) == {str((ws1 / "calc").resolve()), str((ws2 / "calc").resolve())}
    for ws, run in ((ws1, runs[str((ws1 / "calc").resolve())]), (ws2, runs[str((ws2 / "calc").resolve())])):
        assert run["input"] == str((ws / "calc" / "input.gjf").resolve())
        assert run["input_sha256"] == _sha256(ws / "calc" / "input.gjf")

    # DB 归属：两条作业路径分别落在各自沙箱，且归属各自项目
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import list_compute_jobs

    db = ComputeDB()
    rows = list_compute_jobs(db)
    assert len(rows) == 2
    assert all(r["req_cpus"] == job_cpus for r in rows)
    assert all(r["req_memory_mb"] == _TEST_MEMORY_MB for r in rows)
    by_path = {str(r["path"]): r for r in rows}
    assert str((ws1 / "calc" / "input.gjf").resolve()) in by_path
    assert str((ws2 / "calc" / "input.gjf").resolve()) in by_path
    by_conv = {r["conversation_id"]: r for r in rows}
    assert by_conv[project1.id]["path"] == str((ws1 / "calc" / "input.gjf").resolve())
    assert by_conv[project2.id]["path"] == str((ws2 / "calc" / "input.gjf").resolve())
    assert sub1.data["job_id"] != sub2.data["job_id"]


# ---------------------------------------------------------------------------
# 工具路径字段盘点：注册表 + 输入 schema 是唯一事实来源
# ---------------------------------------------------------------------------
#
# kind 语义：
#   workspace_input  相对路径解析到 agent 工作目录（读）
#   workspace_output 相对路径解析到 agent 工作目录（写）
#   workspace_dir    相对路径解析到 agent 工作目录（目录）
#   workspace_relative_only 只接受相对路径（WorkspaceService 契约）
#   conditional_path 仅文件来源模式是路径（SMILES 是分子串，绝不是路径）
#   cwd_input/cwd_output/cwd_dir/cwd_input_map  现状记录：相对路径仍按进程
#                   cwd（本次不扩展契约，属已记录的待验证风险）

TOOL_PATH_FIELDS: dict[str, dict[str, str]] = {
    "qm_input_writer": {
        "source_value": "conditional_path",
        "output_path": "workspace_output",
        "artifact_dir": "workspace_output",
        "chk_name": "workspace_output",
        "rwf_name": "workspace_output",
        "fchk_name": "workspace_output",
    },
    "submit_compute_job": {"input_file": "workspace_input"},
    "format_converter": {"input_path": "workspace_input", "output_path": "workspace_output"},
    "pdb_inspect": {"input_path": "workspace_input"},
    "pdb_clean": {"input_path": "workspace_input", "output_path": "workspace_output"},
    "md_box": {"components.structure_path": "workspace_input", "output_dir": "workspace_dir"},
    "md_energy": {"energy_path": "workspace_input", "output_path": "workspace_output"},
    "md_trajectory": {"trajectory_path": "workspace_input", "topology_path": "workspace_input"},
    **dict.fromkeys(("md_rmsd", "md_rmsf", "md_rdf", "md_msd"), {
        "trajectory_path": "workspace_input", "topology_path": "workspace_input",
        "index_path": "workspace_input", "output_path": "workspace_output",
    }),
    "smiles_to_mol": {"output_path": "workspace_output", "artifact_dir": "workspace_output"},
    "internal_coordinates": {
        "input_path": "workspace_input",
        "zmat_path": "workspace_output",
        "zmatrix_path": "workspace_input",
        "output_path": "workspace_output",
    },
    "conformer_search": {"input_path": "workspace_input", "output_dir": "workspace_dir"},
    "mechanism_predict": {"output_dir": "workspace_dir"},
    # TS workspace is bound by the caller, not exposed in the input schema.
    "log_parser": {"log_path": "workspace_input"},
    "ts_guess": {
        "reactant_path": "workspace_input",
        "product_path": "workspace_input",
        "output_dir": "workspace_dir",
        "input_path": "workspace_input",
        "output_path": "workspace_output",
        "log_path": "workspace_input",
        "ts_candidate_path": "workspace_output",
        "freq_log": "workspace_input",
        "irc_log": "workspace_input",
        "reactant_logs": "workspace_input",
        "product_logs": "workspace_input",
    },
    "read": {"path": "workspace_input"},
    "write": {"path": "workspace_relative_only"},
    "edit": {"path": "workspace_relative_only"},
    "dag_submit_species_evidence": {"opt_file": "workspace_input", "freq_file": "workspace_input"},
    "dag_submit_step_evidence": {
        "ts_file": "workspace_input",
        "irc_file": "workspace_input",
        "irc_forward_file": "workspace_input",
        "irc_reverse_file": "workspace_input",
    },
    # --- 现状记录（未扩展契约） ---
    "molecule_drawer": {"output_path": "cwd_output"},
    "name_to_structure": {"output_path": "cwd_output"},
    "image_to_smiles": {"image_path": "cwd_input"},
    # cdxml_path 的描述自称 workspace-relative 但实现按 cwd 读取——现状记录，
    # 与本次契约扩展范围（read/write/format_converter/log_parser/ts_guess）不符。
    "cdxml_to_graph": {"cdxml_path": "cwd_input"},
    "ir_processor": {"data_path": "cwd_input"},
    "nmr_processor": {"data_path": "cwd_input"},
    "electronic_analysis": {"input_path": "cwd_input", "output_dir": "cwd_dir"},
    "pymol_render": {"structure_path": "cwd_input", "output_path": "cwd_output"},
    "reaction_mapping": {"reactant_path": "cwd_input", "product_path": "cwd_input"},
    "thermo_analysis": {"species.log_path": "cwd_input"},
}


def test_path_field_inventory_matches_registry():
    """盘点测试：清单里每个字段都必须真实存在于注册表工具的输入 schema
    （改名/删除 fail-loud）；嵌套字段用 ``model.field`` 表示。"""
    from typing import get_args

    from cloudra.tools import get_tools_lst

    entries = {e.tool_name: e for e in get_tools_lst()}
    for tool_name, fields in TOOL_PATH_FIELDS.items():
        assert tool_name in entries, f"tool {tool_name!r} not in registry"
        schema = entries[tool_name].input_schema
        for field in fields:
            if "." in field:
                outer, inner = field.split(".", 1)
                annotation = schema.model_fields[outer].annotation
                args = get_args(annotation)
                nested = args[0] if args else annotation
                assert inner in nested.model_fields, f"{tool_name}.{field} missing"
            else:
                assert field in schema.model_fields, f"{tool_name}.{field} missing"


def test_registry_path_fields_are_documented():
    """反向盘点：Chemtool 输入 schema 中任何“路径样”顶层字段（名字含
    path/file/dir/log 且描述提到 path/file）都必须出现在清单里——新增路径
    字段未同步盘点即 fail-loud，防止清单腐化。"""
    from cloudra.tools import get_tools_lst

    # 显式 token 扫描（不用正则：路径字段启发式也只做确定性的子串判定）
    name_tokens = ("path", "file", "dir", "log")
    for entry in get_tools_lst():
        if not entry.cls.__module__.startswith("cloudra.tools.Chemtool"):
            continue
        schema = entry.input_schema
        documented = TOOL_PATH_FIELDS.get(entry.tool_name or entry.class_name.lower(), {})
        for name, info in schema.model_fields.items():
            description = (info.description or "").lower()
            if not any(token in name.lower() for token in name_tokens):
                continue
            if not ("path" in description or "file" in description):
                continue
            assert name in documented, (
                f"undocumented path field: {entry.tool_name}.{name} "
                "— add it to TOOL_PATH_FIELDS (kind per its semantics)"
            )


def test_resolve_tool_path_primitive_semantics(tmp_path):
    """原语自身语义：绝对原样、相对解析到 working_directory、空串原样、
    无桥时回退 cwd；SMILES 类非路径语义由调用方甄别。"""

    class _Tool:
        subagent = None

    class _Bridge:
        working_directory = str(tmp_path / "ws")

    tool = _Tool()
    assert resolve_tool_path(tool, "/abs/file.inp") == "/abs/file.inp"
    assert resolve_tool_path(tool, "calc/input.inp") == str((Path.cwd() / "calc/input.inp").resolve())
    assert resolve_tool_path(tool, "") == ""
    tool.subagent = _Bridge()
    assert resolve_tool_path(tool, "calc/input.inp") == str((tmp_path / "ws" / "calc/input.inp").resolve())
    assert resolve_tool_path(tool, "CCO") == str((tmp_path / "ws" / "CCO").resolve())  # 调用方不该对 SMILES 调用
