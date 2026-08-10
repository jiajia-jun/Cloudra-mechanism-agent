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
- 不向 Coordinator 上下文注入自由文本建议；
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

from cloudra.agent import Agent
from cloudra.config import get_config
from cloudra.dag.models import OrchestrationMode
from cloudra.llm_client import LLMClient

logger = logging.getLogger("Supervisor")


def _load_supervisor_prompt() -> str:
    """从 prompts/supervisor.md 加载 system prompt。"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "supervisor.md")
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


class GraphSupervisor:
    """SupervisorAgent 的触发驱动器：每次图事件运行一轮 agent 循环。

    上下文由 SupervisorAgent 的 ContextManager 持久化（conversation 级，
    session_id=None），跨触发/session/重启连续；本类与任何调用方都不得
    对其调用 clear_context。
    """

    MAX_ROUNDS = 8

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
            parts.append(f"【Coordinator 机理变更说明】{coordinator_request}")
        parts.append(
            "请用 dag_graph 的 view/delivery_report 查看当前两张图，"
            "仅在确有必要时用 mutate 维护 process DAG；无事可做时直接结束，"
            "不要再调用工具。"
        )
        return "\n".join(parts)

    async def run(
        self,
        trigger: str,
        coordinator_request: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GraphSupervisorResult:
        """追加一条触发消息并运行 Supervisor 的工具循环（至多 MAX_ROUNDS 轮）。"""
        # 惰性导入，避免模块级依赖 tools 包。
        from cloudra.tools.Plantool.dag_graph import DagGraph, DagGraphInput

        agent = self._ensure_agent()
        await agent.update_context(
            {"role": "user", "content": self._trigger_message(trigger, coordinator_request)}
        )
        # DagGraph 只读取 session.id 作为 mutation 的 session 归属。
        session = SimpleNamespace(id=session_id or "supervisor")
        mutations: list[dict] = []
        rounds = 0
        note = ""

        for _ in range(self.MAX_ROUNDS):
            try:
                response = await agent.llm_call()
            except Exception as exc:  # LLM 故障不炸任务：Supervisor 是顾问角色
                logger.warning("[Supervisor] llm_call failed: %s", exc)
                note = f"llm_call failed: {exc}"
                break
            message = response.choices[0].message
            raw_tool_calls = message.tool_calls or []
            tool_calls = [tc.model_dump(exclude_none=True) for tc in raw_tool_calls]
            block = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                block["tool_calls"] = tool_calls
            await agent.update_context(block)
            if not tool_calls:
                break
            rounds += 1
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id")
                name = tool_call.get("function", {}).get("name", "")
                raw_args = tool_call.get("function", {}).get("arguments") or "{}"
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args, strict=False)
                    except json.JSONDecodeError as exc:
                        await agent.update_context({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": f"【系统错误】工具参数解析失败: {exc}",
                        })
                        continue
                else:
                    args = raw_args
                if name != "dag_graph":
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"【系统错误】工具 {name!r} 不可用；你只有 dag_graph。",
                    })
                    continue
                try:
                    input_obj = DagGraphInput(**args)
                except ValueError as exc:
                    await agent.update_context({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"【系统错误】dag_graph 参数校验失败: {exc}",
                    })
                    continue
                output = await DagGraph(subagent=agent).tool_call(input_obj, session)
                payload = output.model_dump(mode="json")
                if input_obj.action == "mutate":
                    mutations.append({
                        "accepted": output.accepted,
                        "rejection_code": output.rejection_code,
                        "revisions": payload.get("result", {}).get("revisions"),
                    })
                await agent.update_context({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(payload, ensure_ascii=False, default=str)[:4000],
                })
        else:
            note = f"reached MAX_ROUNDS ({self.MAX_ROUNDS})"

        return GraphSupervisorResult(
            trigger=trigger,
            rounds=rounds,
            mutations=mutations,
            note=note,
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
                # 跳过 system prompt、supervisor advice、上下文压缩提示
                if content.startswith("[Supervisor]") or "上下文压缩" in content:
                    continue
                events.append(f"Step {idx}: system instruction updated.")
            elif role == "user":
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
