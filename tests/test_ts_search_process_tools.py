"""ts_prepare / ts_resume：SOP 的 **全部** agent 可见接口（只有这两个函数）。

护栏重点：
- 阻塞是**正常结果**（is_success=True + blocked），不是错误
- 接口里**没有** status/查询函数（状态经事件回流，暴露查询只会诱导轮询）
- 终态不可 resume
- 校验由流程自己做，失败时把要改的声明项写在 blocked.needs 里
"""

import pytest

pytest.importorskip("rdkit", reason="ts_prepare requires RDKit (chem extra)")

from cloudra.tools.Chemtool.ts_search_process import (  # noqa: E402
    TsPrepare,
    TsPrepare_input_schema,
    TsResume,
    TsResume_input_schema,
)
from cloudra.tools.core.ts_process import (  # noqa: E402
    TsAdjustment,
    TsBudget,
    TsDeclaration,
)

REACTANT = "[F-].CCl"
PRODUCT = "CF.[Cl-]"
REACTION_CENTER = [(0, 1)]
ATOM_MAP = [1, 0, 3, 4, 5, 2]


def _declaration(**overrides) -> TsDeclaration:
    payload = {
        "reactant_smiles": REACTANT,
        "product_smiles": PRODUCT,
        "charge": -1,
        "multiplicity": 1,
        "method": "b3lyp/def2svp",
        "reaction_center": REACTION_CENTER,
        "atom_map": ATOM_MAP,
    }
    payload.update(overrides)
    return TsDeclaration(**payload)


class _OwnerStub:
    """工具归属来源的最小替身（生产上是 _LegacyAgentBridge）。"""

    conversation_id = "test_project"
    working_directory = None


def _owned_tool(tool_class):
    tool = tool_class()
    object.__setattr__(tool, "subagent", _OwnerStub())
    return tool


async def _prepare(tmp_path, **overrides):
    from cloudra.services.nodes import default_resources

    resources = default_resources()
    tool = _owned_tool(TsPrepare)
    return await tool.tool_call(
        TsPrepare_input_schema(
            declaration=_declaration(**overrides), workspace_dir=str(tmp_path),
            compute_cpus=max(1, min(2, resources["cpus"])),
            compute_memory_mb=min(4096, resources["memory_mb"]),
        ),
        session=None,
    )


@pytest.mark.asyncio
async def test_prepare_and_resume_accept_ring_guidance(tmp_path):
    declaration = _declaration(
        reactant_smiles="CCO.O", product_smiles="CCO.O", charge=0,
        reaction_center=[], atom_map=[], ring_order=[0, 1, 2, 9],
        distance_filters=[
            {"atoms": [2, 9], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [0, 9], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [1, 9], "min_ang": 2.5, "max_ang": 3.8},
        ],
    )
    prepare_tool = TsPrepare()
    object.__setattr__(prepare_tool, "subagent", _OwnerStub())
    first = await prepare_tool.tool_call(
        TsPrepare_input_schema(declaration=declaration, workspace_dir=str(tmp_path)),
        session=None,
    )
    assert first.is_success and first.blocked.stage == "map"
    resume_tool = TsResume()
    object.__setattr__(resume_tool, "subagent", _OwnerStub())
    updated = await resume_tool.tool_call(TsResume_input_schema(
        run_id=first.run_id,
        adjustment=TsAdjustment(distance_filters=[
            {"atoms": [2, 9], "min_ang": 2.5, "max_ang": 4.0},
            {"atoms": [0, 9], "min_ang": 2.5, "max_ang": 3.8},
            {"atoms": [1, 9], "min_ang": 2.5, "max_ang": 3.8},
        ]),
        workspace_dir=str(tmp_path),
    ), session=None)
    assert updated.is_success and updated.blocked.stage == "map"


# ---------------------------------------------------------------------------
# ts_prepare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_limit", [None, 3968])
async def test_prepare_returns_a_run_id_and_waits_for_queued_path(tmp_path, monkeypatch, memory_limit):
    """Durable preparation queues the path job before refinement; waiting is not blocked."""
    import asyncio

    from cloudra.persistence.database import ComputeDB
    from cloudra.services import nodes
    from cloudra.tools.core.ts_process import load_record

    if memory_limit is not None:
        resources = dict(nodes.default_resources(), memory_mb=memory_limit)
        monkeypatch.setattr(nodes, "default_resources", lambda: resources)
    out = await _prepare(tmp_path)
    assert out.is_success is True, out.message
    assert out.run_id == "ts_0001"
    assert out.run_dir
    # 等计算不是阻塞：没有 blocked、没有终态，但明确说明在等什么
    assert out.blocked is None
    assert out.terminal is None
    assert out.waiting_for.startswith("job:")
    assert "do not poll" in out.message
    statuses = {r.stage: r.status for r in out.stage_records}
    assert out.stage == "guess"
    assert "submit" not in statuses and "refine" not in statuses

    def submitted_path():
        record = load_record(str(tmp_path), out.run_id)
        with ComputeDB().connect() as con:
            job = con.execute(
                "SELECT state, jobtype, path FROM compute_jobs WHERE id=?",
                (record.job_steps[0].job_id,),
            ).fetchone()
        return record, job

    record, job = await asyncio.to_thread(submitted_path)
    assert [step.purpose for step in record.job_steps] == ["path"]
    assert out.waiting_for == f"job:{record.job_steps[0].job_id}"
    assert tuple(job) == ("ready", "chem_task", record.job_steps[0].input_path)
    if memory_limit is not None:
        assert record.compute_memory_mb == memory_limit


@pytest.mark.asyncio
async def test_prepare_blocks_with_actionable_needs_when_atom_map_is_missing(tmp_path):
    """缺原子映射：阻塞并点名要补的声明项——校验是流程自己的职责，不是问 agent 要不要跑。"""
    out = await _prepare(tmp_path, atom_map=[])
    assert out.is_success is True
    assert out.blocked.stage == "map"
    assert out.blocked.failure_class == "atom_map_missing"
    assert out.blocked.needs == ["atom_map"]
    assert out.path_kind == "not_attempted"


@pytest.mark.asyncio
async def test_prepare_invalid_input_is_terminal_but_not_a_tool_error(tmp_path):
    """声明缺方法 → invalid_input 终态；仍是 is_success=True（调用本身成功了）。"""
    out = await _prepare(tmp_path, method="")
    assert out.is_success is True
    assert out.terminal == "invalid_input"
    assert "method is empty" in out.message


@pytest.mark.asyncio
async def test_prepare_without_workspace_reports_a_caller_error(tmp_path):
    """既没给 workspace_dir 也没绑定工作目录：回 is_success=False，不抛异常。"""
    out = await TsPrepare().tool_call(
        TsPrepare_input_schema(declaration=_declaration()), session=None
    )
    assert out.is_success is False
    assert "workspace_dir" in out.message


def test_the_state_machine_surface_has_two_writers_and_readonly_inspection():
    """One prepare, revisions through resume, independent read-only inspection.

    注意 ``ts_guess`` 是既有的**底层原语**工具（guess 阶段与它共用同一个 xTB 路径运行器），
    不属于流程接口，也不被流程取代——它仍然可以被直接调用。
    """
    from cloudra.tools import get_tools_lst

    names = {entry.tool_name for entry in get_tools_lst()}
    sop_tools = {n for n in names if n.startswith("ts_")} - {"ts_guess"}
    assert sop_tools == {"ts_prepare", "ts_resume", "ts_inspect"}
    # No redundant status aliases.
    assert not {n for n in names if n in {
        "ts_status", "ts_process_status", "ts_progress", "ts_query", "ts_poll",
    }}


# ---------------------------------------------------------------------------
# ts_resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_supplies_the_missing_declaration_and_advances(tmp_path):
    first = await _prepare(tmp_path, atom_map=[])
    assert first.blocked.needs == ["atom_map"]
    out = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id=first.run_id,
            adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert out.is_success is True, out.message
    assert out.intervention_count == 1
    assert {r.stage: r.status for r in out.stage_records}["map"] == "done"
    assert out.waiting_for.startswith("job:")


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_scope", ["project", "owner"])
async def test_resume_rejects_a_different_project_or_owner(tmp_path, foreign_scope):
    import asyncio
    from types import SimpleNamespace

    from cloudra.tools.core.ts_process import load_record

    first = await _prepare(tmp_path, atom_map=[])
    original = await asyncio.to_thread(load_record, str(tmp_path), first.run_id)
    tool = _owned_tool(TsResume)
    session = None
    if foreign_scope == "project":
        tool.subagent.conversation_id = "another_project"
    else:
        session = SimpleNamespace(id="another_owner")
    out = await tool.tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=session,
    )
    assert out.is_success is False
    assert "different project or owner" in out.message
    unchanged = await asyncio.to_thread(load_record, str(tmp_path), first.run_id)
    assert unchanged.model_dump() == original.model_dump()


@pytest.mark.asyncio
async def test_resume_on_a_terminal_run_is_refused_with_the_terminal_state(tmp_path):
    """终态不可续：明确报出终态，不静默重开一条新流程。"""
    first = await _prepare(tmp_path, method="")
    assert first.terminal == "invalid_input"
    out = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id=first.run_id,
            adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert out.is_success is False
    assert out.terminal == "invalid_input"
    assert "not resumed" in out.message


@pytest.mark.asyncio
async def test_resume_with_an_unknown_run_id_is_a_clear_caller_error(tmp_path):
    out = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id="ts_9999", adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert out.is_success is False
    assert "ts_9999" in out.message


@pytest.mark.asyncio
async def test_resume_budget_exhaustion_lands_terminal_search_failed(tmp_path):
    """预算耗尽落 search_failed，并注明"搜索失败 ≠ 反应不可能"。"""
    first = await _prepare(tmp_path, atom_map=[], budget=TsBudget(max_interventions=1))
    second = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(reaction_center=[]),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert second.is_success is True, second.message
    assert second.blocked.needs == ["atom_map"]
    assert second.intervention_count == 1
    third = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert third.terminal == "search_failed"
    assert "NOT a claim" in third.message or "not a claim" in third.message.lower()


@pytest.mark.asyncio
async def test_empty_resume_reads_waiting_checkpoint_without_advancing(tmp_path):
    """An empty adjustment is legal and reads the system-owned checkpoint unchanged."""
    first = await _prepare(tmp_path)
    assert first.waiting_for.startswith("job:")
    out = await _owned_tool(TsResume).tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(), workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert out.is_success is True, out.message
    assert out.intervention_count == 0
    # 作业还没到终态（测试里没有调度守护），所以仍是 waiting，没有伪造终态
    assert out.terminal is None
    assert out.waiting_for.startswith("job:")
    assert out.model_dump() == first.model_dump()
