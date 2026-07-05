"""
ChemBench benchmark evaluator — 答案提取与打分模块。

从 Coordinator 的原始输出文本中提取 [ANSWER]...[/ANSWER] 标记内的答案，
并按 ChemBench 的 preferred_score 类型计算分数。

关于 preferred_score 的两种类型：
  - "multiple_choice_grade" : 选择题，比对选项字母集合是否匹配
  - "mae"                   : 数值题，计算预测值与目标值之差的绝对值
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional


# ── 答案提取 ──────────────────────────────────────────────────────────────────

_ANSWER_PATTERN = re.compile(
    r'\[ANSWER\]\s*([^\[\]]+?)\s*\[/ANSWER\]',
    re.DOTALL | re.IGNORECASE,
)

_NUMBER_PATTERN = re.compile(
    r'[-+]?\d+\.?\d*(?:[eE][+-]?\d+)?'
)


# Placeholder answers injected by the prompt template should be ignored.
_ANSWER_IGNORE = {"", "...", "<答案>", "answer", "[答案]", "your answer"}

# Answers longer than this are likely accidental captures across reasoning text.
_ANSWER_MAX_REASONABLE_LEN = 80


def extract_answer(text: str) -> Optional[str]:
    """
    从 Coordinator 输出文本中提取 [ANSWER]...[/ANSWER] 之间的内容。

    如果文本中存在多个标记，优先取最后一个简短、非占位符的答案。
    若最后一个答案过长（通常是跨越大段推理文本的误匹配），则向前回溯
    寻找第一个合理长度的非占位符答案。如果没有找到有效标记，返回 None。
    """
    matches = _ANSWER_PATTERN.findall(text)
    if not matches:
        return None

    def _is_valid(candidate: str) -> bool:
        c = candidate.strip()
        return bool(c) and c.lower() not in _ANSWER_IGNORE and len(c) <= _ANSWER_MAX_REASONABLE_LEN

    # Prefer the last reasonable answer; if the last one is too long (e.g. due to
    # stray [ANSWER] tokens in the prompt/reasoning), fall back to earlier matches.
    for match in reversed(matches):
        if _is_valid(match):
            return match.strip()

    # No reasonable short answer found; still avoid returning a giant block.
    for match in reversed(matches):
        candidate = match.strip()
        if candidate and candidate.lower() not in _ANSWER_IGNORE:
            return candidate[:_ANSWER_MAX_REASONABLE_LEN].strip()

    return None


# ── 评分 ──────────────────────────────────────────────────────────────────────

def score_result(extracted_answer: Optional[str], question: Any) -> dict:
    """
    对提取出的答案进行评分。

    Args:
        extracted_answer: extract_answer() 的返回值，可能为 None。
        question: ChemBench question 对象（dict 或 object 均可）。

    Returns:
        包含如下字段的 dict：
            all_correct          (int)   : 1 = 完全正确，0 = 错误
            multiple_choice_grade (float): MC 题得分（0.0 / 1.0），非 MC 题为 NaN
            mae                  (float): 数值题绝对误差，非数值题为 NaN
            parsed_prediction    (str)  : 模型给出的预测值（用于调试）
            ground_truth         (list) : 标准答案
    """
    preferred_score = _get_field(question, "preferred_score", "")
    
    # 优先从底层 examples 提取真实 target
    targets = []
    examples = _get_field(question, "examples", [])
    if examples and isinstance(examples, list) and isinstance(examples[0], dict):
        example = examples[0]
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
                # 找出得分为 1 的选项对应字母
                for idx, (_, score) in enumerate(target_scores.items()):
                    if score == 1:
                        targets.append(chr(ord('A') + idx))
        elif preferred_score == "mae" and "target" in example:
            targets.append(str(example["target"]))
            
    if not targets:
        # 兼容兜底：如果存在预渲染的 targets 字段
        targets = _get_field(question, "targets", [])

    result = {
        "all_correct":           0,
        "multiple_choice_grade": float("nan"),
        "mae":                   float("nan"),
        "parsed_prediction":     extracted_answer or "",
        "ground_truth":          targets,
    }

    if extracted_answer is None:
        # 没有提取到答案，全部指标为 0 / NaN
        return result

    if preferred_score == "multiple_choice_grade":
        _score_mc(result, extracted_answer, targets)
    elif preferred_score == "mae":
        _score_numerical(result, extracted_answer, targets)

    return result


def _score_mc(result: dict, answer: str, targets: list) -> None:
    """选择题评分：提取字母集合并与标准答案比对。"""
    # 容忍 "A", "A,B", "A B", "(A)" 等格式
    predicted_letters = set(
        c.strip().upper()
        for c in re.split(r'[\s,;，]+', answer)
        if re.match(r'^[A-Za-z]$', c.strip())
    )
    target_letters = set(
        t.strip().upper()
        for t in targets
        if re.match(r'^[A-Za-z]$', t.strip())
    )

    correct = (predicted_letters == target_letters) and len(predicted_letters) > 0
    result["multiple_choice_grade"] = 1.0 if correct else 0.0
    result["all_correct"]           = 1   if correct else 0
    result["parsed_prediction"]     = ",".join(sorted(predicted_letters)) or answer


def _score_numerical(result: dict, answer: str, targets: list) -> None:
    """数值题评分：解析浮点数并计算 MAE。"""
    number_matches = _NUMBER_PATTERN.findall(answer)
    if not number_matches:
        result["mae"] = float("nan")
        return

    try:
        predicted = float(number_matches[0])
    except ValueError:
        return

    if not targets:
        return

    try:
        target = float(targets[0])
    except (ValueError, TypeError):
        return

    mae = abs(predicted - target)
    result["mae"] = mae
    result["parsed_prediction"] = str(predicted)

    # 相对误差 < 5% 视为正确（ChemBench 常用标准，可在 config 中调整）
    if not math.isnan(target) and target != 0:
        result["all_correct"] = 1 if abs(predicted - target) / abs(target) < 0.05 else 0
    else:
        result["all_correct"] = 1 if mae < 1e-6 else 0


from benchmarks.chembench.utils import get_field


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_field(obj: Any, field: str, default: Any) -> Any:
    return get_field(obj, field, default)
