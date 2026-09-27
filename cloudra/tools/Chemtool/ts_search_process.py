"""TS 搜索 SOP 的 agent 可见接口：`ts_prepare` 与 `ts_resume` 两个函数。

**这是这条 SOP 暴露给 agent 的全部接口**（SOP §2「两个函数」）。刻意**没有** status/查询
函数：状态变更会经事件回流，暴露查询接口只会诱导模型反复轮询、白烧轮次与上下文。

- `ts_prepare`：起一次搜索。进程随后自主推进（建结构 → 映射 → 组装 → 路径初猜 → 校验 →
  提交 → 精修 → 判定）。
- `ts_resume`：进程在**阻塞**处停下后，带上调整过的声明从当前位置继续。**只接受局部覆盖**，
  不是重新声明整条反应。

校验是**流程自己的职责**（SOP §4）：这里不设"要不要提交"的确认步骤，校验失败就以阻塞
返回，并**点名到原子**，agent 据此改声明再 `ts_resume`。

状态机与目录约定在 `cloudra.tools.core.ts_process`；本文件只是薄接口。
"""

from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.geometry_inputs import normalize_ts_atoms
from cloudra.tools.core.ts_process import (
    TsAdjustment,
    TsBlocked,
    TsDeclaration,
    TsProcessRecord,
    TsStageRecord,
    TsStartRequest,
    load_record,
    resume,
    start,
)

description = (
    "Run the transition-state search SOP as a durable process: build both endpoints from SMILES. "
    "For cyclic TS preorganization, declare ring_order and/or distance_filters in complete atom order (Gaussian 1-based, ORCA 0-based). Use explicit "
    "windows; missing forming pairs receive a visible 1.6–3.0 Å fallback. "
    "The process uses only qualified constrained reactant seeds, and ts_resume can correct the "
    "guidance before refinement submission. "
    "map atoms, assemble the reactive complex, generate a path guess (xTB metadynamics, falling back "
    "to IDPP interpolation when xtb is absent), validate internally, then submit and judge. "
    "Returns a run_id; the process advances autonomously and STOPS with a `blocked` payload when it "
    "needs you to change the declaration — fix what the payload names and call ts_resume. "
    "There is deliberately NO status/progress query function: state changes are delivered to you, so "
    "do not poll. A blocked process is a normal outcome, not an error. "
    "Use for: locating a transition state from reactant/product SMILES. "
    "Do not use for: single-point energies, conformer ensembles (use conformer_search) or plain "
    "input writing (use qm_input_writer)."
)


class TsPrepare_input_schema(input_schema):
    declaration: TsDeclaration = Field(
        description="Reaction declaration. All atom fields use complete built XYZ order including H: "
                    "Gaussian starts at 1; ORCA at 0. A three-atom identity atom_map is [1,2,3] "
                    "for Gaussian or [0,1,2] for ORCA; entries follow product atom order. "
                    "method is required. For solvation, set extra_keywords on the DFT declaration "
                    "(e.g. CPCM(Water)), scan.extra_route for an exploratory scan, and "
                    "path_solvation for the optional xTB path guess. Missing maps return built atom "
                    "tables. ring_order and distance_filters work independently or together.",
    )
    workspace_dir: Optional[str] = Field(
        default=None,
        description="Workspace root; the run directory is created at <workspace_dir>/ts/<run_id>/. "
                    "Defaults to the Agent working directory. Relative paths resolve against the "
                    "Agent working directory."
    )


class TsResume_input_schema(input_schema):
    run_id: str = Field(description="run_id returned by ts_prepare")
    adjustment: TsAdjustment = Field(
        default_factory=TsAdjustment,
        description="Local overrides only: ring_order, distance_filters, reaction_center, atom_map, path_refinement_runs, "
                    "max_interventions. This is not a re-declaration of the whole reaction.",
    )
    workspace_dir: Optional[str] = Field(
        default=None,
        description="Workspace root, same as ts_prepare. Defaults to the Agent working directory.",
    )


class TsProcess_output_schema(output_schema):
    is_success: bool = Field(
        description="Whether the process state was advanced. NOTE: a blocked or terminal process "
                    "still reports is_success=True — read `blocked` / `terminal` for the outcome; "
                    "is_success=False means the call itself could not run.",
    )
    run_id: str = Field(default="", description="Process run id (pass it to ts_resume)")
    run_dir: str = Field(default="", description="Run directory holding the whole site")
    stage: str = Field(default="", description="Stage the process stopped at")
    waiting_for: str = Field(
        default="",
        description="Set when the process is waiting on a submitted compute job (e.g. 'job:12'). "
                    "Waiting is NOT blocked: nothing needs your decision, no event is emitted, and "
                    "the existing compute notification path will wake you. Just call ts_resume "
                    "(with an empty adjustment) when that happens.",
    )
    terminal: Optional[str] = Field(
        default=None,
        description="Terminal state: verified / candidate_only / search_failed / invalid_input. "
                    "null while the process can still advance. `search_failed` is NOT a claim that "
                    "the reaction is impossible.",
    )
    blocked: Optional[TsBlocked] = Field(
        default=None,
        description="Present when the process needs you to change the declaration: failure class, "
                    "stage, atom-level details and which declaration items to fix.",
    )
    path_kind: str = Field(
        default="not_attempted",
        description="How the path guess was produced: xtb_path (real metadynamics path search) / "
                    "xtb_path_failed (the engine ran but produced no usable guess) / "
                    "idpp_fallback (xtb unavailable: a DEGRADED interpolation route) / "
                    "not_attempted (no path search was started).",
    )
    intervention_count: int = Field(default=0, description="How many times ts_resume was called")
    stage_records: list[TsStageRecord] = Field(
        default_factory=list, description="Per-stage outcome, including not_implemented stages"
    )
    evidence_candidates: list[str] = Field(
        default_factory=list,
        description="Small artifacts that may be bound as evidence. Per-iteration trajectory frames "
                    "are deliberately excluded.",
    )
    message: str = Field(default="", description="Status or error message")


def _to_output(record: TsProcessRecord) -> TsProcess_output_schema:
    if record.terminal is not None:
        headline = (
            f"{record.run_id} reached terminal state '{record.terminal}' at stage '{record.stage}'."
        )
        try:
            detail = record.stage_record(record.stage).detail
        except KeyError:
            detail = ""
        if detail:
            # 终态的原因要能直接被 agent 读到（否则它只有状态没有依据）
            headline += f" {detail}"
    elif record.waiting_for:
        headline = (
            f"{record.run_id} is waiting on {record.waiting_for} at stage '{record.stage}'; the "
            "compute notification path wakes you, so do not poll — call ts_resume when it arrives."
        )
    elif record.blocked is not None:
        headline = (
            f"{record.run_id} is blocked at stage '{record.blocked.stage}' "
            f"({record.blocked.failure_class}): {record.blocked.message}"
        )
    else:
        headline = f"{record.run_id} is at stage '{record.stage}' and can advance."
    return TsProcess_output_schema(
        is_success=True,
        run_id=record.run_id,
        run_dir=record.run_dir,
        stage=record.stage,
        waiting_for=record.waiting_for,
        terminal=record.terminal,
        blocked=record.blocked,
        path_kind=record.path_kind,
        intervention_count=record.intervention_count,
        stage_records=record.stage_records,
        evidence_candidates=list(record.evidence_candidates),
        message=headline,
    )


def _resolve_workspace(tool: Tool, value: Optional[str]) -> str:
    """工作区根目录：显式值走既有路径语义；否则用绑定 agent 的工作目录。"""
    if value:
        return resolve_tool_path(tool, value)
    subagent = getattr(tool, "subagent", None)
    root = getattr(subagent, "working_directory", None)
    if not root:
        raise ValueError(
            "no workspace_dir was given and no Agent working directory is bound; pass "
            "workspace_dir explicitly"
        )
    return str(root)


class TsPrepare(Tool):
    tool_id: str = 't-59'
    tool_name: str = 'ts_prepare'
    tool_description: str = description
    input_schema: Any = TsPrepare_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: TsPrepare_input_schema, session: Session) -> TsProcess_output_schema:
        import asyncio

        try:
            # 工作区解析失败（没给也没绑定工作目录）属调用错误，必须回 schema 而不是抛出去
            workspace = _resolve_workspace(self, user_input.workspace_dir)
            # 归属与 submit_compute_job 同一来源：项目 conversation_id + 调用 agent 的
            # session.id——作业终态推送只认这两个字段
            request = TsStartRequest(
                declaration=normalize_ts_atoms(user_input.declaration, engine=user_input.declaration.engine),
                workspace_dir=workspace,
                owner_conversation_id=getattr(self.subagent, "conversation_id", None) or "",
                owner_session_id=getattr(session, "id", None) if session else None,
            )
            # 阶段推进是 CPU + 子进程 + 文件 IO，必须离开事件循环
            record = await asyncio.to_thread(start, request)
        except Exception as exc:  # noqa: BLE001 - 起不来就是工具调用失败，如实返回
            return TsProcess_output_schema(
                is_success=False, message=f"ts_prepare could not start a run: {exc}"
            )
        return _to_output(record)


class TsResume(Tool):
    tool_id: str = 't-60'
    tool_name: str = 'ts_resume'
    tool_description: str = description
    input_schema: Any = TsResume_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: TsResume_input_schema, session: Session) -> TsProcess_output_schema:
        import asyncio

        try:
            workspace = _resolve_workspace(self, user_input.workspace_dir)
        except ValueError as exc:
            return TsProcess_output_schema(
                is_success=False, run_id=user_input.run_id, message=str(exc)
            )
        try:
            record = await asyncio.to_thread(load_record, workspace, user_input.run_id)
        except Exception as exc:  # noqa: BLE001 - 找不到运行目录就是调用错误
            return TsProcess_output_schema(
                is_success=False,
                run_id=user_input.run_id,
                message=(
                    f"ts_resume could not load run {user_input.run_id!r} from {workspace}: {exc}. "
                    "Check the run_id returned by ts_prepare."
                ),
            )
        try:
            adjustment = normalize_ts_atoms(user_input.adjustment, engine=record.declaration.engine)
            record = await asyncio.to_thread(resume, record, adjustment)
        except ValueError as exc:
            # 终态不可续：明确报出终态与原因，不静默重开
            return TsProcess_output_schema(
                is_success=False,
                run_id=record.run_id,
                run_dir=record.run_dir,
                stage=record.stage,
                terminal=record.terminal,
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return TsProcess_output_schema(
                is_success=False,
                run_id=user_input.run_id,
                message=f"ts_resume could not advance run {user_input.run_id!r}: {exc}",
            )
        return _to_output(record)


def get_class():
    return TsPrepare
