"""科学督导 Agent（Supervisor）。

Supervisor 是一个轻量的元认知模块，不执行工具，不走 ReAct 循环。
它定期审查当前 Agent 的行为轨迹，判断其是否在战略方向上走偏，
并从历史 case bank 中检索最相关的经验作为语料，给出高层次方向建议。

核心设计：
- 单次思维链推理，输出 verdict + advice；
- 直接对接 ContextManager，每 N 轮 reAct 被调用一次；
- 建议被注入到 Agent 上下文中（位于 identity/query 之下，events 之上）。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    # 仅用于类型注解；运行时在使用点惰性导入。
    import numpy as np

from cloudra.config import get_config
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


class SupervisorReview(BaseModel):
    """Supervisor 审查结果。"""
    verdict: str = Field(
        ...,
        description="判断结果：proceed / pause_and_reflect / redirect",
    )
    reasoning: str = Field(
        default="",
        description="思维链：为什么给出这个判断",
    )
    advice: list[str] = Field(
        default_factory=list,
        description="方向性建议，最多 3 条",
    )
    suggested_direction: Optional[str] = Field(
        default=None,
        description="可选：建议转向的大方向",
    )
    relevant_cases: list[str] = Field(
        default_factory=list,
        description="引用的 case id 列表",
    )


class Supervisor:
    """科学督导器。

    Args:
        model: 使用的 LLM 名称。
        base_url: LLM API base URL。
        api_key: LLM API key。
        interval: 每 N 轮 reAct 调用一次 review。
        max_advice_items: 最多输出几条建议。
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        interval: int = 5,
        max_advice_items: int = 3,
    ):
        cfg = get_config()
        # 默认使用 follower 配置，但允许单独指定
        self.model = model or cfg.follower.model
        self.base_url = base_url or cfg.follower.url
        self.api_key = api_key or cfg.follower.key
        self.interval = max(1, interval)
        self.max_advice_items = max(1, max_advice_items)
        # LLM 传输层客户端缓存：review/extract 每 5 步触发一次，避免重复新建连接池
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

    def should_review(self, step: int) -> bool:
        """判断当前轮次是否应该触发审查。"""
        return step > 0 and step % self.interval == 0

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

    def build_prompt(
        self,
        user_goal: str,
        timeline_summary: str,
        cases: list[dict],
        goal_anchor: str = "",
    ) -> str:
        """构造 Supervisor 的调用 prompt。"""
        case_texts = []
        for case in cases:
            case_texts.append(
                f"- Case {case.get('id', 'unknown')}: {case.get('task_summary', '')}\n"
                f"  结果: {case.get('outcome', 'unknown')} — {case.get('outcome_reason', '')}\n"
                f"  教训: {case.get('lesson', '')}"
            )

        cases_block = "\n".join(case_texts) if case_texts else "（暂无相关历史经验）"
        goal_block = (
            f"任务目标锚点（Agent 自行设定，含完成判据，作为主要审查基准）：\n{goal_anchor}\n\n"
            if goal_anchor
            else ""
        )

        prompt = (
            "你是 Cloudra 的科学督导导师。你的职责是监督 AI 研究助手是否在战略方向上走偏。\n"
            "\n"
            "审查原则：\n"
            "1. 不要指出具体语法错误或工具 bug；\n"
            "2. 不要给出逐步操作指令；\n"
            "3. 默认 proceed：只有方向明显偏离目标、或继续下去会浪费大量资源时，\n"
            "   才给出 pause_and_reflect / redirect；拿不准时不要干预。\n"
            "4. 关注助手是否：\n"
            "   - 偏离了目标锚点/用户原始目标；\n"
            "   - 在关键信息缺失时推进高风险步骤；\n"
            "   - 重复做已有现成答案的工作。\n"
            "5. 给出 verdict 和 1-3 条高层次方向建议。\n"
            "\n"
            f"用户原始目标：{user_goal}\n"
            "\n"
            f"{goal_block}"
            f"近期行为时间线：\n{timeline_summary}\n"
            "\n"
            f"相关历史经验：\n{cases_block}\n"
            "\n"
            "请以 JSON 格式输出，字段包括：\n"
            '- verdict: "proceed" | "pause_and_reflect" | "redirect"\n'
            '- reasoning: 简短思维链\n'
            '- advice: 字符串数组，最多 3 条方向建议\n'
            '- suggested_direction: 可选，建议转向的大方向\n'
            '- relevant_cases: 引用的 case id 数组'
        )
        return prompt

    async def review(
        self,
        user_goal: str,
        messages: list[dict],
        cases: Optional[list[dict]] = None,
        goal_anchor: str = "",
    ) -> SupervisorReview:
        """执行一次战略审查。

        Args:
            user_goal: 用户原始目标。
            messages: 当前 Agent 的完整上下文消息列表。
            cases: 可选的 case bank 列表，每个 case 应包含 embedding 字段。
            goal_anchor: Agent 通过 goal_set 设定的目标锚点（含完成判据），
                有锚点时以其为主要审查基准，user_goal 作为背景。

        Returns:
            SupervisorReview 对象。
        """
        timeline_summary = self.compress_timeline(messages)
        query_vec = await self.embed_text(timeline_summary)
        relevant_cases = self.retrieve_relevant_cases(
            query_vec,
            cases or [],
            k=3,
        )

        prompt = self.build_prompt(user_goal, timeline_summary, relevant_cases, goal_anchor=goal_anchor)

        data, error = await self._get_client().chat_json(
            SUPERVISOR_SYSTEM_PROMPT,
            prompt,
            # thinking 模型的思考段会吃掉输出预算，1024 极易截断 JSON
            max_tokens=4096,
            temperature=1.0,
            response_format={"type": "json_object"},
        )
        if error is not None:
            print(f"[Supervisor] 审查调用/解析失败: {error}")
            return SupervisorReview(verdict="proceed", reasoning=f"Supervisor 审查失败: {error}")

        # 限制 advice 数量
        advice = data.get("advice", [])
        if isinstance(advice, str):
            advice = [advice]
        advice = advice[: self.max_advice_items]

        return SupervisorReview(
            verdict=data.get("verdict", "proceed"),
            reasoning=data.get("reasoning", ""),
            advice=advice,
            suggested_direction=data.get("suggested_direction"),
            relevant_cases=[str(c.get("id", "")) for c in relevant_cases],
        )

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

    def format_advice(self, review: SupervisorReview) -> str:
        """把 SupervisorReview 格式化为注入上下文的 system 消息文本。

        注意：不要在文本前加 [Supervisor] 前缀——SUPERVISOR_ADVICE_MARKER
        由 ContextManager.set_supervisor_advice 在包装时统一添加，
        否则最终消息会出现双重 marker（"[Supervisor]\n[Supervisor] ..."）。
        """
        lines = [str(review.reasoning)]
        if review.advice:
            lines.append("方向建议：")
            for idx, item in enumerate(review.advice, 1):
                lines.append(f"{idx}. {item}")
        if review.suggested_direction:
            lines.append(f"建议转向：{review.suggested_direction}")
        return "\n".join(lines)


def get_supervisor(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    interval: int = 5,
) -> Supervisor:
    """工厂函数，便于从配置创建 Supervisor 实例。"""
    return Supervisor(
        model=model,
        base_url=base_url,
        api_key=api_key,
        interval=interval,
    )
