"""科学督导 Agent（Supervisor）。

``SupervisorAgent`` + ``GraphSupervisor``：dag_guided 模式下的科学督导 agent。
它复用 Agent 基类与 JSONL 消息历史（conversation 级，跨触发、
跨 session、跨进程重启连续），只持有 ``dag_*`` 工具族：用 dag_view /
dag_delivery_report 自助读图，用 dag_accept_mechanism 裁决机理草稿、
dag_review_call 复核每次 delivery 相关调用并绑定阶段。delivery/机理 DAG
由 Coordinator 设计，Supervisor 对其只读（engine 按 actor 强制）；
阶段绑定由 harness 确定性校验后落图。

核心设计：
- 不按 ReAct 步数轮询；仅由图事件触发；
- 结论文本随 ``GraphSupervisorResult.report`` 返回调用方（DagController），
  由它经 runtime_v2 的 NoticeManager pin / agent.message 回投 Coordinator；
- 所有在线影响必须经过 DAG engine 的权限、revision 与无环校验；
- 上下文每次触发不清空，只追加触发消息。
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from cloudra.core.agent import Agent
from cloudra.dag.models import OrchestrationMode
from cloudra.infra.config import get_config
from cloudra.runtime.prompt_assembler import load_role_prompt

logger = logging.getLogger(__name__)


def load_supervisor_prompt() -> str:
    """加载 supervisor 角色 prompt（按 mtime 缓存，改 prompt 文件立即生效）。

    与 PromptAssembler 的每请求 (mtime_ns, size) 重校验一致；文件缺失时
    回退到与当前 delivery-review 角色一致的一句话描述。
    """
    try:
        return load_role_prompt("supervisor")
    except FileNotFoundError:
        return (
            "You are Cloudra's graph-planning Supervisor in dag_guided mode: "
            "review the Coordinator's delivery mechanism DAG (read-only for you) — "
            "adjudicate mechanism drafts and evidence call reviews — "
            "using only the dag_* tool family."
        )


class SupervisorAgent(Agent):
    """dag_guided 下的科学督导 agent：只持有 dag_* 工具族，上下文持久。

    权限为 READ|MANAGE（dag_* 工具的权限类别为 MANAGE），写安全由 DAG
    engine 按 actor=SUPERVISOR 强制：delivery DAG 只读，可裁决机理草稿、
    复核调用并绑定阶段、加严 coverage contract。
    """

    id: str = "supervisor"
    name: str = "supervisor"
    type: str = "supervisor"

    model: Optional[str] = None
    llm_site: Optional[str] = None
    _api_key: Optional[str] = None
    temperature: float = 1.0
    max_tokens: int = 8192
    context_window: Optional[int] = None

    prompt_name: Optional[str] = "supervisor"
    query: str = ""
    is_stream: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        cfg = get_config().follower
        self.model = self.model or cfg.model
        self.llm_site = self.llm_site or cfg.url
        self._api_key = self._api_key or cfg.key
        self.context_window = self.context_window or cfg.context_window

    def has_read_permission(self) -> bool:
        return True

    def has_manage_permission(self) -> bool:
        return True

    def get_available_tools(self, tools: Optional[list] = None) -> list:
        """白名单：所有 dag_* 工具。读 delivery 图、裁决草稿与复核都经它们。"""
        return [
            entry
            for entry in super().get_available_tools(tools)
            if entry.tool_name.startswith("dag_")
        ]


class GraphSupervisorResult(BaseModel):
    """一次 Supervisor 触发的结构化结果。"""

    model_config = ConfigDict(frozen=True)

    trigger: str
    rounds: int = 0
    mutations: list[dict] = Field(default_factory=list)
    note: str = ""
    report: str = ""


class GraphSupervisor:
    """SupervisorAgent 的触发驱动器：每次图事件运行一轮 agent 循环。

    上下文由 SupervisorAgent 的 JSONL 消息历史持久化（conversation 级，
    session_id=None），跨触发/session/重启连续；本类与任何调用方都不得
    对其调用 clear_context。
    """

    # 单次触发不设工具轮次上限：一轮复核常要数十次读图/裁决调用，
    # 旧 16 轮预算会在只 view 时被切断。结束条件是模型不再发
    # tool_calls，或 llm_call 失败；空回复仍强制收尾给 Coordinator。
    # 空回复且无 tool_calls 时连续容忍次数：模型常在 view 后空转一拍，
    # 立刻收尾并禁止工具会把「我将接受草稿」写成正文、图却不变。
    EMPTY_END_GRACE = 3
    _WRITE_DAG_TOOLS = frozenset({
        "dag_add_species",
        "dag_add_step",
        "dag_update_delivery_element",
        "dag_remove_edge",
        "dag_set_coverage_contract",
        "dag_accept_mechanism",
        "dag_review_call",
    })

    def __init__(
        self,
        *,
        conversation_id: str,
        working_directory: Optional[str] = None,
    ):
        self.conversation_id = conversation_id
        self.working_directory = working_directory
        self._agent: Optional[SupervisorAgent] = None

    def _ensure_agent(self) -> SupervisorAgent:
        if self._agent is None:
            self._agent = SupervisorAgent(
                conversation_id=self.conversation_id,
                working_directory=self.working_directory,
                orchestration_mode=OrchestrationMode.DAG_GUIDED,
                session_id=None,
            )
        return self._agent

    @staticmethod
    def _trigger_message(trigger: str, coordinator_request: Optional[str]) -> str:
        parts = [f"[Graph event]{trigger}"]
        if coordinator_request:
            label = {
                "coordinator_message": "[Coordinator message]",
                "mechanism_proposed": "[Mechanism proposal rationale]",
                "tool_call_review": "[Pending call reviews]",
            }.get(trigger, "[Coordinator mechanism-change note]")
            parts.append(f"{label}{coordinator_request}")
        if trigger == "mechanism_proposed":
            parts.append(
                "Review the draft: species/steps coverage, per-element stage contracts "
                "(list order is the bind order), and the rationale. Accept with "
                "dag_accept_mechanism only if the mechanism and contracts are sound — "
                "acceptance unlocks compute; otherwise reject with a concrete reason so "
                "the Coordinator can revise."
            )
        elif trigger == "tool_call_review":
            parts.append(
                "Adjudicate each pending review with dag_review_call (target element + stage "
                "+ verdict): agree only when the evidence truly supports that stage — a "
                "ts_guess result is advisory and never supports ts_opt/frequency, and a TS "
                "frequency stage needs exactly one imaginary frequency. disagree means the "
                "stage is still owed (it is NOT a disposal); skip with a reason only when "
                "the stage is deliberately abandoned; not_applicable with a reason when the "
                "stage slot does not apply to this element at all (e.g. a barrierless step has "
                "no ts_opt/frequency, a unimolecular step has no endpoint_b complex); ignore "
                "calls that are not delivery evidence."
            )
        parts.append(
            "First call dag_view to read the delivery projection and coverage gaps; fetch a "
            "subgraph with graph_kind=delivery + node_ids only if needed. Whether or not you "
            "change anything, leave a conclusion for the Coordinator before ending "
            "(empty replies are forbidden)."
        )
        return "\n".join(parts)

    @staticmethod
    def _view_placeholder(content: str) -> str | None:
        """若 content 是成功的 view 结果，返回过时占位符；否则 None。"""
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("action") not in {"view", "dag_view"}:
            return None
        if payload.get("is_success") is False:
            return None
        result = payload.get("result") or {}
        kind = result.get("graph_kind") or "projection"
        revision = result.get("revision")
        revisions = result.get("revisions")
        if revision is not None:
            rev_text = f"revision={revision}"
        elif isinstance(revisions, dict):
            rev_text = f"revisions={revisions}"
        else:
            rev_text = "revision=?"
        return (
            f"[Stale view folded] action=view graph_kind={kind} {rev_text}. "
            "The graph store is authoritative; call view again if you need details."
        )

    async def _fold_stale_views(self, agent: SupervisorAgent, keep_tool_call_id: str) -> None:
        """新 view 成功后，把上下文里更早的 view 工具结果折叠成一行占位。

        决策/写图记录保留；被折叠的是可随时从权威图存储重取的快照。
        """
        context = await agent.get_context()
        changed = False
        rewritten: list = []
        for block in context:
            if (
                isinstance(block, dict)
                and block.get("role") == "tool"
                and block.get("tool_call_id") != keep_tool_call_id
            ):
                placeholder = self._view_placeholder(str(block.get("content") or ""))
                if placeholder is not None and block.get("content") != placeholder:
                    block = {**block, "content": placeholder}
                    changed = True
            rewritten.append(block)
        if changed:
            await agent._ensure_message_history().replace(rewritten)

    @staticmethod
    def _fallback_report(
        trigger: str,
        rounds: int,
        mutations: list[dict],
        note: str,
    ) -> str:
        accepted = sum(1 for m in mutations if m.get("accepted"))
        parts = [
            f"Supervisor conclusion this turn ({trigger}): ",
            f"tool rounds={rounds}, accepted mutations={accepted}/{len(mutations)}. ",
        ]
        if note:
            parts.append(f"note={note}. ")
        parts.append(
            "This turn left no natural-language note; inspect the delivery "
            "projection with dag_view, or use dag_message_supervisor to "
            "communicate again."
        )
        return "".join(parts)

    async def _force_text_closing(
        self,
        agent: SupervisorAgent,
        *,
        prompt: str,
        emit,
        fallback: str,
    ) -> str:
        """强制一次仅文本收尾（丢弃 tool_calls）。"""
        await agent.update_context({"role": "user", "content": prompt})
        try:
            response = await agent.llm_call()
            closing = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("[Supervisor] force-closing llm_call failed: %s", exc)
            closing = ""
        text = closing or fallback
        await agent.update_context({"role": "assistant", "content": text})
        if text:
            await emit("llm_chunk", {
                "stream": "content",
                "delta": text,
                "agent_id": "supervisor",
                "agent_name": "supervisor",
            })
            await emit("llm_stream_end", {})
        return text

    async def run(
        self,
        trigger: str,
        coordinator_request: Optional[str] = None,
        session_id: Optional[str] = None,
        event_sink=None,
    ) -> GraphSupervisorResult:
        """追加一条触发消息并运行 Supervisor 的工具循环。

        不设轮次上限：模型不再发 tool_calls（或 llm_call 失败）才结束。
        event_sink：可选异步回调 (event_type, data)，由调用方（DagController）
        把运行过程写进 supervisor 自己的 session 事件流——TUI 选中它的
        session 行时才能看到推理与 dag_* 工具调用，否则窗口是空的。

        结束时无论是否改图，结论文本都随 ``GraphSupervisorResult.report``
        返回；若模型空回复则强制再收尾一次。报告的投递（NoticeManager
        pin / agent.message 唤醒）由调用方 DagController 负责——它持有
        runtime_v2 的 core 句柄与触发者身份。
        """
        # 惰性导入，避免模块级依赖 tools 包。
        from cloudra.tools import get_tools_lst

        dag_tools = {
            entry.tool_name: entry
            for entry in get_tools_lst()
            if entry.tool_name.startswith("dag_")
        }

        async def _emit(event_type: str, data: dict) -> None:
            if event_sink is None:
                return
            try:
                await event_sink(event_type, data)
            except Exception:  # 展示通道故障不影响督导本身
                logger.debug("[Supervisor] event emit failed: %s", event_type)

        agent = self._ensure_agent()
        trigger_message = self._trigger_message(trigger, coordinator_request)
        await agent.update_context(
            {"role": "user", "content": trigger_message}
        )
        await _emit("user_message", {"content": trigger_message})
        # DAG 写工具只读取 session.id 作为 mutation 的 session 归属。
        session = SimpleNamespace(id=session_id or "supervisor")
        mutations: list[dict] = []
        rounds = 0
        note = ""
        last_report = ""
        empty_streak = 0

        while True:
            try:
                response = await agent.llm_call()
            except Exception as exc:  # LLM 故障不炸任务：Supervisor 是顾问角色
                logger.warning("[Supervisor] llm_call failed: %s", exc)
                note = f"llm_call failed: {exc}"
                break
            message = response.choices[0].message
            raw_tool_calls = message.tool_calls or []
            tool_calls = [tc.model_dump(exclude_none=True) for tc in raw_tool_calls]
            content_text = (message.content or "").strip()
            block = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                block["tool_calls"] = tool_calls
            await agent.update_context(block)
            if content_text:
                last_report = content_text
                await _emit("llm_chunk", {
                    "stream": "content",
                    "delta": message.content,
                    "agent_id": "supervisor",
                    "agent_name": "supervisor",
                })
                await _emit("llm_stream_end", {})
            if not tool_calls:
                if content_text:
                    last_report = content_text
                    break
                # 空回复 + 无工具：不算结束。立刻强制收尾并禁止工具，
                # 否则模型会把复核结论写成正文（「我将接受草稿」），图不变。
                empty_streak += 1
                if empty_streak == 1:
                    await agent.update_context({
                        "role": "user",
                        "content": (
                            "[System] An empty reply does not end the turn. "
                            "If a draft awaits your verdict or reviews are still pending, "
                            "call dag_accept_mechanism / dag_review_call now; "
                            "do not put the verdict in prose instead of the tool call."
                        ),
                    })
                if empty_streak >= self.EMPTY_END_GRACE:
                    break
                continue
            empty_streak = 0
            rounds += 1
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id")
                name = tool_call.get("function", {}).get("name", "")
                raw_args = tool_call.get("function", {}).get("arguments") or "{}"
                try:
                    from cloudra.infra.json_args import loads_tool_arguments

                    args = loads_tool_arguments(raw_args)
                except json.JSONDecodeError as exc:
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"[System error] Failed to parse tool arguments: {exc.msg}",
                    })
                    continue
                entry = dag_tools.get(name)
                if entry is None:
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": (
                            f"[System error] Tool {name!r} is not available; "
                            "you only have dag_* tools."
                        ),
                    })
                    continue
                try:
                    input_obj = entry.input_schema(**args)
                except Exception as exc:
                    # Pydantic v2 ValidationError 不是 ValueError；统一回喂便于模型改参。
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": (
                            f"[System error] {name} argument validation failed: {exc}. "
                            "Use this tool's flat fields; do not send a mutate operations array."
                        ),
                    })
                    continue
                args_summary = json.dumps(args, ensure_ascii=False, default=str)
                await _emit("tool_started", {"tool": name, "arguments": args_summary})
                try:
                    output = await entry.instantiate(subagent=agent).tool_call(
                        input_obj, session
                    )
                except Exception as exc:
                    # 工具层异常回喂模型让它调整，而不是炸掉整个督导运行——
                    # 否则一次 dag_view / dag_review_call 崩溃就会把 Supervisor session 直接终结。
                    logger.warning("[Supervisor] %s failed: %s", name, exc)
                    error_content = f"[System error] {name} failed: {exc}"
                    await _emit("tool_finished", {
                        "tool": name,
                        "arguments": args_summary,
                        "result": error_content,
                    })
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": error_content,
                    })
                    continue
                payload = output.model_dump(mode="json")
                if name in self._WRITE_DAG_TOOLS and output.accepted is not None:
                    mutations.append({
                        "accepted": output.accepted,
                        "rejection_code": output.rejection_code,
                        "revisions": payload.get("result", {}).get("revisions"),
                    })
                content = json.dumps(payload, ensure_ascii=False, default=str)
                await _emit("tool_finished", {
                    "tool": name,
                    "arguments": args_summary,
                    "result": content,
                })
                await agent.update_context({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                })
                action = payload.get("action")
                if (
                    output.is_success
                    and (name == "dag_view" or action in {"view", "dag_view"})
                ):
                    await self._fold_stale_views(agent, tool_call_id)

        if not last_report.strip() and not note.startswith("llm_call failed"):
            last_report = await self._force_text_closing(
                agent,
                prompt=(
                    "[System] You ended without leaving any conclusion text for the Coordinator. "
                    "In two or three sentences, say which reviews you adjudicated / why no stage "
                    "bind was made, and what the Coordinator should do next. This is a closing "
                    "turn; do not call tools."
                ),
                emit=_emit,
                fallback=self._fallback_report(trigger, rounds, mutations, note),
            )
        elif not last_report.strip():
            last_report = self._fallback_report(trigger, rounds, mutations, note)

        return GraphSupervisorResult(
            trigger=trigger,
            rounds=rounds,
            mutations=mutations,
            note=note,
            report=last_report,
        )

