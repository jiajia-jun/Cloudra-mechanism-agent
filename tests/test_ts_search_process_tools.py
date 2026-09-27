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


async def _prepare(tmp_path, **overrides):
    tool = TsPrepare()
    object.__setattr__(tool, "subagent", _OwnerStub())
    return await tool.tool_call(
        TsPrepare_input_schema(
            declaration=_declaration(**overrides), workspace_dir=str(tmp_path)
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
async def test_prepare_returns_a_run_id_and_stops_with_a_blocked_payload(tmp_path):
    """前端 + 提交跑完后在 refine 等作业终态：is_success=True，且 waiting 不是 blocked。"""
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
    # 提交真的发生了（作业号 + 精修输入）
    assert statuses["submit"] == "done"
    assert statuses["refine"] == "waiting"


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


def test_the_sop_surface_is_exactly_two_functions_and_no_status_query():
    """SOP §2：流程只暴露两个函数，**刻意没有** status/查询接口（否则诱导轮询）。

    注意 ``ts_guess`` 是既有的**底层原语**工具（guess 阶段与它共用同一个 xTB 路径运行器），
    不属于流程接口，也不被流程取代——它仍然可以被直接调用。
    """
    from cloudra.tools import get_tools_lst

    names = {entry.tool_name for entry in get_tools_lst()}
    # 流程接口恰好这两个
    sop_tools = {n for n in names if n.startswith("ts_")} - {"ts_guess"}
    assert sop_tools == {"ts_prepare", "ts_resume"}
    # 没有任何形态的状态查询入口
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
    out = await TsResume().tool_call(
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
async def test_resume_on_a_terminal_run_is_refused_with_the_terminal_state(tmp_path):
    """终态不可续：明确报出终态，不静默重开一条新流程。"""
    first = await _prepare(tmp_path, method="")
    assert first.terminal == "invalid_input"
    out = await TsResume().tool_call(
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
    out = await TsResume().tool_call(
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
    second = await TsResume().tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(atom_map=ATOM_MAP),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    third = await TsResume().tool_call(
        TsResume_input_schema(
            run_id=first.run_id, adjustment=TsAdjustment(reaction_center=[]),
            workspace_dir=str(tmp_path),
        ),
        session=None,
    )
    assert third.terminal == "search_failed"
    assert "NOT a claim" in third.message or "not a claim" in third.message.lower()
    del second


@pytest.mark.asyncio
async def test_resume_after_a_compute_wake_needs_no_adjustment(tmp_path):
    """计算通知唤醒后 agent 调 ts_resume 时**没有什么要改**——空 adjustment 必须合法。

    这是 wait→wake→resume 这条主路径的契约：等待期间没有决策可做，唤醒后只是让流程
    重新读一次作业那一行继续推进。空 adjustment 非法的话，这条路径就走不通了。
    """
    first = await _prepare(tmp_path)
    assert first.waiting_for.startswith("job:")
    out = await TsResume().tool_call(
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
