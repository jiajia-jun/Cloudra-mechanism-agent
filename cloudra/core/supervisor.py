"""科学督导 Agent（Supervisor）。

包含两个部分：

1. ``Supervisor``：case-bank 提取（任务结束后的经验沉淀），不干预在线执行。
2. ``SupervisorAgent`` + ``GraphSupervisor``：dag_guided 模式下的图规划 agent。
   它复用 Agent 基类与持久 ContextManager（conversation 级上下文，跨触发、
   跨 session、跨进程重启连续），只持有 ``dag_graph`` 工具：用 view /
   delivery_report 自助读图，用 mutate 维护 process DAG。delivery/机理 DAG
   由 Coordinator 设计，Supervisor 对其只读（engine 按 actor 强制）。

核心设计：
- 不按 ReAct 步数轮询；仅由图事件触发；
- 结束时把结论文本钉进 Coordinator 的 ``[Supervisor]`` 建议（覆盖旧建议）；
  仅当督导跑在 Coordinator 工具循环之外（子 Agent / API）时才 inject_event 唤醒；
- 所有在线影响必须经过 DAG engine 的权限、revision 与无环校验；
- 上下文每次触发不清空，只追加触发消息。
"""

from __future__ import annotations

import json
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    # 仅用于类型注解；运行时在使用点惰性导入。
    import numpy as np

from cloudra.core.agent import Agent
from cloudra.dag.models import OrchestrationMode
from cloudra.infra.config import get_config
from cloudra.infra.llm_client import LLMClient

logger = logging.getLogger("Supervisor")


def _load_supervisor_prompt() -> str:
    """从 prompts/supervisor.md 加载 system prompt。"""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "prompts", "supervisor.md"
    )
    if os.path.exists(prompt_path):
        return open(prompt_path, encoding="utf-8").read()
    return "你是 Cloudra 的科学督导导师。你的职责是监督 AI 研究助手是否在战略方向上走偏。"


SUPERVISOR_SYSTEM_PROMPT = _load_supervisor_prompt()


class TimelineEvent(BaseModel):
    """时间线事件，用于压缩轨迹。"""
    step: int
    timestamp: float
    actor: str  # user / agent / tool
    action_type: str  # think / tool_call / tool_result / user_input
    summary: str  # 一句话摘要
    details: dict = Field(default_factory=dict)


class SupervisorAgent(Agent):
    """dag_guided 下的图规划 agent：只持有 dag_graph 工具，上下文持久。

    权限为 READ|MANAGE（dag_graph 的权限类别为 MANAGE），写安全由 DAG
    engine 按 actor=SUPERVISOR 强制：process DAG 可维护，delivery DAG 只读。
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
        """白名单：只有 dag_graph。读两张图、维护 process DAG 都经它。"""
        return [
            entry
            for entry in super().get_available_tools(tools)
            if entry.tool_name == "dag_graph"
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

    上下文由 SupervisorAgent 的 ContextManager 持久化（conversation 级，
    session_id=None），跨触发/session/重启连续；本类与任何调用方都不得
    对其调用 clear_context。
    """

    # 单次触发不设工具轮次上限：完整 process 排产常要数十次 mutate（每批 1–3 op），
    # 旧 16 轮预算会在只 view 时被切断、图没写完。结束条件是模型不再发
    # tool_calls，或 llm_call 失败；空回复仍强制收尾给 Coordinator。
    # 空回复且无 tool_calls 时连续容忍次数：模型常在 view 后空转一拍，
    # 立刻收尾并禁止工具会把「我将排产」写成正文、图却不变。
    EMPTY_END_GRACE = 3

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
        parts = [f"【图事件触发】{trigger}"]
        if coordinator_request:
            label = (
                "【Coordinator 留言】"
                if trigger == "coordinator_message"
                else "【Coordinator 机理变更说明】"
            )
            parts.append(f"{label}{coordinator_request}")
        if trigger in {"delivery_updated", "coordinator_message", "graph_initialization"}:
            parts.append(
                "排产条件：若 delivery 已有实质机理且 process 仍只有模板 planned "
                "（p_analyze/p_literature/p_skill/p_delivery_design）或非模板计划"
                "尚未覆盖当前缺口，应 mutate 补计算 planned 节点；"
                "若非模板 frontier 已覆盖缺口，可不改图但必须说明理由。"
                "无论是否改图，结束前必须留下给 Coordinator 的结论文本（禁止空回复）。"
            )
        parts.append(
            "请先用 dag_graph(action=view) 读 frontier/blockers/delivery_gaps 投影；"
            "确有必要时再用 graph_kind + node_ids/status_filter 取摘要子图。"
            "需要排产或改流程时用 mutate 维护 process DAG；"
            "先 mutate（若需要）再写结论文本——不要用正文代替 mutate。"
        )
        return "\n".join(parts)

    @staticmethod
    def _view_placeholder(content: str) -> str | None:
        """若 content 是成功的 view 结果，返回过时占位符；否则 None。"""
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("action") != "view":
            return None
        if payload.get("success") is False:
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
            f"【过时视图已折叠】action=view graph_kind={kind} {rev_text}。"
            "图存储是权威；需要细节请重新 view。"
        )

    async def _fold_stale_views(self, agent: SupervisorAgent, keep_tool_call_id: str) -> None:
        """新 view 成功后，把上下文里更早的 view 工具结果折叠成一行占位。

        决策/mutate 记录保留；被折叠的是可随时从权威图存储重取的快照。
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
            await agent._ensure_context_manager().replace(rewritten)

    @staticmethod
    def _fallback_report(
        trigger: str,
        rounds: int,
        mutations: list[dict],
        note: str,
    ) -> str:
        accepted = sum(1 for m in mutations if m.get("accepted"))
        parts = [
            f"Supervisor 本轮结论（{trigger}）：",
            f"工具轮次={rounds}，accepted mutations={accepted}/{len(mutations)}。",
        ]
        if note:
            parts.append(f"note={note}。")
        parts.append(
            "本轮未留下自然语言说明；请查看 process 图变更，"
            "或用 dag_graph(action=message_supervisor) 再沟通。"
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

    async def _publish_report_to_coordinator(
        self, report: str, *, wake_coordinator: bool
    ) -> None:
        """钉住 ``[Supervisor]`` 建议；仅在 Coordinator 可能 waiting 时发唤醒事件。

        Coordinator 自己的 mutate / message_supervisor 路径里 Supervisor 是同步
        await 的，下一轮推理 naturally 能读到钉住的建议——再 inject 会变成
        重复的 ``【supervisor】`` 系统行。子 Agent 或 API（user_replan）触发时
        Coordinator 往往在 waiting，必须 inject_event 才能拉起来。
        """
        if not report.strip():
            return
        from cloudra.persistence.context_manager import ContextManager
        from cloudra.persistence.database import get_database_path

        try:
            cm = ContextManager(
                agent_id="a-0",
                conversation_id=self.conversation_id,
                prompt=None,
                query="",
                session_id=None,
            )
            await cm.set_supervisor_advice(report.strip())
        except Exception as exc:
            logger.warning("[Supervisor] set_supervisor_advice failed: %s", exc)
        if not wake_coordinator:
            return
        try:
            await ContextManager.inject_event(
                conversation_id=self.conversation_id,
                agent_id="a-0",
                event_type="supervisor",
                content=report.strip(),
                db_path=get_database_path(self.conversation_id),
            )
        except Exception as exc:
            logger.warning("[Supervisor] inject_event to coordinator failed: %s", exc)

    async def run(
        self,
        trigger: str,
        coordinator_request: Optional[str] = None,
        session_id: Optional[str] = None,
        event_sink=None,
        wake_coordinator: bool = False,
    ) -> GraphSupervisorResult:
        """追加一条触发消息并运行 Supervisor 的工具循环。

        不设轮次上限：模型不再发 tool_calls（或 llm_call 失败）才结束。
        event_sink：可选异步回调 (event_type, data)，由调用方（DagController）
        把运行过程写进 supervisor 自己的 session 事件流——TUI 选中它的
        session 行时才能看到推理与 dag_graph 调用，否则窗口是空的。

        结束时无论是否改图，都会把结论文本钉进 Coordinator 的 ``[Supervisor]``
        建议；若模型空回复则强制再收尾一次。``wake_coordinator`` 为真时再
        inject_event（子 Agent / API 触发，Coordinator 可能在 waiting）。
        """
        # 惰性导入，避免模块级依赖 tools 包。
        from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

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
        # DagGraph 只读取 session.id 作为 mutation 的 session 归属。
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
                # 模型会把排产计划写成正文（「我将 mutate」），process 图不变。
                empty_streak += 1
                if empty_streak == 1:
                    await agent.update_context({
                        "role": "user",
                        "content": (
                            "【系统提示】空回复不算结束。若 process 仍缺非模板排产，"
                            "现在调用 dag_graph(action=mutate) 写入 planned 节点；"
                            "不要把计划写在正文里代替 mutate。"
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
                        "content": f"【系统错误】工具参数解析失败: {exc.msg}",
                    })
                    continue
                if name != "dag_graph":
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"【系统错误】工具 {name!r} 不可用；你只有 dag_graph。",
                    })
                    continue
                try:
                    input_obj = DagGraphInput(**args)
                except Exception as exc:
                    # Pydantic v2 ValidationError 不是 ValueError；统一回喂便于模型改参。
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": (
                            f"【系统错误】dag_graph 参数校验失败: {exc}。"
                            "mutate 请拆成每批 1–3 个 op，payload 尽量扁平；"
                            "base_revisions/operations 放在工具调用顶层。"
                        ),
                    })
                    continue
                args_summary = json.dumps(args, ensure_ascii=False, default=str)[:300]
                await _emit("tool_started", {"tool": "dag_graph", "arguments": args_summary})
                try:
                    output = await DagGraph(subagent=agent).tool_call(input_obj, session)
                except Exception as exc:
                    # 工具层异常回喂模型让它调整，而不是炸掉整个督导运行——
                    # 否则一次 view/mutate 崩溃就会把 Supervisor session 直接终结。
                    logger.warning(
                        "[Supervisor] dag_graph %s failed: %s", input_obj.action, exc
                    )
                    error_content = f"【系统错误】dag_graph {input_obj.action} 执行失败: {exc}"
                    await _emit("tool_finished", {
                        "tool": "dag_graph",
                        "arguments": args_summary,
                        "result": error_content[:500],
                    })
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": error_content,
                    })
                    continue
                payload = output.model_dump(mode="json")
                if input_obj.action == "mutate":
                    mutations.append({
                        "accepted": output.accepted,
                        "rejection_code": output.rejection_code,
                        "revisions": payload.get("result", {}).get("revisions"),
                    })
                content = json.dumps(payload, ensure_ascii=False, default=str)
                await _emit("tool_finished", {
                    "tool": "dag_graph",
                    "arguments": args_summary,
                    "result": content[:500],
                })
                await agent.update_context({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content,
                })
                if input_obj.action == "view" and output.success:
                    await self._fold_stale_views(agent, tool_call_id)

        if not last_report.strip() and not note.startswith("llm_call failed"):
            last_report = await self._force_text_closing(
                agent,
                prompt=(
                    "【系统提示】你刚才结束时没有留下任何给 Coordinator 的结论文本。"
                    "请用两三句话说明：是否已 mutate 排产/为何未改图、当前 frontier 建议、"
                    "Coordinator 下一步该做什么。这是收尾，不要再调用工具。"
                ),
                emit=_emit,
                fallback=self._fallback_report(trigger, rounds, mutations, note),
            )
        elif not last_report.strip():
            last_report = self._fallback_report(trigger, rounds, mutations, note)

        await self._publish_report_to_coordinator(
            last_report, wake_coordinator=wake_coordinator
        )

        return GraphSupervisorResult(
            trigger=trigger,
            rounds=rounds,
            mutations=mutations,
            note=note,
            report=last_report,
        )


class Supervisor:
    """case-bank 提取器（任务结束后的经验沉淀，不参与在线图规划）。

    Args:
        model: 使用的 LLM 名称。
        base_url: LLM API base URL。
        api_key: LLM API key。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        cfg = get_config()
        # 默认使用 follower 配置，但允许单独指定
        self.model = model or cfg.follower.model
        self.base_url = base_url or cfg.follower.url
        self.api_key = api_key or cfg.follower.key
        # LLM 传输层客户端缓存，供独立的 case extraction 复用。
        self._llm_client: Optional[LLMClient] = None

    def _get_client(self) -> LLMClient:
        """返回缓存的 LLMClient（三级 fallback 由传输层内部处理）。"""
        if self._llm_client is None:
            self._llm_client = LLMClient(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
            )
        return self._llm_client

    def compress_timeline(
        self,
        messages: list[dict],
        max_tokens: int = 3000,
    ) -> str:
        """按时间线压缩最近轨迹为一段话。

        目前采用基于规则的压缩：保留关键角色、工具调用和决策点，
        省略过长的观测内容。后续可替换为 LLM 摘要。
        """
        events: list[str] = []
        for idx, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(part.get("text", "")) for part in content if isinstance(part, dict)
                )
            content = str(content)[:500]  # 单条消息截断

            if role == "system":
                # 跳过 system prompt、supervisor advice、旧版 system 梗概
                if content.startswith("[Supervisor]") or "上下文压缩" in content:
                    continue
                events.append(f"Step {idx}: system instruction updated.")
            elif role == "user":
                if content.startswith("[上下文压缩提示]"):
                    events.append(f"Step {idx}: compaction handoff injected.")
                else:
                    events.append(f"Step {idx}: user said '{content}'.")
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                    events.append(f"Step {idx}: agent decided to call tools: {', '.join(names)}.")
                elif content:
                    events.append(f"Step {idx}: agent reasoned '{content[:240]}...'.")
            elif role == "tool":
                tool_name = msg.get("name", "tool")
                events.append(f"Step {idx}: tool '{tool_name}' returned result.")

        # 只保留最近的事件，避免过长
        summary = " ".join(events[-40:])
        if len(summary) > max_tokens * 4:  # 粗略按 1 token ≈ 4 字符估算
            summary = summary[: max_tokens * 4]
        return summary

    async def embed_text(self, text: str) -> np.ndarray:
        """将文本编码为向量。

        默认使用 OpenAI embedding API。如果未配置，返回零向量（退化 gracefully）。
        """
        # numpy 仅在 embedding/检索路径使用，惰性导入以避免拖慢模块加载。
        import numpy as np

        if not all([self.model, self.base_url, self.api_key]):
            # 未配置时返回零向量，避免阻塞
            return np.zeros(1536, dtype=np.float32)

        try:
            # 注意：base_url 若指向 OpenAI 兼容服务，embedding 模型名可能不同
            # 这里使用 text-embedding-3-small 作为默认值
            response = await self._get_client().embed(
                text[:8000],
                model="text-embedding-3-small",
            )
            vec = np.array(response.data[0].embedding, dtype=np.float32)
            return vec
        except Exception as e:
            logger.warning("[Supervisor] embedding 生成失败，退化为零向量: %s", e)
            return np.zeros(1536, dtype=np.float32)

    def retrieve_relevant_cases(
        self,
        query_vec: np.ndarray,
        cases: list[dict],
        k: int = 3,
    ) -> list[dict]:
        """根据向量内积从 case bank 中检索最相关的 k 个 cases。

        兼容从数据库读取的 embedding（bytes）和内存中的 embedding（list）。
        """
        import numpy as np

        if not cases or np.all(query_vec == 0):
            return []

        scored = []
        for case in cases:
            emb = case.get("embedding")
            if emb is None:
                continue
            # 数据库中 embedding 以 BLOB 存储，需先还原为 numpy 数组
            if isinstance(emb, (bytes, memoryview)):
                try:
                    emb = np.frombuffer(emb, dtype=np.float32)
                except Exception:
                    continue
            case_vec = np.array(emb, dtype=np.float32)
            if case_vec.size == 0 or np.all(case_vec == 0):
                continue
            norm = np.linalg.norm(query_vec) * np.linalg.norm(case_vec)
            sim = float(np.dot(query_vec, case_vec) / norm) if norm > 0 else 0.0
            scored.append((sim, case))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [case for _, case in scored[:k]]

    async def extract_case(self, messages: list[dict]) -> dict:
        """从完整 trajectory 中提取结构化 case。

        Returns:
            包含 task_summary、outcome、outcome_reason、lesson 的字典。
            如果 LLM 调用失败，返回基于规则的兜底结果。
        """
        timeline_summary = self.compress_timeline(messages)

        prompt = (
            "请从以下 AI 助手的任务执行记录中提炼一个结构化经验案例（case）。\n\n"
            "输出必须且只能是一个 JSON 对象，字段如下：\n"
            '- task_summary: 一句话概括任务目标\n'
            '- outcome: "success" | "partial" | "failure"\n'
            '- outcome_reason: 成功或失败的关键原因\n'
            '- lesson: 可复用的经验或教训，供未来类似任务参考\n\n'
            "--- 执行记录 ---\n\n"
            f"{timeline_summary}\n\n"
            "--- JSON ---"
        )

        data, error = await self._get_client().chat_json(
            "你是一个从任务记录中提取经验教训的助手。",
            prompt,
            max_tokens=4096,
            temperature=1.0,
            response_format={"type": "json_object"},
        )
        if error is not None:
            print(f"[Supervisor] 提取 Case JSON 解析失败: {error}")
            return self._fallback_case_data(timeline_summary, error)

        return {
            "task_summary": data.get("task_summary", timeline_summary[:200]),
            "outcome": data.get("outcome", "unknown"),
            "outcome_reason": data.get("outcome_reason", ""),
            "lesson": data.get("lesson", ""),
        }

    def _fallback_case_data(self, timeline_summary: str, exc: Exception) -> dict:
        """extract_case 的 LLM 调用失败时的兜底返回。

        task_summary 置空，让 _persist_case 提前返回、不沉淀残缺 case，
        行为与提取失败不写入 case bank 的设计一致。
        """
        return {
            "task_summary": "",
            "outcome": "unknown",
            "outcome_reason": f"Case 提取 LLM 调用失败: {exc}",
            "lesson": "",
        }

def get_supervisor(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Supervisor:
    """工厂函数，便于从配置创建 Supervisor 实例。"""
    return Supervisor(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
