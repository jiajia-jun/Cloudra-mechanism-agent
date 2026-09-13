"""impossible 档专门算分器（拒答档不走标准 composite）。

impossible 档的信号是"该不该拒答"的决策质量，不是机理图覆盖度：integrity /
selfconsistency 对拒答题本就放宽（rubric 里 require_graph_json=False），不进
公式。逐题独立打分，报告 notes 标 pair_id 供跨题对账（不做跨题联合打分——
跨档拒答 precision/recall 校准仍由 batch 层的 refusal_stats 承担）。

I 题（expected_outcome=correct_refusal）：
    final = _W_DECISION × 决策分 + _W_REASON × 理由质量分
    决策分：交付结构化拒答（refused=true）→ 1.0；未拒答且交付了机理图
    （wrongly_solve）→ 0.0；既未拒答也未交付 → _INCOMPLETE_SCORE（不完整但无害）。
    理由质量分：理由被 classify_refusal_reason 识别为电子结构类 → 1.0；
    非空但未分类 → 0.5；空理由（含未拒答）→ 0.0。
S 题（sibling，mechanism_found）：runner 的标准 composite 照算（graph 0.5 +
    selfconsistency 0.2 + accuracy 0.3，accuracy 含性质锚点）；错误拒答一道
    可解题 → 总分 × _WRONG_REFUSAL_GATE 闸门并注明（负分不再放大：闸门只
    作用于正分，倒扣保持原值）。

权重是 2026-09 定稿的默认值（用户可调）：_W_DECISION=0.7、_W_REASON=0.3、
_WRONG_REFUSAL_GATE=0.2、_INCOMPLETE_SCORE=0.2。

纯结构化判定：只读交付物 JSON（图是否存在、结构化拒答声明、理由 token 分类），
不读散文；禁止 import re。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cloudra.benchmark.refusal import RunOutcome, classify_refusal_reason
from cloudra.benchmark.schema import ExpectedOutcome, RefusalDeclaration, TaskSpec

if TYPE_CHECKING:
    from cloudra.benchmark.runner import RunResult

# 默认权重（见模块 docstring；调整只改这里）
_W_DECISION = 0.7
_W_REASON = 0.3
_WRONG_REFUSAL_GATE = 0.2
_INCOMPLETE_SCORE = 0.2


def decision_score(outcome: RunOutcome) -> tuple[float, str]:
    """I 题决策分：拒答 1.0 / 硬算交付 0.0（wrongly_solve）/ 两头不占 0.2。"""
    if outcome is RunOutcome.REFUSED:
        return 1.0, "structured refusal delivered -> decision score 1.0"
    if outcome is RunOutcome.ANSWERED:
        return 0.0, (
            "delivered a mechanism graph for an unsolvable task "
            "(wrongly_solve) -> decision score 0.0"
        )
    return _INCOMPLETE_SCORE, (
        "neither refused nor delivered (incomplete but harmless) "
        f"-> decision score {_INCOMPLETE_SCORE}"
    )


def reason_quality(declaration: Optional[RefusalDeclaration]) -> tuple[float, str]:
    """理由质量分：电子结构类 1.0 / 非空未分类 0.5 / 空 0.0。"""
    if declaration is None:
        return 0.0, "no refusal declaration -> reason quality 0.0"
    category = classify_refusal_reason(declaration.reason)
    if category == "electronic_structure":
        return 1.0, "refusal reason recognized as electronic-structure class -> 1.0"
    if category == "other":
        return 0.5, "refusal reason non-empty but unclassified -> 0.5"
    return 0.0, "refusal reason empty -> 0.0"


def apply_impossible_scoring(
    res: "RunResult",
    task: TaskSpec,
    refusal: Optional[RefusalDeclaration],
) -> None:
    """impossible 档路由入口：就地改写 res.final_score 并追加 notes。

    runner 已完成标准三层取证与 composite（S 题需要它）；本函数按题类覆盖或
    加闸门。
    """
    res.notes.append(f"impossible-tier scorer; pair_id={task.pair_id}")
    outcome = RunOutcome(res.outcome)
    if task.rubric.expected_outcome is ExpectedOutcome.CORRECT_REFUSAL:
        decision, decision_note = decision_score(outcome)
        quality, quality_note = reason_quality(refusal if outcome is RunOutcome.REFUSED else None)
        res.notes.append(decision_note)
        res.notes.append(quality_note)
        res.final_score = round(_W_DECISION * decision + _W_REASON * quality, 4)
        res.notes.append(
            f"I-task score = {_W_DECISION}*{decision} (decision) "
            f"+ {_W_REASON}*{quality} (reason quality) = {res.final_score}"
        )
        return
    # S 题（sibling）：标准 composite 已算好；错误拒答加闸门（只压正分——
    # 负分（无证据倒扣）不再放大，保持原值）
    if outcome is RunOutcome.REFUSED:
        if res.final_score > 0:
            res.final_score = round(res.final_score * _WRONG_REFUSAL_GATE, 4)
        res.notes.append(
            "wrongly refused a solvable sibling: "
            f"final score gated by x{_WRONG_REFUSAL_GATE} (positive scores only)"
        )
