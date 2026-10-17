"""场景级 Agent 回归 harness（评审 5.8）。

单测覆盖组件、benchmark 覆盖化学正确性，中间那一层「一次完整 Agent 任务是否按预期
经过 读取指令 → 选择工具 → 等待/唤醒 → 提交证据 → 结束门禁」此前无人守。提示词、
默认 protocol、角色权限任一改动都可能全绿过局部单测却改变真实轨迹。

本模块提供：

- ``ScriptedProvider``：**scripted/fake provider**，按 role 分流、零 API key、
  可脚本化抛错（带 HTTP 状态码语义）与「脚本耗尽即收尾」；
- ``ScenarioHarness``：把 core + store + runner + CommandBus + 默认 8 个 PolicyStage
  与真实工具执行器（``LegacyToolExecutor``）装成一次真实运行，并提供事件/状态查询。

断言纪律（评审验收）：只断言**事件序列、结构化字段与状态不变量**，不断言模型措辞。
每个场景在 docstring 里写明它消费哪些「杠杆」，这样改 prompt / 权限 / protocol /
重试预算 / 压缩阈值时，能直接从红灯场景定位影响面：

| 杠杆 | 受影响的场景 |
| :--- | :--- |
| 默认 invocation protocol | 普通问答（默认协议下的纯文本收尾） |
| Benchmark 方法策略作用域 | 模型看到当前范围；普通项目残留白名单仍能生成用户指定的计算输入 |
| 角色权限矩阵 | small_mol 技能→计算入口、unattended 拒批 |
| 重试预算与 fail-fast 分类 | provider 暂态重试 / 永久 4xx |
| 压缩阈值与摘要 | context overflow |
| 结题门禁 + 编排模式 | dag_guided 证据门与督导裁决、仅修订论证后清除旧拒绝 |
| 停止请求 + 最终答复门禁 | 未放行的候选答复不进入用户消息，放行事件先于最终答复 |
| 消息投递/恢复语义 | 异步子 Agent 回传、重启 |
| 重启后的按需收口 | 用户重新发消息时先关闭旧工具/程序，再进入新回复 |
| 督导反馈通知 + 后台等待 | 只读督导反馈唤醒协调员，消费消息后仍保护运行中的计算 |
| 计算完成通知 + 后台等待 | 高通量仍在运行时消费单个结果，再回到等待状态；配置预算的 TS 终态通知能唤醒并落盘 |
| 工具进度持久化 | 阶段记录落盘失败立即终止 Agent，不重试工具副作用 |
| YOLO 审批结构校验 | 非布尔结论不得写入文件 |
| TS 故障检查点 + 干预预算 | 重复相同 scan 续接保留原故障、不耗尽预算 |
| TS fixture 频率门禁 + 终态事件 | 真实零虚频日志阻止 IRC，重复 resume 保留故障与预算 |
| TS 构象文件修订 | 相对路径绑定工作区；更换结构清除旧绑定并保留同一流程 |
| TS 同结构文件替换 | 复制同一结构后保留映射和初猜声明，无需 Agent 重复填写 |
| TS 结构编号转换 | 内部分子与Agent视图使用同一编号，源文件保持原样，显式新编号只转换一次 |
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.invocation import InvocationService
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    Command,
    InvocationProtocol,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

TERMINAL = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}


@dataclass
class Step:
    """provider 的一步脚本：文本 / 工具调用 / 抛错。"""

    text: str = ""
    tools: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    error: BaseException | None = None
    stop: bool = False
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    wait_for: asyncio.Event | None = None


class ProviderFault(Exception):
    """脚本化的 provider 故障（``status_code`` 决定可重试与否）。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ScriptedProvider:
    """按 role 分流的 scripted provider。脚本耗尽后以纯文本收尾（不再发工具调用）。

    ``calls`` 记录每次调用（role_id + 消息），供断言「重试几次」「是否被调用」。
    ``summary_calls`` 单独计数压缩摘要调用（压缩场景用它替代真实 summarizer）。
    """

    def __init__(
        self,
        *,
        default: Iterable[Step] | None = None,
        by_role: dict[str, Iterable[Step]] | None = None,
    ) -> None:
        self._scripts: dict[str, list[Step]] = {
            role: list(steps) for role, steps in (by_role or {}).items()
        }
        self._default: list[Step] = list(default or [])
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []
        #: tool_call_id 全局递增：同一步/不同步之间的调用 id 必须唯一，
        #: 否则按 id 归并的工具轨迹会把两次调用并成一条（假绿）。
        self._next_tool_call = 0
        self.summary_calls = 0
        self.summary_replies: list[str] = []

    def script(self, role_id: str, *steps: Step) -> "ScriptedProvider":
        self._scripts[role_id] = list(steps)
        return self

    def script_default(self, *steps: Step) -> "ScriptedProvider":
        self._default = list(steps)
        return self

    def call_count(self, role_id: str | None = None) -> int:
        if role_id is None:
            return len(self.calls)
        return sum(1 for role, _ in self.calls if role == role_id)

    async def select_tool_names(self, agent, messages, *, resolved_settings):
        self.selection_calls = getattr(self, 'selection_calls', [])
        self.selection_calls.append((agent.id, messages))
        return LLMResponse(content='[]')

    async def complete(
        self,
        agent: AgentSession,
        messages: list[dict[str, Any]],
        tools: list[str],
        **_kwargs: Any,
    ) -> LLMResponse:
        self.calls.append((agent.role_id, messages))
        steps = self._scripts.get(agent.role_id)
        if steps is None:
            steps = self._default
        if not steps:
            return LLMResponse(content=f"[{agent.role_id} script exhausted]", stop_requested=True)
        step = steps.pop(0)
        if step.wait_for is not None:
            await step.wait_for.wait()
        if step.error is not None:
            raise step.error
        tool_calls: list[ToolCall] = []
        for name, args in step.tools:
            self._next_tool_call += 1
            tool_calls.append(
                ToolCall(id=f"tc_{self._next_tool_call}", name=name, arguments=args)
            )
        return LLMResponse(
            content=step.text,
            tool_calls=tool_calls,
            stop_requested=step.stop,
            reasoning=step.reasoning,
            usage=step.usage,
        )

    async def summarize(self, messages: list[dict[str, Any]]) -> str:
        """供压缩场景替代真实摘要调用。"""
        self.summary_calls += 1
        return self.summary_replies.pop(0) if self.summary_replies else _summary_json(messages)


def _summary_json(messages: list[dict[str, Any]]) -> str:
    """一份合法的最小压缩摘要。

    形状按 ``compaction._JSON_SHAPE_NOTE`` 的九键契约（objective 是单对象、其余
    八个是数组、每项 {text, sources}）；形状不符会让压缩反复重问并最终拒替换，
    场景会以「摘要调用次数」暴露该问题。
    """
    import json

    return json.dumps(
        {
            "objective": {"text": "(scripted summary)", "sources": []},
            "active_requests": [],
            "corrections": [],
            "constraints": [],
            "pending": [],
            "completed": [],
            "failed_attempts": [],
            "evidence": [],
            "next_actions": [],
        },
        ensure_ascii=False,
    )


def ordinary_method_input_steps(source: Path, output: Path) -> list[Step]:
    """普通项目生成不在旧白名单里的方法/基组；无需启动 QM。"""
    return [Step(tools=[("qm_input_writer", {
        "engine": "orca", "source_type": "xyz_file", "source_value": str(source),
        "method": "PBE0", "basis_set": "def2-TZVP", "output_path": str(output),
    })]), Step(stop=True)]


def malformed_shell_steps() -> list[Step]:
    """非法 shell 必须终结为被拦工具调用，后续 Agent 回合仍能继续。"""
    return [
        Step(tools=[("bash", {"command": 'echo "unfinished'})]),
        Step(tools=[("todo_write", {"todos": [{"content": "Recovered after invalid input", "status": "done"}]})]),
        Step(stop=True),
    ]


def pending_stop_answer_step(answer: str) -> Step:
    """带候选答复的部分退出请求；是否展示由真实完成门禁决定。"""
    return Step(tools=[("stop", {"delivery_disposition": "partial", "final_answer": answer})])



def final_delivery_review_steps(review: Step, resume: asyncio.Event, park: asyncio.Event) -> dict[str, list[Step]]:
    """完整交付经最终督导审查，唤醒后重复同一声明；拒绝仍留在研究回合。"""
    return {
        "coordinator": [Step(tools=[("stop", {"delivery_disposition": "complete"})]),
                        Step(wait_for=resume, tools=[("stop", {"delivery_disposition": "complete"})]),
                        Step(wait_for=park)],
        "supervisor": [review, Step(stop=True)],
    }


def confirm_partial_stop_step(release: asyncio.Event) -> Step:
    """督导裁决后确认已提交材料；程序绑定批准与答复，无需模型复制标识。"""
    return Step(wait_for=release, tools=[("stop", {"delivery_disposition": "partial"})])


def compute_result_recovery_steps() -> list[Step]:
    """已完成计算唤醒后处理结果，其他作业继续运行时再次挂起。"""
    return [
        Step(tools=[("todo_write", {"todos": [{"content": "Review completed calculation", "status": "done"}]})]),
        Step(stop=True),
    ]


def budgeted_ts_result_recovery_steps(run_id: str) -> list[Step]:
    """配置预算的 TS 终态通知唤醒后，读取真实回执再结束当前运行。"""
    return [Step(tools=[("ts_inspect", {"run_id": run_id})]), Step(stop=True)]


def supervisor_feedback_recovery_steps() -> list[Step]:
    """协调员收到督导反馈后重新进入一轮，未完成计算仍受结题门禁保护。"""
    return [Step(tools=[("agent_hub", {"action": "browse"})]), Step(stop=True)]


def interrupted_program_fixture(agent: AgentSession) -> list[EventDraft]:
    """崩溃现场：一个已有真实 run 留下尚未结束的程序和已启动的工具。"""
    assert agent.current_run is not None
    program = {"execution_id": "interrupted-program", "outer_tool_call_id": "interrupted-js"}
    tool = {"execution_id": program["execution_id"], "tool_call_id": "interrupted-tool",
            "tool_name": "todo_read"}
    return [EventDraft(kind, "agent", agent.project_id, agent.id, agent.current_run.run_id, data)
            for kind, data in (
                ("program.submitted", program), ("program.started", program),
                ("tool.requested", tool), ("tool.started", tool),
            )]


class ScenarioHarness:
    """一次场景的完整运行时。"""

    def __init__(
        self,
        tmp_path,
        *,
        provider: ScriptedProvider | None = None,
        tools: Any = None,
        retry_backoff: tuple[float, ...] = (0.01,),
        max_turn_retries: int = 2,
        store_name: str = "runtime-v2.db",
        attach_store: bool = True,
    ) -> None:
        self.tmp_path = tmp_path
        self.store = RuntimeStore(tmp_path / store_name)
        self.core = RuntimeCore(strict_events=True)
        if attach_store:
            self.core.store = self.store
        self.provider = provider or ScriptedProvider(default=[Step(text="done", stop=True)])
        self.tools = tools if tools is not None else LegacyToolExecutor(self.core)
        stages = default_stages(self.core)
        invocations = InvocationService(
            event_writer=self.core.event_writer,
            stages=stages,
            tools=self.tools,
            agents=self.core.agents,
        )
        self.pipeline = TurnPipeline(
            event_log=self.core.event_log,
            stages=stages,
            llm=self.provider,
            tools=self.tools,
            event_hub=self.core.event_hub,
            notices=self.core.notices,
            invocations=invocations,
        )
        self.runner = AgentRunner(
            self.core,
            self.pipeline,
            max_turn_retries=max_turn_retries,
            retry_backoff=retry_backoff,
        )
        self.core.runner = self.runner
        self.bus = CommandBus(self.core)
        self.project = None

    @classmethod
    async def start(
        cls, tmp_path, *, workspace_dir: str | Path | None = None, **kwargs: Any
    ) -> "ScenarioHarness":
        harness = await asyncio.to_thread(cls, tmp_path, **kwargs)
        payload = {"name": "scenario"}
        if workspace_dir is not None:
            payload["workspace_dir"] = str(workspace_dir)
        await harness.bus.execute(Command(type="project.create", payload=payload))
        harness.project = next(iter(harness.core.projects.values()))
        return harness

    @classmethod
    async def restore(cls, tmp_path, *, store_name: str = "runtime-v2.db", **kwargs: Any):
        """从已有 store 恢复一个 harness（重启场景）：worker 全停、只重建投影。"""
        from cloudra.runtime_v2.persistence import restore_core

        harness = await asyncio.to_thread(cls, tmp_path, store_name=store_name, **kwargs)
        await asyncio.to_thread(restore_core, harness.core, harness.store)
        harness.project = next(iter(harness.core.projects.values()), None)
        return harness

    # ------------------------------------------------------------------ 操纵

    async def spawn(
        self,
        role_id: str,
        query: str = "go",
        *,
        protocol: InvocationProtocol | str | None = None,
        parent: AgentSession | None = None,
        **settings: Any,
    ) -> AgentSession:
        payload: dict[str, Any] = {"role_id": role_id, "query": query}
        if parent is not None:
            payload["parent_session_id"] = parent.id
        if settings:
            payload["settings"] = settings
        agent = (
            await self.bus.execute(
                Command(
                    type="agent.spawn",
                    target={"project_id": self.project.id},
                    payload=payload,
                )
            )
        ).data
        if protocol is not None:
            # scripted 直调业务工具必须固定 traditional 协议：默认的 javascript
            # 只放行 js_exec + 直接控制类（改默认协议是否影响轨迹，由「默认协议」
            # 场景单独守）。
            agent.settings.invocation_protocol = InvocationProtocol(protocol)
        return agent

    async def wait_terminal(self, agent: AgentSession, timeout: float = 8.0) -> AgentSession:
        await self.wait_for(lambda: agent.state in TERMINAL, f"terminal state of {agent.id}", timeout)
        return agent

    async def wait_for(self, predicate: Callable[[], bool], what: str, timeout: float = 8.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(f"timed out waiting for {what}: {self.describe(agent=None)}")
            await asyncio.sleep(0.01)

    async def settle(self, ticks: int = 5) -> None:
        """让后台任务推进若干 tick（不占真实长等待）。"""
        for _ in range(ticks):
            await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        """停掉 runner 的后台任务，避免悬挂任务告警。"""
        for agent in list(self.core.agents.values()):
            try:
                await self.runner.cancel(agent.id)
            except Exception:  # 关停竞态：场景断言已完成，不再让收尾噪声掩盖结论
                pass

    # ------------------------------------------------------------------ 查询

    def events(self, agent: AgentSession) -> list[Any]:
        return self.core.event_log.query_session(agent.id)

    def types(self, agent: AgentSession) -> list[str]:
        return [event.type for event in self.events(agent)]

    def run_rows(self, agent: AgentSession) -> list[dict[str, Any]]:
        """按 run_id 归并 run.started / run.finished 的结构化字段。"""
        rows: dict[str, dict[str, Any]] = {}
        for event in self.events(agent):
            if event.type == "run.started":
                rows[event.run_id or ""] = {"run_id": event.run_id, "outcome": None}
            elif event.type == "run.finished":
                row = rows.setdefault(event.run_id or "", {"run_id": event.run_id})
                row.update(
                    outcome=event.data.get("outcome"),
                    basis=event.data.get("basis"),
                    failure_kind=event.data.get("failure_kind"),
                )
        return [row for row in rows.values() if row.get("outcome") is not None]

    def tool_events(self, agent: AgentSession) -> list[dict[str, Any]]:
        """工具调用轨迹：按 tool_call_id 归并 requested/started/blocked/finished。

        被策略拦下的调用（如 unattended 拒 ask_user）只有 requested + blocked +
        finished，没有 started——轨迹里必须保留它，否则「没被拦」的断言会假绿。
        """
        rows: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in self.events(agent):
            if not event.type.startswith("tool."):
                continue
            key = str(event.data.get("tool_call_id") or "")
            row = rows.get(key)
            if row is None:
                row = {
                    "tool_call_id": key,
                    "tool_name": event.data.get("tool_name"),
                    "started": False,
                    "blocked": False,
                    "block_stage": None,
                    "is_success": None,
                    "status": None,
                    "effect_state": None,
                    "result_summary": "",
                    "result_data": None,
                }
                rows[key] = row
                order.append(key)
            if event.type == "tool.started":
                row["started"] = True
            elif event.type == "tool.blocked":
                row["blocked"] = True
                row["block_stage"] = event.data.get("stage")
            elif event.type == "tool.finished":
                row["is_success"] = event.data.get("is_success")
                row["status"] = event.data.get("status")
                row["effect_state"] = event.data.get("effect_state")
                row["result_summary"] = event.data.get("result_summary") or ""
            elif event.type == "tool.result_recorded":
                result = event.data.get("result") or {}
                row["result_data"] = result.get("data")
        return [rows[key] for key in order]

    def messages(self, agent: AgentSession) -> list[dict[str, Any]]:
        return [event.data for event in self.events(agent) if event.type == "agent.message_injected"]

    def child_reports(self, agent: AgentSession) -> list[dict[str, Any]]:
        """投递给该 agent 的子 Agent 完成回传（结构化 manifest 在事件里）。"""
        return [
            data
            for data in self.messages(agent)
            if isinstance(data.get("manifest"), dict)
        ]

    def children_of(self, agent: AgentSession) -> list[AgentSession]:
        return [a for a in self.core.agents.values() if a.parent_session_id == agent.id]

    def describe(self, agent: AgentSession | None) -> str:
        if agent is None:
            return "agents=" + str({
                a.id: {
                    "role": a.role_id,
                    "state": a.state.value,
                    "runs": self.run_rows(a),
                    "tools": self.tool_events(a),
                }
                for a in self.core.agents.values()
            })
        return (
            f"agent={agent.id} state={agent.state.value} "
            f"runs={self.run_rows(agent)} tools={self.tool_events(agent)}"
        )


# Names shared by the zero-key TS state-machine regressions.
TS_SCENARIOS = ('ts_prepare_once_auto_complete', 'ts_failed_scan_retry_same_run', 'ts_readonly_inspection',
                'ts_resume_scan_without_freeze', 'ts_d1_atom_binding_native_scan_recovery',
                'ts_conformer_source_revision_same_run', 'ts_same_structure_source_keeps_declarations',
                'ts_source_reorder_keeps_imported_state', 'ts_queued_refinement_revision_same_run',
                'ts_stop_prevents_automatic_progression', 'ts_stopped_attempt_resumes_same_run',
                'ts_file_seed_preoptimization_can_be_removed_after_failure',
                'ts_acknowledged_completion_recovers_without_resume',
                'ts_run_scan_revision_inherits_shared_input_settings')


def d1_component_order_files(workspace: Path) -> tuple[Path, Path]:
    """Isolated 16-atom D1 reactant-order fixture; no live Gold or compute data."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    fragments = []
    for fragment in Chem.GetMolFrags(Chem.MolFromSmiles('C=CC=C.C=C'), asMols=True):
        molecule = Chem.AddHs(fragment)
        if AllChem.EmbedMolecule(molecule, randomSeed=42) != 0:
            raise ValueError('D1 fixture embedding failed')
        fragments.append(molecule)
    combined = Chem.CombineMols(*fragments)
    geometry = Chem.Conformer(combined.GetNumAtoms())
    offset = 0
    for index, molecule in enumerate(fragments):
        for atom in range(molecule.GetNumAtoms()):
            point = molecule.GetConformer().GetAtomPosition(atom)
            geometry.SetAtomPosition(offset + atom, (point.x + (7 if index else 0), point.y, point.z))
        offset += molecule.GetNumAtoms()
    combined.RemoveAllConformers()
    combined.AddConformer(geometry)
    xyz, graph = workspace / 'd1_component_order.xyz', workspace / 'd1_component_order.mol'
    xyz.write_text(Chem.MolToXYZBlock(combined))
    graph.write_text(Chem.MolToMolBlock(combined))
    return xyz, graph


def scope_review_completion_steps() -> list[Step]:
    """Read authoritative delivery, then request completion after scoped re-review."""
    return [Step(tools=[("dag_delivery_report", {})]),
            Step(tools=[("stop", {"delivery_disposition": "complete"})])]

def stale_review_resubmit_steps(ts_file, resubmit, finish, park) -> list[Step]:
    """Real file resubmission after an administrative stale-review notification."""
    return [
        Step(tools=[("dag_submit_step_evidence", {"step_name": "step1", "ts_file": ts_file})]),
        Step(wait_for=park, tools=[('dag_view', {})]),
        Step(tools=[("stop", {"delivery_disposition": "partial"})]),
        Step(wait_for=resubmit, tools=[("dag_submit_step_evidence", {"step_name": "step1", "ts_file": ts_file})]),
        Step(tools=[("dag_delivery_report", {})]),
        Step(wait_for=finish, text="gather missing scientific evidence"),
    ]


def supervisor_stale_file_review_steps(review_id: str) -> list[Step]:
    """Read a removed target's review through the real Supervisor tool, then finish."""
    return [Step(tools=[('dag_view_evidence', {'review_id': review_id})]), Step(stop=True)]
