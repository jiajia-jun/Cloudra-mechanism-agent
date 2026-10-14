"""DAG harness as a policy stage.

The stage wraps the deterministic dag/ engine (DagController) without making
the turn pipeline aware of graphs.  ``dag_record`` / ``dag_guided`` are just
the same stage enabled by the agent's settings.

Task 4A（统一运行结束门禁，计划 §6）：stop 的交付审计不在 before_tool 里做
任何带副作用的预检——显式 stop 与无 tool_calls 的纯文本最终回复都在
runner 收尾前的统一边界经 ``audit_run_end`` 进入 ``audit_stop`` 判定，退出
审批请求只在那里创建一次。before_tool 只剩实质计算门禁（substantive gate）。

State & side-effect declaration (3d):

- The graph itself is NOT stage state: the single authority is the project's
  ConversationDB (dag store, on-disk SQLite), so every restart rebuilds it
  losslessly.  ``_controllers`` is a **deliberately volatile**, lazily
  rebuilt cache of DagController instances (``_controller()`` recreates them
  on demand); dropping it on restart costs one reconstruction, nothing else.
- Side effects (SQLite via DagController, supervisor notification via
  notify_supervisor) stay inside the stage by exemption: DagController is an
  imperative engine over its own durable store and the notification is
  inherently IO, so purifying them into Decision/Effect objects would build
  a parallel command system for no recoverability gain — the recoverable
  state already lives in the dag store and the event log.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from cloudra.base.role_identity import legacy_agent_id_for_role
from cloudra.dag.controller import DagController
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult

logger = logging.getLogger(__name__)


class DagPolicyStage:
    name = "dag"

    def __init__(self, core=None) -> None:
        self._controllers: dict[str, DagController] = {}
        # Optional kernel handle, used by the run-end gate's pending-background
        # check (v2-native siblings/reminders projection via the controller).
        self._core = core

    @staticmethod
    def _legacy_agent_id(role_id: str) -> str:
        """DAG 变更日志与 CallReview sidecar 使用 legacy 子 agent id（a-0..a-8）；
        v2 的 role_id 经唯一映射表（cloudra.base.role_identity）推出（D13），
        launcher/swarm 两条 spawn 路径一致。"""
        return legacy_agent_id_for_role(role_id)

    async def _controller(self, ctx: PipelineContext) -> DagController | None:
        mode = ctx.settings.orchestration_mode
        if mode.value == "standard":
            return None
        agent = ctx.agent
        if agent.role_id == "supervisor":
            # 真实督导 agent 不持有 DagController：督导通知永不指向自身
            # （杜绝自我复核循环），其工具结果不进 on_tool_finished（督导读
            # 证据不产生 review），stop 也不进入 Coordinator 的 delivery 门禁
            # （督导的结束以信箱为准，计划 §2/§6）。督导的 dag_* 裁决工具
            # 自带 store/engine 访问，不经此控制器。
            return None
        controller = self._controllers.get(agent.id)
        if controller is None or controller.mode.value != mode.value:
            # 同步 SQLite init 必须卸载出事件循环线程（护栏告警/死锁根因）
            db = await asyncio.to_thread(lambda: ConversationDB(agent.project_id).init())
            controller = DagController(
                db,
                agent.id,
                mode,
                conversation_id=agent.project_id,
                working_directory=ctx.workspace_dir,
                agent_id=self._legacy_agent_id(agent.role_id),
                role_id=agent.role_id,
                core=self._core,
            )
            self._controllers[agent.id] = controller
        return controller

    async def audit_run_end(
        self,
        ctx: PipelineContext,
        *,
        explicit_stop: bool,
        stop_arguments: dict[str, Any] | None = None,
    ):
        """统一结束门禁的 DAG 判定（runner 收尾前调用一次）。

        角色分流（§6）：只有 Coordinator（legacy a-0）进入项目交付覆盖门禁；
        研究子 agent 的结束以其自身任务/角色约束为准，不强加项目覆盖——
        其 stop 大多是"挂起等父 agent"而非交付。Supervisor 经 ``_controller``
        返回 None 天然不进此门禁。

        隐式最终回复（无 tool_calls）的 disposition 由确定性覆盖率推导：覆盖
        通过按 complete 审计、不通过按 partial——既不默认 complete，也不再
        无条件登记 unaudited partial（该捷径已删除）。
        """
        controller = await self._controller(ctx)
        if controller is None:
            return None
        if self._legacy_agent_id(ctx.agent.role_id) != "a-0":
            return None
        await controller.initialize()
        if explicit_stop:
            args = stop_arguments or {}
            # 缺省与 stop 工具 schema 对齐（default="complete"）：runner 传的是
            # 原始调用参数，pydantic 默认值不会生效，缺省必须在这里补齐——
            # 缺省即声明 complete 并进入完成审计；要 partial 必须显式声明。
            disposition = str(args.get("delivery_disposition") or "complete")
            return await controller.audit_stop(
                disposition,
                user_stop_event_id=args.get("user_stop_event_id"),
            )
        report = await asyncio.to_thread(controller.delivery_report)
        disposition = "complete" if report.complete else "partial"
        return await controller.audit_stop(disposition)

    async def on_run_end(self, agent, *, explicit_stop: bool) -> None:
        controller = self._controllers.get(agent.id)
        if controller is None or self._core is None:
            return
        events = await asyncio.to_thread(self._core.event_log.query_session, agent.id,
            types={'agent.completion_gate'}, limit=1)
        if events and events[-1].data.get('action') == 'allow_final':
            await controller.commit_stop()

    @staticmethod
    def _apply_delivery_delta(ctx: PipelineContext, result: ToolResult, finished) -> None:
        line = None
        if finished is not None:
            summary_fn = getattr(finished, "summary_line", None)
            if callable(summary_fn):
                line = summary_fn()
        if not line:
            return
        combined = f"{result.summary}\n{line}".strip() if result.summary else line
        object.__setattr__(result, "summary", combined)
        notices = getattr(ctx, "notices", None)
        if notices is not None:
            notices.push(ctx.agent.id, line)

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        controller = await self._controller(ctx)
        if controller is None:
            return PolicyResult.allow()
        await controller.initialize()
        disposition = await controller.check_substantive_gate(call.name, call.arguments)
        if disposition is None:
            return PolicyResult.allow()
        kind, message = disposition
        if kind == "block":
            ctx.emit("dag.gate_blocked", {"gate": self.name, "message": message, "tool": call.name})
            return PolicyResult.block(message)
        if kind == "warn":
            ctx.emit("agent.warning", {"code": "dag.gate.warn", "message": message})
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        if (ctx.agent.role_id == 'supervisor' and self._core is not None
                and call.name in {'write', 'edit'}
                and result.is_success and result.data.get('is_written')
                and Path(result.data.get('filepath') or '') == Path('PROCESS.md')):
            from cloudra.runtime_v2.notices import RESEARCH_OBSERVATION_PIN_KEY

            if self._core.notices.pin_is_consumed(ctx.agent.id, RESEARCH_OBSERVATION_PIN_KEY):
                self._core.notices.unpin(ctx.agent.id, RESEARCH_OBSERVATION_PIN_KEY)
        if ctx.agent.role_id == "supervisor":
            # 督导裁决落库后非轮询投递裁决通知（durable 行 + pin + mailbox +
            # 条件 wake，cancelled 不复活）：结构化裁决 dag_review_evidence、
            # per-call 裁决 dag_review_call、草稿裁决 dag_accept_mechanism
            # 三类共用同一条 flush 通道。
            if (
                call.name
                in {
                    "dag_review_evidence",
                    "dag_review_call",
                    "dag_review_species",
                    "dag_review_step",
                    "dag_accept_mechanism",
                }
                and self._core is not None
            ):
                from cloudra.runtime_v2.supervision import flush_review_notifications

                await flush_review_notifications(self._core, ctx.agent.project_id)
            return
        controller = await self._controller(ctx)
        if controller is None:
            return
        payload = {**(result.data or {}), "is_success": result.is_success}
        finished = await controller.on_tool_finished(
            call.id,
            call.name,
            call.arguments,
            payload,
        )
        self._apply_delivery_delta(ctx, result, finished)
        changed = Path(result.data.get('filepath') or '')
        if (self._core is not None and ctx.settings.orchestration_mode.value == 'dag_guided'
                and call.name in {'write', 'edit'} and result.is_success
                and result.data.get('is_written') and changed.parent == Path('.')
                and changed.suffix.lower() == '.md'):
            from cloudra.runtime_v2.supervision import notify_supervisor

            try:
                await notify_supervisor(self._core, ctx.agent.project_id, reason=f'Research notes updated: {changed.name}')
            except Exception:
                # Notebook maintenance must not turn a completed research action into a failure.
                logger.warning('Could not notify Supervisor about %s', changed.name, exc_info=True)
        if self._core is not None and call.name in {'dag_remove_node', 'dag_remove_edge'}:
            from cloudra.runtime_v2.supervision import flush_review_notifications
            await flush_review_notifications(self._core, ctx.agent.project_id)

    async def before_llm(self, ctx: PipelineContext, messages: list[dict[str, Any]]) -> None:
        controller = await self._controller(ctx)
        notices = getattr(ctx, "notices", None)
        if controller is None:
            if notices is not None:
                notices.unpin(ctx.agent.id, "dag")
            return
        projection = await controller.prompt_projection()
        if notices is not None:
            if projection:
                notices.pin(ctx.agent.id, "dag", projection)
            else:
                notices.unpin(ctx.agent.id, "dag")
            return
        if projection:
            messages.append({"role": "system", "content": projection})
