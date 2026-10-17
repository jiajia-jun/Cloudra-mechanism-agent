"""Task 3（P0）：C1 生产协议完整回归（完整链路 FP 测试）。

只替换 LLM（benchmark_support.ScriptedLLM）与外部引擎
（tests/fixtures/benchmark_engines）；RuntimeCore / CommandBus / AgentRunner /
TurnPipeline / InvocationService / LegacyToolExecutor / 真实 Node/QuickJS /
SQLite / scheduler / guard / calculator 全部真实。Web 从
BenchmarkService.start 进入；CLI 从 BenchmarkRunner + RuntimeV2Backend 进入。

断言四个事实源交叉核对：磁盘（沙箱文件 + 引擎读到的 sha256）、DB（作业
归属/终态/通知标记）、事件（requested → finished 闭合、无重复提交）、
agent（子报告、父完成、挂起不算题目完成）。测试日志可沿 batch_id →
project_id → parent/child → tool_call_id → job_id → artifact 定位。
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import pytest

from cloudra.benchmark.backend import RuntimeV2Backend
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import AgentState, OrchestrationMode
from cloudra.services.nodes import default_resources
from tests.benchmark_support import (
    Receipt,
    ScriptedLLM,
    assemble_live_pipeline,
    calls,
    crash,
    js,
    text,
    wait_until,
)
from tests.fixtures.benchmark_engines.engine import install_engine

_HERE = Path(__file__).resolve().parent
_HOST_DIR = _HERE.parent / "cloudra" / "runtime_v2" / "js_host"


def _node_major() -> int | None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        return None
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(out.lstrip("v").split(".")[0]) if out.lstrip("v")[:1].isdigit() else None


_NODE_MAJOR = _node_major()
_HOST_AVAILABLE = (
    _NODE_MAJOR is not None
    and _NODE_MAJOR >= 22
    and (_HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file()
)
_RDKIT_AVAILABLE = importlib.util.find_spec("rdkit") is not None
_REQUIRES_HOST = pytest.mark.skipif(
    not _HOST_AVAILABLE,
    reason=(
        "optional JS host prerequisites missing: need node >= 22 "
        f"(found {_NODE_MAJOR}) and js_host/node_modules/quickjs-emscripten "
        "(install with: npm ci --prefix cloudra/runtime_v2/js_host)"
    ),
)
_REQUIRES_RDKIT = pytest.mark.skipif(
    not _RDKIT_AVAILABLE,
    reason="qm_input_writer requires RDKit (install the chem extra: pip install -e .[chem])",
)
_REQUIRES_HOST_AND_RDKIT = pytest.mark.skipif(
    not (_HOST_AVAILABLE and _RDKIT_AVAILABLE), reason="JS host and/or RDKit unavailable"
)

_BARRIER = "Done. The computed barrier is 5.0 kcal/mol."

# CLI 子 agent 完整链（smiles → writer → 同步 submit → query → parser）。
# 同步 submit 由真实 guard 阻塞到终态（确定性同步点：monitor 启动耗时不参与
# 竞速），parse 必然读到已完成的日志。
# 计算资源由 agent 显式申请、节点按容量硬校验：申请超过本机核数会被合法拒收
# （那是 submit 工具的正确行为，不是被测的链路行为）。CI runner 只有 2 核，
# 所以脚本申请 min(2, 本机核数)，与 tests/test_xtb_channel.py 的既有口径一致。
# 输入声明的内存也会由 submit 推导并记账；writer 默认 4GB 超过 CI 的 3968MB
# 额度。引擎替身只需少量内存，显式写入最多 512MB，并给并发用例留一半额度。
_TEST_CPUS = max(1, min(2, os.cpu_count() or 1))
_TEST_MEMORY_MB = max(1, min(512, default_resources()["memory_mb"] // 2))
_CPUS_TOKEN = "__CPUS__"
_MEMORY_TOKEN = "__MEMORY_MB__"


def _fit_resources(program: str) -> str:
    """把脚本里的资源占位换成这台机器能申请到的测试额度。"""
    return program.replace(_CPUS_TOKEN, str(_TEST_CPUS)).replace(
        _MEMORY_TOKEN, str(_TEST_MEMORY_MB)
    )

_CHILD_SYNC_CHAIN_PROGRAM = _fit_resources(r"""
const w = await tools.qm_input_writer({
  engine: "gaussian",
  source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{ "sp": null }],
  nproc: __CPUS__, mem: "__MEMORY_MB__MB",
  output_path: "calc/input.gjf",
});
if (!w.is_success) { text("WRITER FAIL: " + w.summary); }
else {
  const s = await tools.submit_compute_job({
    input_file: w.data.input_path, job_type: "gaussian", is_async: false, cpus: __CPUS__,
  });
  if (!s.is_success) { text("SUBMIT FAIL: " + s.summary); }
  else {
    const q = await tools.query_compute_job({ job_id: s.data.job_id });
    const p = await tools.log_parser({ log_path: "calc/input.log" });
    if (!p.is_success) { text("PARSE FAIL: " + p.summary); }
    else {
      text("PARSED job=" + s.data.job_id + " state=" + q.data.jobs[0].state +
           " engine=" + p.data.engine);
    }
  }
}
""")

# 父 agent（run2）：异步提交同一输入（真实 scheduler 认领 → guard → 引擎），
# 随后按真实门禁挂起等唤醒；终态由 watcher 的 compute.db 判定收口。
_PARENT_ASYNC_SUBMIT_PROGRAM = _fit_resources(r"""
const s = await tools.submit_compute_job({
  input_file: "calc/input.gjf", job_type: "gaussian", is_async: true, cpus: __CPUS__,
});
if (!s.is_success) { text("PARENT SUBMIT FAIL: " + s.summary); }
else { text("PARENT SUBMITTED job=" + s.data.job_id + " state=" + s.data.state); }
""")

# 引擎失败 → 修正后重提：第一次同步提交必须带回 failed 回执（含编号），
# 第二次同输入成功，两个编号不同、旧失败记录保留。
_CHILD_FAIL_THEN_RESUBMIT_PROGRAM = _fit_resources(r"""
const w = await tools.qm_input_writer({
  engine: "gaussian",
  source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{ "sp": null }],
  nproc: __CPUS__, mem: "__MEMORY_MB__MB",
  output_path: "calc/input.gjf",
});
if (!w.is_success) { text("WRITER FAIL: " + w.summary); }
else {
  const first = await tools.submit_compute_job({
    input_file: w.data.input_path, job_type: "gaussian", is_async: false, cpus: __CPUS__,
  });
  text("FIRST ok=" + first.is_success + " job=" + first.data.job_id +
       " state=" + first.data.state);
}
""")

_CHILD_RESUBMIT_CHAIN_PROGRAM = _fit_resources(r"""
const w = await tools.qm_input_writer({
  engine: "gaussian",
  source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{ "sp": null }],
  nproc: __CPUS__, mem: "__MEMORY_MB__MB",
  output_path: "calc/input.gjf",
});
if (!w.is_success) { text("WRITER FAIL: " + w.summary); }
else {
  const s = await tools.submit_compute_job({
    input_file: w.data.input_path, job_type: "gaussian", is_async: false, cpus: __CPUS__,
  });
  if (!s.is_success) { text("SECOND STILL FAILED: " + s.summary); }
  else {
    const q = await tools.query_compute_job({ job_id: s.data.job_id });
    const p = await tools.log_parser({ log_path: "calc/input.log" });
    text("SECOND ok=true job=" + s.data.job_id + " state=" + q.data.jobs[0].state +
         " engine=" + p.data.engine);
  }
}
""")

# 非法输入 → 可解释失败且无半成品；纠正后继续。
_CHILD_MALFORMED_THEN_CORRECTED_PROGRAM = r"""
const badText = "5\ntruncated\nC 0.0 0.0 0.0\n";
const badWrite = await tools.write({
  path: "xyz/bad.xyz", content: badText, expected_sha256: "missing",
});
const goodText = "3\nwater\nO 0.000000 0.000000 0.117300\n" +
                 "H 0.000000 0.757200 -0.469200\nH 0.000000 -0.757200 -0.469200\n";
const goodWrite = await tools.write({
  path: "xyz/water.xyz", content: goodText, expected_sha256: "missing",
});
const badSource = await tools.qm_input_writer({
  source_type: "xyz_file", source_value: "xyz/bad.xyz",
  method: "b3lyp", engine: "gaussian", output_path: "calc/bad_from_xyz.gjf",
});
const badOption = await tools.qm_input_writer({
  engine: "orca", source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "def2-svp",
  task_type: [{ "opt": "TS,calcfc,noeigen" }],
  output_path: "calc/bad_orca.inp",
});
text("WRITTEN bad=" + badWrite.is_success + " good=" + goodWrite.is_success +
     " | MALFORMED ok=" + badSource.is_success +
     " | BAD OPTION ok=" + badOption.is_success);
"""

_CHILD_CORRECTED_CHAIN_PROGRAM = _fit_resources(r"""
const w = await tools.qm_input_writer({
  engine: "gaussian",
  source_type: "xyz_file", source_value: "xyz/water.xyz",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{ "sp": null }],
  nproc: __CPUS__, mem: "__MEMORY_MB__MB",
  output_path: "calc/input.gjf",
});
if (!w.is_success) { text("WRITER FAIL: " + w.summary); }
else {
  const s = await tools.submit_compute_job({
    input_file: w.data.input_path, job_type: "gaussian", is_async: false, cpus: __CPUS__,
  });
  if (!s.is_success) { text("SUBMIT FAIL: " + s.summary); }
  else {
    const p = await tools.log_parser({ log_path: "calc/input.log" });
    text("CORRECTED job=" + s.data.job_id + " engine=" + p.data.engine);
  }
}
""")

# JS 业务失败 envelope：工具 is_success=false 时后续脚本不得当成成功。
_CHILD_BUSINESS_FAILURE_PROGRAM = r"""
const parsed = await tools.log_parser({ log_path: "missing.log" });
if (parsed.is_success) {
  text("UNEXPECTED SUCCESS " + parsed.summary);
} else {
  text("BUSINESS FAILURE HANDLED is_success=false");
}
"""

# Web 路径子 agent：提交后不轮询——ComputeNotifyBroker 回传唤醒后 query+parser。
_CHILD_PREP_PROGRAM = _fit_resources(r"""
const w = await tools.qm_input_writer({
  engine: "gaussian",
  source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{ "sp": null }],
  nproc: __CPUS__, mem: "__MEMORY_MB__MB",
  output_path: "calc/input.gjf",
});
if (!w.is_success) { text("WRITER FAIL: " + w.summary); }
else {
  const s = await tools.submit_compute_job({
    input_file: w.data.input_path, job_type: "gaussian", is_async: true, cpus: __CPUS__,
  });
  if (!s.is_success) { text("SUBMIT FAIL: " + s.summary); }
  else {
    const q = await tools.query_compute_job({ job_id: s.data.job_id });
    text("SUBMITTED job=" + s.data.job_id + " state=" + q.data.jobs[0].state);
  }
}
""")

_CHILD_QUERY_PARSE_PROGRAM = r"""
const q = await tools.query_compute_job({});
const jobs = q.data.jobs;
if (!jobs || jobs.length === 0) { text("NO JOBS: " + q.summary); }
else {
  const job = jobs[0];
  const p = await tools.log_parser({ log_path: job.log_path });
  if (!p.is_success) { text("PARSE FAIL: " + p.summary); }
  else { text("NOTIFIED job=" + job.job_id + " state=" + job.state + " engine=" + p.data.engine); }
}
"""

_SPAWN_PROGRAM = _fit_resources(r"""
const r = await tools.subagent_launcher({
  role_id: "small_mol",
  query: "Prepare a water single-point Gaussian input from SMILES O, submit it asynchronously with cpus=__CPUS__, wait for completion and parse the log.",
});
if (!r.is_success) { text("SPAWN FAIL: " + r.summary); }
else { text("SPAWNED session=" + r.data.session_id); }
""")


def _task_json(task_id: str, *, mode: OrchestrationMode = OrchestrationMode.STANDARD,
               method_allowed: tuple[str, ...] = ("b3lyp",)) -> str:
    from cloudra.benchmark.schema import GoldSpec, PromptSpec, SystemSpec, TaskSpec

    task = TaskSpec(
        task_id=task_id,
        tier="easy",
        prompt=PromptSpec(query="solve it", role="coordinator", orchestration_mode=mode),
        system=SystemSpec(reactants=["O"]),
        gold=GoldSpec(
            mechanism_graph={
                "nodes": [{"id": "R", "role": "reactant", "smiles": ["O"]}],
                "edges": [],
            }
        ),
        method_policy={"allowed_methods": list(method_allowed)},
    )
    return json.dumps(task.model_dump(mode="json"))


def _write_tasks(dir_path: Path, *ids: str, mode=OrchestrationMode.STANDARD,
                 method_allowed: tuple[str, ...] = ("b3lyp",)) -> str:
    dir_path.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        (dir_path / f"{tid}.json").write_text(
            _task_json(tid, mode=mode, method_allowed=method_allowed), encoding="utf-8"
        )
    return str(dir_path)


def _script_standard_roles(llm: ScriptedLLM) -> None:
    """CLI standard 场景脚本。

    子 agent 走同步 guard 链（writer→submit→query→parser，确定性）；父 agent
    run2 走异步 scheduler 链（真实认领 + guard），再按真实门禁挂起等 watcher。
    Web 场景子 agent 的脚本单独注入（broker 唤醒第二段）。
    """
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        # run2（子完成唤醒）：异步提交 + 按真实门禁挂起；回执在 run 内校验
        js(1, _PARENT_ASYNC_SUBMIT_PROGRAM),
        text(2, _BARRIER, expect=Receipt(
            tool="js_exec", contains=["PARENT SUBMITTED job="])),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_SYNC_CHAIN_PROGRAM),
        text(2, "chain complete, reporting", expect=Receipt(
            tool="js_exec", contains=["PARSED job="])),
    ])


def _compute_rows():
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import list_compute_jobs

    db = ComputeDB()
    try:
        ready = os.path.isfile(db.path) and os.path.getsize(db.path) > 0
    except OSError:
        ready = False
    return list_compute_jobs(db) if ready else []


def _release_engine_when_submitted(engine, seen: list[int], stop: threading.Event,
                                   timeout: float = 30.0) -> threading.Thread:
    """后台线程：等到 compute_jobs 行进入 running（调度已认领、guard 即将拉
    起）才释放引擎。

    用 DB 行状态而非墙钟做同步点：认领 → 释放 → 引擎完成 → monitor 落
    done，子 agent 的轮询循环必然收敛（确定性，不靠 sleep 竞速）。
    """

    def watch() -> None:
        deadline = time.time() + timeout
        while time.time() < deadline and not stop.is_set():
            rows = _compute_rows()
            for row in rows:
                if row["id"] not in seen and row["state"] == "running":
                    seen.append(row["id"])
                    engine.release()
                    return
            time.sleep(0.05)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


def _event_names(core, session_id: str) -> list[str]:
    return [e.type for e in core.event_log.query_session(session_id)]


def _tool_call_ids(core, session_id: str, tool_name: str) -> list[str]:
    ids = []
    for envelope in core.event_log.query_session(session_id):
        if envelope.type == "tool.requested" and envelope.data.get("tool_name") == tool_name:
            ids.append(str(envelope.data.get("tool_call_id") or ""))
    return ids


def _js_outputs(core, session_id: str) -> list[str]:
    """JS 程序 text() 输出：js_exec 的 tool.finished 摘要。"""
    out = []
    for envelope in core.event_log.query_session(session_id):
        if envelope.type == "tool.finished" and envelope.data.get("tool_name") == "js_exec":
            out.append(str((envelope.data or {}).get("summary") or ""))
    return out


def _dump_session(core, session_id: str, limit: int = 60) -> str:
    """失败取证：会话事件流摘要（type + 关键字段），供断言消息直接引用。"""
    lines = []
    for envelope in core.event_log.query_session(session_id)[-limit:]:
        data = envelope.data or {}
        lines.append(
            f"{envelope.type} run={envelope.run_id} tool={data.get('tool_name', '')} "
            f"to={data.get('to', '')} summary={str(data.get('summary') or data.get('content') or data.get('message') or '')[:160]}"
        )
    return "\n".join(lines)


def _program_outputs(core, agent) -> list[str]:
    """JS 程序的 text() 输出（program.output 事件；js_exec 本身不落 invocation
    事件，程序输出是客体内唯一可审计的输出通道）。"""
    return [
        str((e.data or {}).get("value"))
        for e in core.event_log.query_session(agent.id)
        if e.type == "program.output"
    ]


def _has_guest_rejection(core, agent) -> bool:
    """客体线缆不暴露该工具时，程序以 ToolCallError/TypeError 终止——这也算
    fail-closed（工具从未执行）。"""
    for envelope in core.event_log.query_session(agent.id):
        if envelope.type != "program.finished":
            continue
        text = str((envelope.data or {}).get("error") or "")
        if "not a function" in text or "unknown tool" in text.lower():
            return True
    return False


def _agent_summary(core, agent) -> str:
    """紧凑诊断：状态 + run 数 + 工具序列 + 错误（失败消息里够用不刷屏）。"""
    events = core.event_log.query_session(agent.id)
    tools = [e.data.get("tool_name") for e in events if e.type == "tool.requested"]
    errors = [
        f"{e.type}: {str((e.data or {}).get('error') or (e.data or {}).get('message') or '')[:160]}"
        for e in events
        if e.type in {"llm.failed", "tool.blocked"}
    ]
    runs = sum(1 for e in events if e.type == "run.started")
    return (
        f"--- {agent.role_id} {agent.state.value} runs={runs}\n"
        f"    tools={tools}\n    errors={errors}"
    )


def _assert_job_chain(core, *, engine, workspace: Path, project_id: str,
                      expect_rows: int = 1, expect_engine_runs: int = 1) -> list[dict]:
    """磁盘/DB/事件三源断言（job 链；可含多条作业）。"""
    # 磁盘：沙箱产物 + 引擎实际读到的输入 sha256 与沙箱一致
    gjf = workspace / "calc" / "input.gjf"
    log = workspace / "calc" / "input.log"
    if not (gjf.is_file() and log.is_file()):
        agent_dump = "\n".join(_agent_summary(core, a) for a in core.agents.values())
        raise AssertionError(
            f"compute chain produced no sandbox artifacts ({gjf}, {log}); "
            f"sandbox entries={sorted(p.name for p in workspace.rglob('*'))}\n{agent_dump}"
        )
    runs = engine.runs()
    assert len(runs) == expect_engine_runs, runs
    for run in runs:
        assert run["input"] == str(gjf.resolve())
        assert run["input_sha256"] == hashlib.sha256(gjf.read_bytes()).hexdigest()
        assert run["cwd"] == str((workspace / "calc").resolve())

    # DB：归属/终态/路径（每题的所有作业都落在本沙箱、归属本项目）
    rows = _compute_rows()
    assert len(rows) == expect_rows, rows
    for row in rows:
        assert row["state"] == "done"
        assert row["conversation_id"] == project_id
        assert row["path"] == str(gjf.resolve())
        assert row["req_cpus"] == _TEST_CPUS
        assert row["req_memory_mb"] == _TEST_MEMORY_MB

    # 事件：每条作业恰好一次 submit，requested/started/finished 一一闭合，
    # 无重复提交、无越权 job id
    submits = [e for e in core.event_log if e.type == "tool.requested"
               and e.data.get("tool_name") == "submit_compute_job"]
    finished = [e for e in core.event_log if e.type == "tool.finished"
                and e.data.get("tool_name") == "submit_compute_job"]
    assert len(submits) == expect_rows, submits
    assert len(finished) == expect_rows, finished
    assert {e.data["tool_call_id"] for e in submits} == {
        e.data["tool_call_id"] for e in finished
    }
    return rows


# ---------------------------------------------------------------------------
# CLI 入口：BenchmarkRunner + RuntimeV2Backend（默认 javascript 协议）
# ---------------------------------------------------------------------------

@_REQUIRES_HOST_AND_RDKIT
def test_cli_full_chain_standard_js(tmp_path, monkeypatch):
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    _script_standard_roles(llm)

    backend = RuntimeV2Backend(
        llm=llm,
        start_scheduler=True,
        poll_interval_s=0.05,
        stuck_grace_s=10.0,
    )

    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    from cloudra.benchmark.runner import load_tasks

    task = load_tasks(Path(tasks_dir))[0]
    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)

    result = runner.run_task(task)

    core = backend.core_by_task("T1")
    assert core is not None
    workspace = Path(result.sandbox).resolve()
    project_id = next(iter(core.projects))
    # 两条作业：子 agent 的同步 guard 链 + 父 agent 的异步 scheduler 链
    rows = _assert_job_chain(
        core, engine=engine, workspace=workspace, project_id=project_id,
        expect_rows=2, expect_engine_runs=2,
    )

    # agent：子收到可追踪回执并完成；父最终消息携带能垒；挂起不算完成
    agents = {a.role_id: a for a in core.agents.values()}
    child = agents["small_mol"]
    parent = agents["coordinator"]
    assert child.state is AgentState.SUCCEEDED, (
        f"child ended {child.state.value}:\n{_dump_session(core, child.id)}"
    )
    assert parent.state is AgentState.SUCCEEDED

    # 事件级证据：log_parser 真实执行（js_exec 自身不落 invocation 事件，
    # 其内部 guest 调用照常落 requested/finished）
    parse_finished = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "log_parser"
    ]
    assert parse_finished, f"child never parsed the log:\n{_dump_session(core, child.id)}"
    parse_summaries = [
        str(e.data.get("result_summary") or e.data.get("summary") or "").lower()
        for e in parse_finished
    ]
    assert any("gaussian" in summary for summary in parse_summaries), parse_summaries

    # 挂起不当作题目完成：父 run1 在子仍在跑时收尾（standard 模式的挂起是
    # watcher 级判定，dag 门禁未启用），子终态唤醒后父开新 run 才给最终答复
    parent_runs = [
        e for e in core.event_log.query_session(parent.id) if e.type == "run.started"
    ]
    assert len(parent_runs) >= 2, f"parent never reopened a run:\n{_dump_session(core, parent.id)}"
    parent_messages = [
        str((e.data or {}).get("content") or "")
        for e in core.event_log.query_session(parent.id)
        if e.type == "agent.message_emitted"
    ]
    # 最终消息只作审计留痕：它不参与任何评分（评分只读交付物）
    assert any("5.0 kcal/mol" in m for m in parent_messages), parent_messages

    # 评分落库（空沙箱无图 → 零证据倒扣，与既有契约一致）
    runs = runner.db.list_runs_for("")
    assert [r["task_id"] for r in runs] == ["T1"]
    assert runs[0]["final_score"] == -1.0
    assert any("mechanism_graph.json not found" in n for n in runs[0]["notes"]), runs[0]["notes"]

    # 追踪链可定位：project → parent/child → tool_call → job → 产物
    child_submits = set(_tool_call_ids(core, child.id, "submit_compute_job"))
    parent_submits = set(_tool_call_ids(core, parent.id, "submit_compute_job"))
    assert len(child_submits) == 1 and len(parent_submits) == 1
    by_session = {r["session_id"]: r for r in rows}
    assert by_session[child.id]["state"] == "done"      # 同步链作业
    assert by_session[parent.id]["state"] == "done"     # async 作业
    # 测试 scheduler 的 worker_id 追踪异步作业归属（同步作业不经认领）
    assert by_session[parent.id]["lease_owner"].startswith("scheduler:")
    assert by_session[child.id]["lease_owner"] in (None, "")


# ---------------------------------------------------------------------------
# Web 入口：BenchmarkService.start（live RuntimeCore + 测试 scheduler + broker）
# ---------------------------------------------------------------------------

@_REQUIRES_HOST_AND_RDKIT
@pytest.mark.asyncio
async def test_web_full_chain_standard_js(tmp_path, monkeypatch):
    from cloudra.benchmark.batch import BenchmarkService
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.scheduler.daemon import SchedulerDaemon

    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    engine.set_control("wait")  # 引擎等待释放：先验证"挂起 ≠ 题目完成"

    core = RuntimeCore(strict_events=True)
    llm = ScriptedLLM(core)
    assemble_live_pipeline(core, llm)
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children and compute finish"),
        text(1, _BARRIER),
        text(1, _BARRIER),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_PREP_PROGRAM),
        text(2, "submitted; waiting for completion notification"),
        js(1, _CHILD_QUERY_PARSE_PROGRAM),
        text(2, "evidence reported"),
    ])

    bus = CommandBus(core)
    scheduler = SchedulerDaemon(worker_id=f"scheduler:{os.getpid()}:webfp", poll_interval=0.05)
    await scheduler.start()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker.start()
    try:
        service = BenchmarkService(core, bus, data_dir=tmp_path / "bench")
        tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
        snap = await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1)
        batch = service._batch
        batch_id = snap["batch_id"]

        # 父进入 wait_background 挂起时，batch 仍未评分（注入延迟引擎验证）
        def parent_suspended() -> bool:
            st = batch.task_states[0]
            if not st.agent_id:
                return False
            parent = core.require_agent(st.agent_id)
            return parent.state is AgentState.SUCCEEDED
        await wait_until(parent_suspended, timeout=60.0, what="parent suspension")
        await asyncio.sleep(0.3)  # 给 watcher 一个轮询周期证明"仍未完成"
        assert service.status()["tasks"][0]["status"] == "running"

        engine.release()
        await wait_until(
            lambda: service.status()["status"] == "done",
            timeout=90.0,
            what="batch completion",
        )

        final = service.status()
        assert final["tasks"][0]["status"] == "scored"
        assert final["tasks"][0]["project_id"].startswith("prj")
        assert final["tasks"][0]["agent_id"]
        project_id = final["tasks"][0]["project_id"]
        sandbox = batch.sandboxes / "T1" / batch.batch_id

        _assert_job_chain(core, engine=engine, workspace=sandbox.resolve(), project_id=project_id)

        # 通知已投递并标记（broker 回传闭环）
        rows = _compute_rows()
        assert rows[0]["session_id"]
        assert rows[0]["notified_at"]  # notified 标记

        # 子 agent 的第二段（通知唤醒后的 query+parser）真实执行
        child = next(a for a in core.agents.values() if a.role_id == "small_mol")
        notify_parses = [
            e for e in core.event_log.query_session(child.id)
            if e.type == "tool.finished" and e.data.get("tool_name") == "log_parser"
        ]
        assert notify_parses, f"child never parsed after the notification:\n{_dump_session(core, child.id)}"
        assert any(
            "gaussian" in str(e.data.get("result_summary") or e.data.get("summary") or "").lower()
            for e in notify_parses
        )
        child_runs = [e for e in core.event_log.query_session(child.id) if e.type == "run.finished"]
        assert len(child_runs) >= 2  # 挂起一轮 + 通知唤醒一轮

        # benchmark.db：批次与运行行
        from cloudra.benchmark.runner import BenchmarkDB

        bdb = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
        runs = bdb.list_runs_for(batch_id)
        assert [r["task_id"] for r in runs] == ["T1"]
        assert runs[0]["final_score"] == -1.0

        # 追踪链：batch_id → project_id → parent/child → tool_call → job
        parent = core.require_agent(final["tasks"][0]["agent_id"])
        assert parent.role_id == "coordinator"
        assert _tool_call_ids(core, child.id, "log_parser")
        assert rows[0]["conversation_id"] == project_id
    finally:
        await broker.close()
        await scheduler.close()


# ---------------------------------------------------------------------------
# traditional 协议等价补充用例（CLI 入口，一条）
# ---------------------------------------------------------------------------

@_REQUIRES_RDKIT
def test_cli_full_chain_traditional_equivalent(tmp_path, monkeypatch):
    """traditional 协议等价补充用例：同一链路在传统线缆上跑通。

    协议由 ``AgentHost.effective_settings`` 冻结进 agent settings 快照
    （spawn 唯一解析点），因此从这里把 invocation_protocol 钉成 traditional
    ——与 JS 用例只差线缆形状，不换执行器、不换工具实现。
    """
    from cloudra.runtime_v2 import agent_host as agent_host_mod
    from cloudra.runtime_v2.schemas import InvocationProtocol

    original_effective_settings = agent_host_mod.AgentHost.effective_settings

    def _forced_traditional(self, project, role, override):
        settings = original_effective_settings(self, project, role, override)
        settings.invocation_protocol = InvocationProtocol.TRADITIONAL
        return settings

    monkeypatch.setattr(
        agent_host_mod.AgentHost, "effective_settings", _forced_traditional
    )
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()

    def job_id_of(core, agent):
        rows = _compute_rows()
        assert rows, "expected a compute row for the traditional child query"
        return {"job_id": rows[0]["id"]}

    llm.script("coordinator", [
        calls(1, [("subagent_launcher", {
            "role_id": "small_mol",
            "query": "traditional protocol equivalent chain",
        })]),
        text(2, "suspended"),
        text(1, _BARRIER),
        text(1, _BARRIER),
    ])
    llm.script("small_mol", [
        calls(1, [("qm_input_writer", {
            "source_type": "smiles", "source_value": "O",
            "engine": "gaussian",
            "method": "b3lyp", "basis_set": "6-31g(d)",
            "task_type": [{"sp": None}], "nproc": _TEST_CPUS,
            "mem": f"{_TEST_MEMORY_MB}MB",
            "output_path": "calc/input.gjf",
        })], run=1),
        calls(2, [("submit_compute_job", {
            "input_file": "calc/input.gjf", "job_type": "gaussian",
            "is_async": True, "cpus": _TEST_CPUS,
        })], run=1, expect=Receipt(tool="qm_input_writer", is_success=True)),
        calls(3, [("query_compute_job", job_id_of)], run=1, expect=Receipt(
            tool="submit_compute_job", is_success=True)),
        text(4, "Waiting for the compute notification.", run=1),
        text(1, "chain complete via traditional protocol", run=2),
    ])

    backend = RuntimeV2Backend(
        llm=llm, start_scheduler=True, poll_interval_s=0.05,
        stuck_grace_s=10.0,
    )

    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    from cloudra.benchmark.runner import load_tasks

    task = load_tasks(Path(tasks_dir))[0]
    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    result = runner.run_task(task)

    core = backend.core_by_task("T1")
    workspace = Path(result.sandbox).resolve()
    project_id = next(iter(core.projects))
    _assert_job_chain(core, engine=engine, workspace=workspace, project_id=project_id)
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    parent = next(a for a in core.agents.values() if a.role_id == "coordinator")
    assert child.state is AgentState.SUCCEEDED
    assert parent.state is AgentState.SUCCEEDED
    # 传统线缆下子 agent 的工具回执照常闭合：query 用真实作业号读取同编号状态
    child_tools = [
        e.data.get("tool_name")
        for e in core.event_log.query_session(child.id)
        if e.type == "tool.requested"
    ]
    assert child_tools.count("qm_input_writer") == 1
    assert child_tools.count("submit_compute_job") == 1
    assert child_tools.count("query_compute_job") == 1
    parent_messages = [
        str((e.data or {}).get("content") or "")
        for e in core.event_log.query_session(parent.id)
        if e.type == "agent.message_emitted"
    ]
    assert any("5.0 kcal/mol" in m for m in parent_messages), parent_messages
    assert parent.settings.invocation_protocol.value == "traditional"


# ---------------------------------------------------------------------------
# 引擎失败 → 修正后重提；非法输入 → 纠正；JS 业务失败 envelope
# ---------------------------------------------------------------------------

def _run_cli_task(tmp_path, monkeypatch, llm, *, task_id: str = "T1",
                  mode: OrchestrationMode = OrchestrationMode.STANDARD,
                  method_allowed: tuple[str, ...] = ("b3lyp",),
                  backend: RuntimeV2Backend | None = None):
    """CLI 入口跑一题（引擎由调用方先 install_engine 并设好控制文件）。"""
    backend = backend or RuntimeV2Backend(
        llm=llm, start_scheduler=True,
        poll_interval_s=0.05, stuck_grace_s=10.0,
    )
    tasks_dir = _write_tasks(
        tmp_path / "tasks", task_id, mode=mode, method_allowed=method_allowed
    )
    from cloudra.benchmark.runner import load_tasks

    task = load_tasks(Path(tasks_dir))[0]
    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    result = runner.run_task(task)
    core = backend.core_by_task(task_id)
    return runner, result, core


@_REQUIRES_HOST_AND_RDKIT
def test_cli_engine_failure_then_resubmit(tmp_path, monkeypatch):
    """固定第一次失败、第二次成功：两次编号不同、旧失败记录保留、
    失败回执带回 job_id/state（Task 2 修复在完整链路上的验证）。"""
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    engine.set_control("fail_once")

    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_FAIL_THEN_RESUBMIT_PROGRAM),
        js(2, _CHILD_RESUBMIT_CHAIN_PROGRAM, expect=Receipt(
            tool="js_exec", contains=["FIRST ok=false job=", "state=failed"])),
        text(3, "recovered after resubmission", expect=Receipt(
            tool="js_exec", contains=["SECOND ok=true job="])),
    ])
    runner, result, core = _run_cli_task(tmp_path, monkeypatch, llm)

    rows = _compute_rows()
    assert len(rows) == 2, rows
    by_id = {r["id"]: r for r in rows}
    assert len(by_id) == 2 and len({r["id"] for r in rows}) == 2  # 不同编号
    states = sorted(r["state"] for r in rows)
    assert states == ["done", "failed"], states
    failed = next(r for r in rows if r["state"] == "failed")
    done = next(r for r in rows if r["state"] == "done")
    assert failed["id"] != done["id"]
    assert failed["conversation_id"] == done["conversation_id"]
    assert failed["path"] == done["path"]            # 旧失败记录保留且指向同一输入
    assert failed["end_timestamp"] and done["end_timestamp"]

    # 引擎实际跑了两次（第一次失败、第二次成功）
    assert len(engine.runs()) == 2, engine.runs()

    # 事件：两次提交各自闭合，没有重复提交/编号串号
    submits = [e for e in core.event_log if e.type == "tool.requested"
               and e.data.get("tool_name") == "submit_compute_job"]
    assert len(submits) == 2
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    assert child.state is AgentState.SUCCEEDED, (
        f"child ended {child.state.value}:\n{_dump_session(core, child.id)}"
    )
    # 子 agent 拿到失败回执里的编号，与 DB 中的失败行一致
    assert failed["session_id"] == child.id


@_REQUIRES_HOST_AND_RDKIT
def test_cli_malformed_inputs_fail_then_corrected(tmp_path, monkeypatch):
    """非法输入（XYZ 首行原子数与内容不符 + ORCA 用 Gaussian 子选项）第一
    步可解释失败且无半成品；纠正后继续到最后一步。写文件走真实 write 工具与
    工作区路径语义（审批 LLM 是外部服务，用替身自动放行）。"""
    from cloudra.infra.yolo_guard import YoloGuard

    async def _approve(self, tool_name, tool_args, agent, session, **_kwargs):
        return True, ""

    monkeypatch.setattr(YoloGuard, "judge", _approve)
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_MALFORMED_THEN_CORRECTED_PROGRAM),
        js(2, _CHILD_CORRECTED_CHAIN_PROGRAM, expect=Receipt(
            tool="js_exec", contains=["MALFORMED ok=false", "BAD OPTION ok=false"])),
        text(3, "corrected and completed", expect=Receipt(
            tool="js_exec", contains=["CORRECTED job="])),
    ])
    runner, result, core = _run_cli_task(tmp_path, monkeypatch, llm)

    workspace = Path(result.sandbox).resolve()
    # 写文件的路径语义：相对路径落在沙箱（不是进程 cwd）
    assert (workspace / "xyz" / "bad.xyz").is_file()
    assert (workspace / "xyz" / "water.xyz").is_file()
    # 无半成品：两次非法调用都不产生输出文件
    assert not (workspace / "calc" / "bad_from_xyz.gjf").exists()
    assert not (workspace / "calc" / "bad_orca.inp").exists()
    # 纠正后的链路照常产出并跑完
    assert (workspace / "calc" / "input.gjf").is_file()
    rows = _compute_rows()
    assert len(rows) == 1 and rows[0]["state"] == "done"
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    writer_events = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "qm_input_writer"
    ]
    assert len(writer_events) == 3  # 两次失败 + 一次成功，逐次真实执行
    # 可解释：失败回执带拒绝原因（不是空消息）
    summaries = [str(e.data.get("result_summary") or "") for e in writer_events]
    # 畸形 XYZ 由输入校验确定性拦截（34293c1d 起报 "Invalid input ..."）；
    # "Failed to generate" 是仍存在的通用包装路径
    assert any(
        "Invalid input for qm_input_writer" in s or "Failed to generate" in s
        for s in summaries
    ), summaries
    assert any("calcfc" in s or "refused" in s.lower() for s in summaries), summaries


@_REQUIRES_HOST
def test_cli_js_business_failure_envelope(tmp_path, monkeypatch):
    """JS 业务失败 envelope：程序可以正常完成，但工具 is_success=false 时
    后续脚本不得当成成功——事件状态与程序输出一致，且不产生计算作业。"""
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_BUSINESS_FAILURE_PROGRAM),
        text(2, "handled the business failure", expect=Receipt(
            tool="js_exec", contains=["BUSINESS FAILURE HANDLED is_success=false"])),
    ])
    runner, result, core = _run_cli_task(tmp_path, monkeypatch, llm)

    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    assert child.state is AgentState.SUCCEEDED, (
        f"child ended {child.state.value}:\n{_dump_session(core, child.id)}"
    )
    parse_events = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "tool.finished" and e.data.get("tool_name") == "log_parser"
    ]
    assert len(parse_events) == 1
    summary = str(parse_events[0].data.get("result_summary") or "")
    assert '"is_success": false' in summary, summary       # 事件如实记失败
    # 后续步骤没有被当成成功继续：没有提交、没有作业行、引擎从未运行
    assert _tool_call_ids(core, child.id, "submit_compute_job") == []
    assert _compute_rows() == []
    assert engine.runs() == []


# ---------------------------------------------------------------------------
# dag_guided 主场景：草稿 → 真实 Supervisor 接受 → 子执行 → 显式送审 →
# 督导裁决 → 父按真实门禁结束（WAITING_APPROVAL/wait_review + 退出裁决）
# ---------------------------------------------------------------------------

_GUIDED_PROPOSE_PROGRAM = r"""
const proposal = await tools.dag_propose_mechanism({
  rationale: "test pathway: single elementary step R -> P",
  species: [{ name: "R", smiles: "O" }, { name: "P", smiles: "O" }],
  steps: [{ name: "step1", from: "R", to: "P" }],
});
text("PROPOSED ok=" + proposal.is_success + " " + proposal.summary);
"""

_GUIDED_SPAWN_PROGRAM = r"""
const r = await tools.subagent_launcher({
  role_id: "small_mol",
  query: "Run the input preparation and compute for step1, then explicitly submit the finished parse as frequency evidence for species R.",
});
if (!r.is_success) { text("SPAWN FAIL: " + r.summary); }
else { text("SPAWNED session=" + r.data.session_id); }
"""

# 子 agent：确定性 compute 链 + 显式送审（dag_bind_evidence 带 claim）。
def _guided_child_program(core, agent) -> str:
    """子 agent：确定性 compute 链 + 显式送审（目标用生产图里的真实 node_id）。

    节点 id 由 DAG 引擎生成，测试侧只读 store 取 id 生成脚本；送审本身走生产
    工具 dag_bind_evidence（带 claim = 显式送审来源）。
    """
    store = _dag_store(agent.project_id)
    snapshot = store.load_snapshot()
    node = next(
        (n for n in snapshot.delivery.nodes if getattr(n, "name", "") == "R"), None
    )
    assert node is not None, "species R missing from the delivery graph"
    return f'''
const w = await tools.qm_input_writer({{
  engine: "gaussian",
  source_type: "smiles", source_value: "O",
  method: "b3lyp", basis_set: "6-31g(d)",
  task_type: [{{ "freq": null }}],
  nproc: {_TEST_CPUS}, mem: "{_TEST_MEMORY_MB}MB",
  output_path: "calc/input.gjf",
}});
if (!w.is_success) {{ text("WRITER FAIL: " + w.summary); }}
else {{
  const s = await tools.submit_compute_job({{
    input_file: w.data.input_path, job_type: "gaussian", is_async: false,
    cpus: {_TEST_CPUS},
  }});
  if (!s.is_success) {{ text("SUBMIT FAIL: " + s.summary); }}
  else {{
    const p = await tools.log_parser({{ log_path: "calc/input.log" }});
    if (!p.is_success) {{ text("PARSE FAIL: " + p.summary); }}
    else {{
      const bound = await tools.dag_bind_evidence({{
        attachments: [{{
          tool_call_id: p.call_id,
          bind_target: "{node.node_id}",
          stage_kind: "geometry",
          claim: "R is the optimized water minimum (opt+freq job, only real frequencies)",
          rationale: "step1 compute chain",
        }}],
      }});
      text("SUBMITTED evidence ok=" + bound.is_success + " job=" + s.data.job_id +
           " " + bound.summary);
    }}
  }}
}}
'''


def _dag_store(project_id: str):
    """测试侧只读 DAG store（裁决仍由生产工具写入，测试不修改状态）。"""
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(project_id)
    db.ensure_schema()
    return DagStore(db)


def _supervisor_catchup_program(core, agent) -> str:
    """督导每轮动作：自读持久信箱，裁决当前仍待办的那一项。

    脚本按 run 固定配对执行（本函数即"本轮该做什么"），因此通知提前/扎堆到达
    时不会错位——线上一条待办处理完后，下一轮脚本再取新的待办。测试只读
    store 决定脚本参数；裁决本身走生产工具（dag_accept_mechanism /
    dag_review_call / dag_review_evidence）。
    """
    store = _dag_store(agent.project_id)
    draft = store.latest_draft()
    if draft is not None and draft.get("state") == "open":
        return (
            "const r = await tools.dag_accept_mechanism({"
            ' verdict: "accept", rationale: "test pathway is coherent", '
            f' draft_id: "{draft["draft_id"]}" }});\n'
            'text("ACCEPTED draft ok=" + r.is_success + " " + r.summary);'
        )
    pending = [r for r in store.list_call_reviews("pending") if r.source == "explicit"]
    if pending:
        review = pending[0]
        target = review.suggested_target_id or ""
        stage = review.suggested_stage or ""
        return (
            "const r = await tools.dag_review_call({"
            f' review_id: "{review.review_id}", target_id: "{target}", '
            f' stage_kind: "{stage}", verdict: "agree", '
            ' reason: "parsed optimization evidence supports the claim" });\n'
            'text("CALL VERDICT ok=" + r.is_success + " " + r.summary);'
        )
    queued = [r for r in store.list_review_requests("queued") if r.kind == "exit"]
    if queued:
        return (
            "const r = await tools.dag_review_evidence({"
            f' request_id: "{queued[0].request_id}", verdict: "accept", '
            ' reason: "partial delivery under the declared scope is acceptable" });\n'
            'text("EXIT REVIEW ok=" + r.is_success + " " + r.summary);'
        )
    return 'text("SUPERVISOR: no pending supervision item");'


@_REQUIRES_HOST_AND_RDKIT
@pytest.mark.parametrize("draft_order", ["before_suspend", "after_suspend"])
def test_cli_guided_supervisor_loop(tmp_path, monkeypatch, draft_order):
    """dag_guided 主场景（四个事实源 + 真实督导裁决回路）。

    所有图/证据事件都经生产工具（dag_propose_mechanism / dag_bind_evidence /
    dag_accept_mechanism / dag_review_call / dag_review_evidence）与真实
    Supervisor runtime_v2 agent 走；测试只读 store 生成脚本参数，绝不直接改
    DAG 状态绕过门禁。
    """
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    class GuidedLLM(ScriptedLLM):
        """通知可在当前 run 或下一 run 到达；业务动作按真实草稿状态选择。"""

        phase = "propose"
        draft_order_checked = False

        async def complete(self, agent, messages, tools, **kwargs):
            self.core = backend.last_core
            if agent.role_id == "supervisor" and not self.calls_seen_for_supervisor():
                if draft_order == "after_suspend":
                    await wait_until(
                        lambda: any(
                            a.role_id == "coordinator" and a.state is AgentState.SUCCEEDED
                            for a in self.core.agents.values()
                        ),
                        what="coordinator parks before the draft verdict",
                    )
            if agent.role_id == "coordinator":
                key = (agent.role_id, agent.id, agent.current_run.run_id)
                turn = self._turn_index.get(key, 0) + 1
                if self.phase == "propose":
                    step = js(turn, _GUIDED_PROPOSE_PROGRAM)
                    self.phase = "spawn"
                elif self.phase == "spawn":
                    if draft_order == "before_suspend" and not self.draft_order_checked:
                        await wait_until(
                            lambda: any(
                                a.role_id == "supervisor" and a.state is AgentState.SUCCEEDED
                                for a in self.core.agents.values()
                            ),
                            what="draft supervisor finishes before coordinator continues",
                        )
                        self.draft_order_checked = True
                    draft = await asyncio.to_thread(
                        lambda: _dag_store(agent.project_id).latest_draft()
                    )
                    if draft is not None and draft.get("state") == "accepted":
                        step = js(turn, _GUIDED_SPAWN_PROGRAM)
                        self.phase = "finish"
                    else:
                        step = text(turn, "suspended until the Supervisor decides on the draft")
                else:
                    step = calls(turn, [("stop", {"delivery_disposition": "partial"})], content=_BARRIER)
                self.script("coordinator", [step])
            return await super().complete(agent, messages, tools, **kwargs)

        def calls_seen_for_supervisor(self):
            return any(c["role"] == "supervisor" for c in self.calls_seen)

    llm = GuidedLLM()
    backend = RuntimeV2Backend(
        llm=llm, start_scheduler=True,
        poll_interval_s=0.05, stuck_grace_s=10.0,
    )

    # 子 agent：run1 = 确定性 compute 链 + 显式送审；run2 = 收到 call verdict 后收尾
    child_steps = [
        js(1, _guided_child_program, run=1),
        text(2, "evidence submitted for review", run=1, expect=Receipt(
            tool="js_exec", contains=["SUBMITTED evidence ok="])),
    ]
    for turn in range(3, 6):
        child_steps.append(text(turn, "evidence submitted for review", run=1))
    for turn in range(1, 5):
        child_steps.append(text(turn, "call verdict received", run=2))
    # 通知可多驱动一次收尾 run；未用到的幂等回执步骤无害。
    for extra_run in range(3, 7):
        for turn in range(1, 4):
            child_steps.append(text(turn, "call verdict received", run=extra_run))
    llm.script("small_mol", child_steps)

    # Supervisor：真实 agent；每轮自读持久信箱裁决当前待办（run 键控脚本）
    supervisor_steps = []
    for run_index in range(1, 9):
        supervisor_steps.append(js(1, _supervisor_catchup_program, run=run_index))
        for turn in range(2, 6):
            supervisor_steps.append(
                text(turn, "Supervision turn complete.", run=run_index)
            )
    llm.script("supervisor", supervisor_steps)

    runner, result, core = _run_cli_task(
        tmp_path, monkeypatch, llm, mode=OrchestrationMode.DAG_GUIDED, backend=backend
    )
    workspace = Path(result.sandbox).resolve()
    project_id = next(iter(core.projects))

    # 磁盘 + DB + 事件：子 agent 的同步 compute 链照常闭合
    _assert_job_chain(core, engine=engine, workspace=workspace, project_id=project_id)

    agents = {a.role_id: a for a in core.agents.values()}
    child = agents["small_mol"]
    parent = agents["coordinator"]
    supervisor = agents["supervisor"]      # 真实 spawn 出来的督导 agent

    # 显式验证两种合法交错，不能靠机器速度碰巧覆盖其中一种。
    parent_events = core.event_log.query_session(parent.id)
    draft_notice = next(
        e for e in parent_events
        if e.type == "agent.message_injected"
        and str(e.data.get("content", "")).startswith("[Supervisor draft verdict]")
    )
    first_parent_finish = next(e for e in parent_events if e.type == "run.finished")
    assert (draft_notice.seq < first_parent_finish.seq) == (draft_order == "before_suspend")
    assert child.state is AgentState.SUCCEEDED, (
        f"child ended {child.state.value}:\n{_dump_session(core, child.id)}"
    )
    assert parent.state is AgentState.SUCCEEDED, (
        f"parent ended {parent.state.value}:\n{_dump_session(core, parent.id)}"
    )

    # 督导裁决全部经生产工具（事件级证据）
    supervisor_tools = [
        e.data.get("tool_name")
        for e in core.event_log.query_session(supervisor.id)
        if e.type == "tool.requested"
    ]
    assert "dag_accept_mechanism" in supervisor_tools, supervisor_tools
    assert "dag_review_call" in supervisor_tools, supervisor_tools
    assert "dag_review_evidence" in supervisor_tools, supervisor_tools
    supervisor_runs = [
        e for e in core.event_log.query_session(supervisor.id) if e.type == "run.started"
    ]
    assert len(supervisor_runs) >= 3  # 草稿 / 送审 / 退出请求各一轮裁决

    # 图存储是权威：草稿被督导接受，显式送审的 CallReview 被裁决
    store = _dag_store(project_id)
    draft = store.latest_draft()
    assert draft is not None and draft.get("state") == "accepted", draft
    explicit = [r for r in store.list_call_reviews(None) if r.source == "explicit"]
    assert len(explicit) == 1, explicit
    review = explicit[0]
    assert review.suggested_stage == "geometry" and review.suggested_target_id
    assert review.state != "pending", review.state          # 督导已裁决
    assert review.tool_call_id in _tool_call_ids(core, child.id, "log_parser")

    # 父按真实门禁结束：partial 等裁决（wait_review）→ 程序关联批准后收尾
    parent_states = [
        (e.data.get("to"), e.data.get("reason"))
        for e in core.event_log.query_session(parent.id)
        if e.type == "agent.state_changed"
    ]
    assert ("waiting_approval", "wait_review") in parent_states, parent_states
    parent_messages = [
        str((e.data or {}).get("content") or "")
        for e in core.event_log.query_session(parent.id)
        if e.type == "agent.message_emitted"
    ]
    assert any("5.0 kcal/mol" in m for m in parent_messages), parent_messages
    dispositions = getattr(store, "list_delivery_dispositions", None)
    if dispositions is not None:
        assert any(d.get("disposition") == "partial" for d in dispositions()), dispositions


# ---------------------------------------------------------------------------
# Task 4（P1）：角色投影、无人值守继承与"白名单先于入库"的能力契约
# ---------------------------------------------------------------------------

_GUEST_FAIL_CLOSED_PROGRAM = r"""
const stopType = typeof tools.stop;
text("GUEST STOP typeof=" + stopType);
try {
  const stopped = await tools.stop({ reason: "guest direct control attempt" });
  text("GUEST STOP ok=" + stopped.is_success + " " + stopped.summary);
} catch (err) {
  if (stopType !== "undefined" || !(err instanceof TypeError)) { throw err; }
  text("GUEST STOP rejected=TypeError");
}
"""

_ASK_USER_PROGRAM = r"""
let outcome = "unreachable";
try {
  const asked = await tools.ask_user({ question: "Which pathway should I follow?" });
  outcome = "reached-tool ok=" + asked.is_success;
} catch (err) {
  outcome = "guest-rejected " + (err && err.message ? err.message : "error");
}
text("ASK " + outcome);
"""

_METHOD_POLICY_PROGRAM = r"""
async function attemptWriter(args) {
  try {
    const r = await tools.qm_input_writer(args);
    return r.is_success ? "ALLOWED" : "DENIED(is_success=false)";
  } catch (err) {
    return "DENIED(" + (err && err.message ? err.message.slice(0, 80) : "error") + ")";
  }
}
const bad = await attemptWriter({
  engine: "gaussian",
  source_type: "smiles", source_value: "O", method: "b3lyp",
  basis_set: "6-31g(d)", task_type: [{ "sp": null }],
  output_path: "calc/bad_method.gjf",
});
const ext = await attemptWriter({
  engine: "orca", source_type: "smiles", source_value: "O",
  external_program: "/opt/conda/envs/chemai/bin/mace",
  task_type: [{ "opt": null }],
  output_path: "calc/bad_external.inp",
});
const good = await tools.qm_input_writer({
  engine: "orca", source_type: "smiles", source_value: "O",
  method: "xTB2", basis_set: "", task_type: [{ "opt": null }],
  output_path: "calc/ok.inp",
});
text("BADM=" + bad + " | EXTM=" + ext + " | GOOD=" + good.is_success);
"""


@_REQUIRES_HOST
def test_cli_guest_fail_closed_and_role_projection(tmp_path, monkeypatch):
    """JS 客体只能调用线缆允许的工具：直接控制类（stop）从程序内调用被拒；
    角色投影唯一事实源仍是 capabilities（督导面不含 bash/计算入口）。"""
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _GUEST_FAIL_CLOSED_PROGRAM),
        text(2, "guest surface checked", expect=Receipt(
            tool="js_exec", contains=[
                "GUEST STOP typeof=undefined", "GUEST STOP rejected=TypeError",
            ])),
    ])
    _, _, core = _run_cli_task(tmp_path, monkeypatch, llm)
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    assert child.state is AgentState.SUCCEEDED, _dump_session(core, child.id)
    assert _tool_call_ids(core, child.id, "stop") == []
    outputs = _program_outputs(core, child)
    assert "GUEST STOP typeof=undefined" in outputs, outputs
    assert "GUEST STOP rejected=TypeError" in outputs, outputs

    # 客体调用被拒（stop 是 direct-only，不能从程序内调用）
    child_calls = [c for c in llm.calls_seen if c["role"] == "small_mol"]
    assert child_calls and child_calls[0]["tools"] == ["*"]  # 能力投影 = 角色 tool_policy

    # 督导面是 registry 的 supervisor_access 投影：不含 bash / 计算入口
    from cloudra.tools.capabilities import supervisor_tool_names

    supervisor_tools = set(supervisor_tool_names())
    assert "dag_review_call" in supervisor_tools
    assert "dag_accept_mechanism" in supervisor_tools
    assert "bash" not in supervisor_tools
    assert "submit_compute_job" not in supervisor_tools
    assert "qm_input_writer" not in supervisor_tools


@_REQUIRES_HOST
def test_cli_child_inherits_unattended_and_ask_user_blocked(tmp_path, monkeypatch):
    """子 agent 继承 unattended/clean_context/yolo/编排模式；ask_user 强行调用
    被 fail-closed 拦截，绝不进入 waiting_input。"""
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _ASK_USER_PROGRAM),
        text(2, "ask_user handled fail-closed", expect=Receipt(
            tool="js_exec", contains=["ASK "])),
    ])
    runner, result, core = _run_cli_task(tmp_path, monkeypatch, llm)
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    parent = next(a for a in core.agents.values() if a.role_id == "coordinator")

    assert child.settings.unattended is True
    assert child.settings.clean_context is True
    assert child.settings.yolo is True
    assert child.settings.orchestration_mode == parent.settings.orchestration_mode
    assert child.settings.invocation_protocol == parent.settings.invocation_protocol

    # fail-closed：要么客体线缆直接不暴露（program 抛错），要么 unattended stage
    # 拦截；两条路径都绝不允许 ask_user 真正执行
    asked_calls = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "tool.requested" and e.data.get("tool_name") == "ask_user"
    ]
    assert asked_calls == [], asked_calls
    outputs = _program_outputs(core, child)
    assert any(
        "guest-rejected" in o or "reached-tool ok=false" in o for o in outputs
    ), outputs
    states = {
        e.data.get("to")
        for e in core.event_log.query_session(child.id)
        if e.type == "agent.state_changed"
    }
    assert "waiting_input" not in states, states
    assert child.state is AgentState.SUCCEEDED


@_REQUIRES_HOST_AND_RDKIT
def test_cli_method_policy_blocks_before_compute(tmp_path, monkeypatch):
    """白名单在链路上先于入库：非白名单方法（含外部 MLIP 路由）被拦截且不创建
    计算作业行；白名单方法照常产出输入文件。"""
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, "Done. The computed barrier is 5.0 kcal/mol."),
    ])
    llm.script("small_mol", [
        js(1, _METHOD_POLICY_PROGRAM),
        text(2, "method policy enforced", expect=Receipt(
            tool="js_exec", contains=["BADM=DENIED", "EXTM=DENIED", "GOOD=true"])),
    ])
    runner, result, core = _run_cli_task(
        tmp_path, monkeypatch, llm, method_allowed=("xtb",)
    )
    child = next(a for a in core.agents.values() if a.role_id == "small_mol")
    workspace = Path(result.sandbox).resolve()

    blocked = [
        e for e in core.event_log.query_session(child.id)
        if e.type == "tool.blocked" and e.data.get("stage") == "method_policy"
    ]
    assert len(blocked) >= 2, [
        (e.data.get("tool_name"), e.data.get("message")) for e in blocked
    ]
    outputs = _program_outputs(core, child)
    assert any(
        "BADM=DENIED" in o and "EXTM=DENIED" in o and "GOOD=true" in o for o in outputs
    ), outputs
    # 拦截发生在执行前：非法调用的输出文件不存在，白名单调用照常落盘
    assert not (workspace / "calc" / "bad_method.gjf").exists()
    assert not (workspace / "calc" / "bad_external.inp").exists()
    assert (workspace / "calc" / "ok.inp").is_file()
    assert _compute_rows() == []          # 没有任何作业入库
    assert child.state is AgentState.SUCCEEDED


# ---------------------------------------------------------------------------
# Task 5（P1）：并发隔离、stop 级联与关闭时真实 JS host 回收
# ---------------------------------------------------------------------------

async def _web_harness(core, llm, tmp_path, *, concurrency=1):
    """Web 入口装配：live core + 测试 scheduler + broker + BenchmarkService。"""
    from cloudra.benchmark.batch import BenchmarkService
    from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
    from cloudra.scheduler.daemon import SchedulerDaemon

    assemble_live_pipeline(core, llm)
    bus = CommandBus(core)
    scheduler = SchedulerDaemon(
        worker_id=f"scheduler:{os.getpid()}:fp{core.projects and len(core.projects)}",
        poll_interval=0.05,
    )
    await scheduler.start()
    broker = ComputeNotifyBroker(core, poll_interval=0.05)
    await broker.start()
    service = BenchmarkService(core, bus, data_dir=tmp_path / "bench")
    return bus, scheduler, broker, service


@_REQUIRES_HOST_AND_RDKIT
@pytest.mark.asyncio
async def test_web_concurrent_mixed_success_and_failure(tmp_path, monkeypatch):
    """两题并发：一题的推理崩溃不终止另一题；沙箱、作业与记录彼此独立。"""
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    core = RuntimeCore(strict_events=True)
    llm = ScriptedLLM(core)   # 按项目名分池：并发两题脚本互不串
    # T1 的 coordinator 第一轮就崩溃（脚本化失败）；T2 走完整链路
    llm.script("coordinator", [crash(1, "T1 coordinator crashed")], project="benchmark:T1")
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, _BARRIER),
        text(1, _BARRIER),
    ], project="benchmark:T2")
    llm.script("small_mol", [
        js(1, _CHILD_SYNC_CHAIN_PROGRAM),
        text(2, "chain complete, reporting", expect=Receipt(
            tool="js_exec", contains=["PARSED job="])),
        text(3, "chain complete, reporting"),
    ], project="benchmark:T2")

    tasks_dir = _write_tasks(tmp_path / "tasks", "T1", "T2")
    _, scheduler, broker, service = await _web_harness(core, llm, tmp_path, concurrency=2)
    try:
        await service.start(tasks_dirs=[tasks_dir], only="", concurrency=2)
        batch = service._batch
        await wait_until(
            lambda: service.status()["status"] in {"done", "error"},
            timeout=90.0,
            what="batch completion",
        )
        final = service.status()
        by_task = {t["task_id"]: t for t in final["tasks"]}
        assert by_task["T2"]["status"] == "scored", by_task["T2"]
        assert by_task["T1"]["status"] in {"error", "scored"}, by_task["T1"]
        # T1 失败不终止 T2：T2 有独立沙箱与自己的作业
        t1_sandbox = batch.sandboxes / "T1" / batch.batch_id
        t2_sandbox = batch.sandboxes / "T2" / batch.batch_id
        assert t1_sandbox != t2_sandbox
        rows = _compute_rows()
        assert len(rows) == 1
        assert str(rows[0]["path"]).startswith(str(Path(by_task["T2"]["project_id"]) if False else t2_sandbox))
        assert rows[0]["state"] == "done"
        assert not (t1_sandbox / "calc" / "input.gjf").exists()
        # 两题各自的运行记录都在（失败也留痕）
        from cloudra.benchmark.runner import BenchmarkDB

        db = BenchmarkDB(tmp_path / "bench" / "benchmark.db")
        run_ids = {r["task_id"] for r in db.list_runs_for(final["batch_id"])}
        assert run_ids == {"T1", "T2"}
    finally:
        await broker.close()
        await scheduler.close()


@_REQUIRES_HOST_AND_RDKIT
@pytest.mark.asyncio
async def test_web_stop_cascades_but_keeps_live_compute(tmp_path, monkeypatch):
    """batch stop：级联取消推理子树并停止新请求；已提交的计算继续登记与运行
    （测试用控制文件释放引擎后自行收尾），绝不被 kill。"""
    from cloudra.infra.compute_utils import calc_lock_path, guard_lock_path
    from cloudra.infra.flocks import is_lock_held

    # 只观察真实 spawn 返回的句柄；stop 取消同步等待后，由测试负责等 guard
    # 自然退出并 reap，不能因账本先写 done 就提前关掉事件循环。
    guard_processes = []
    original_spawn = asyncio.create_subprocess_exec

    async def capture_guard(*args, **kwargs):
        proc = await original_spawn(*args, **kwargs)
        if args[1:3] == ("-m", "cloudra.runtime.monitor"):
            guard_processes.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture_guard)
    engine = install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    engine.set_control("wait")
    core = RuntimeCore(strict_events=True)
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, _BARRIER),
        text(1, _BARRIER),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_SYNC_CHAIN_PROGRAM),
        text(2, "chain complete"),
    ])

    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    _, scheduler, broker, service = await _web_harness(core, llm, tmp_path)
    try:
        await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1)
        # running 行先于 guard 启动落库，不能拿它当活计算的同步点；等待引擎
        # 已读到输入，再用生产 flock 口径确认 guard/calculator 都已启动。
        await wait_until(lambda: bool(engine.runs()), timeout=60.0, what="live calculator startup")
        started_runs = engine.runs()
        rows = _compute_rows()
        assert len(started_runs) == len(rows) == 1, (started_runs, rows)
        job_id = rows[0]["id"]
        workdir = str(Path(rows[0]["path"]).parent)
        assert started_runs[0]["input"] == rows[0]["path"]
        assert rows[0]["state"] == "running", rows[0]
        guard_lock = guard_lock_path(workdir, job_id)
        calc_lock = calc_lock_path(workdir, job_id)
        assert is_lock_held(guard_lock)
        assert is_lock_held(calc_lock)
        await service.stop()
        await wait_until(
            lambda: service.status()["status"] == "stopped",
            timeout=60.0,
            what="batch stop convergence",
        )
        # 推理子树落 cancelled，且取消后不再新发 LLM 请求
        cancelled = [
            a for a in core.agents.values() if a.state is AgentState.CANCELLED
        ]
        assert cancelled, {a.role_id: a.state.value for a in core.agents.values()}
        for agent in cancelled:
            events = core.event_log.query_session(agent.id)
            cancel_seq = max(
                i for i, e in enumerate(events)
                if e.type == "agent.state_changed" and e.data.get("to") == "cancelled"
            )
            later_llm = [
                e for e in events[cancel_seq + 1:] if e.type == "llm.request_started"
            ]
            assert later_llm == [], (agent.role_id, later_llm)

        # 活计算仍在册且未终态（没有被 kill、没有被标失败）
        rows = _compute_rows()
        assert len(rows) == 1 and rows[0]["id"] == job_id, rows
        assert rows[0]["state"] == "running", rows[0]
        assert is_lock_held(guard_lock)
        assert is_lock_held(calc_lock)
        assert not rows[0]["end_timestamp"] or rows[0]["end_timestamp"] <= 0, rows[0]

        # 释放引擎：计算自行跑到终态（证明 stop 没碰它）
        engine.release()
        await wait_until(
            lambda: (_compute_rows() or [{}])[0].get("state") == "done",
            timeout=60.0,
            what="compute completion after stop",
        )
        assert _compute_rows()[0]["id"] == job_id
        assert engine.runs() == started_runs, "stop must not restart the calculator"
    finally:
        engine.release()
        await broker.close()
        await scheduler.close()
        await asyncio.wait_for(
            asyncio.gather(*(proc.wait() for proc in guard_processes)), timeout=60.0
        )


@_REQUIRES_HOST_AND_RDKIT
@pytest.mark.asyncio
async def test_web_shutdown_reaps_real_js_host(tmp_path, monkeypatch):
    """关闭口径：以持有的 host 进程句柄等待真实退出（不扫 PID 文本），
    core.aclose() 后登记表为空且不再有存活 host。"""
    install_engine(monkeypatch, tmp_path / "bin", "gaussian")
    core = RuntimeCore(strict_events=True)
    llm = ScriptedLLM()
    llm.script("coordinator", [
        js(1, _SPAWN_PROGRAM),
        text(2, "suspended until children finish"),
        text(1, _BARRIER),
        text(1, _BARRIER),
    ])
    llm.script("small_mol", [
        js(1, _CHILD_SYNC_CHAIN_PROGRAM),
        text(2, "chain complete"),
    ])
    tasks_dir = _write_tasks(tmp_path / "tasks", "T1")
    _, scheduler, broker, service = await _web_harness(core, llm, tmp_path)
    js_runtime = core.runner.pipeline.js_runtime
    observed: list = []
    try:
        await service.start(tasks_dirs=[tasks_dir], only="", concurrency=1)

        def capture() -> bool:
            procs = js_runtime.active_executions()
            if procs:
                observed.extend(procs.values())
                return True
            return False

        await wait_until(capture, timeout=60.0, what="a live js host")
        await wait_until(
            lambda: service.status()["status"] in {"done", "error"},
            timeout=90.0,
            what="batch completion",
        )
        # 持有的句柄必须已真实退出（returncode 非 None = 已 reap）
        for proc in observed:
            assert proc.returncode is not None, proc
        assert js_runtime.active_executions() == {}
        await core.aclose()
        assert js_runtime.active_executions() == {}
        await core.aclose()  # 幂等
    finally:
        await broker.close()
        await scheduler.close()
