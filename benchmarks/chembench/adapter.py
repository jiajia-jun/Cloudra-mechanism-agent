"""
ChemBench benchmark runner — adapter 模块。

负责将 ChemBench 的 question 对象转换为 Cloudra 能理解的自然语言任务描述。

为什么不直接用 ChemBench 原始 prompt？
  ChemBench 的 prompt 面向"被动回答"的模型，措辞上倾向于直接问答。
  Cloudra 的 Coordinator 是一个主动规划的 Agent：它会分析任务、可能查资料、
  调用化学工具，最终综合给出答案。因此 query 的措辞应该是"任务描述"而非"考题"，
  同时保留原始内容，让 Coordinator 自行决定是否需要工具辅助。
"""

from __future__ import annotations

import re
from typing import Any

# Coordinator 最终答案必须包含的格式标记（ChemBench 评分依赖此格式）
_ANSWER_FORMAT_INSTRUCTION = (
    "\n\n【格式要求】请将你的最终答案严格包裹在标记内：[ANSWER]<答案>[/ANSWER]\n"
    "对于选择题，答案填写选项字母（如 A 或 A,B）；"
    "对于数值计算题，填写数值（使用英文小数点，不含单位）。\n"
    "整个回答（包括你在调用 stop 结束任务时的 reason 中）必须且仅有一个 [ANSWER]...[/ANSWER] 标记。"
)


def question_to_query(question: Any) -> str:
    """
    将 ChemBench question 对象转换为 Cloudra 任务 query 字符串。

    Args:
        question: ChemBench 的 question 对象（支持 dict 和 object 两种形态）。

    Returns:
        格式化后的任务描述字符串，供 Coordinator 接收。
    """
    # ── 提取原始问题文本 ──────────────────────────────────────────────────────
    user_content = _extract_user_content(question)

    # ── 提取题目元信息，帮助 Coordinator 了解背景 ─────────────────────────────
    preferred_score = _get_field(question, "preferred_score", "")
    keywords        = _get_field(question, "keywords", [])
    description     = _get_field(question, "description", "")
    name            = _get_field(question, "name", "")

    question_type = (
        "多项选择题" if preferred_score == "multiple_choice_grade" else "数值计算题"
    )

    keyword_str = "、".join(keywords[:6]) if keywords else "化学"

    # ── 构建任务描述 ──────────────────────────────────────────────────────────
    parts = [
        f"【化学基准测试任务】{question_type}",
        f"关键词：{keyword_str}",
    ]
    if description:
        parts.append(f"题目背景：{description}")
    parts.append("")
    parts.append(user_content)
    parts.append(_ANSWER_FORMAT_INSTRUCTION)

    return "\n".join(parts)


from benchmarks.chembench.utils import get_field


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_field(question: Any, field: str, default: Any) -> Any:
    return get_field(question, field, default)


def _extract_user_content(question: Any) -> str:
    """
    优先从底层 examples 数据结构中提取题目；兼容原有的 prompts 解析模式。
    """
    # ── 1. 适配官方 Task 对象底层数据结构 ──
    examples = _get_field(question, "examples", [])
    if examples and isinstance(examples, list) and isinstance(examples[0], dict):
        example = examples[0]
        input_text = example.get("input", "").strip()
        
        # 如果是选择题，我们需要自己将 JSON 中的选项映射为 A, B, C, D 字母呈现给 Agent
        preferred_score = _get_field(question, "preferred_score", "")
        if preferred_score == "multiple_choice_grade" and "target_scores" in example:
            target_scores = example["target_scores"]
            # 某些版本的数据把 target_scores 序列化为 JSON 字符串
            if isinstance(target_scores, str):
                try:
                    import json
                    target_scores = json.loads(target_scores)
                except Exception:
                    target_scores = {}
            if isinstance(target_scores, dict):
                options_lines = ["\n\nOptions:"]
                for idx, (option_text, _) in enumerate(target_scores.items()):
                    letter = chr(ord('A') + idx)
                    options_lines.append(f"{letter}. {option_text}")
                input_text += "\n".join(options_lines)
            
        if input_text:
            return input_text

    # ── 2. 兼容兜底：ChemBench 原生渲染后的 prompts 结构 ──
    prompts = _get_field(question, "prompts", {})
    try:
        batch = prompts.get("batch", []) if isinstance(prompts, dict) else []
        messages = batch[0].get("messages", []) if batch else []
        for msg in messages:
            if msg.get("role") == "user":
                return msg.get("content", "").strip()
    except (IndexError, AttributeError, TypeError):
        pass

    # 兜底：直接 str(question)
    return str(question)
