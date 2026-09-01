"""拒答（refusal）行为分类与跨档 precision/recall 统计。

拒答在全部四档统一记为一等 outcome（answered/refused/failed），与"作答"和
"失败"区分开。ground truth 来自 task.rubric.expected_outcome
（CORRECT_REFUSAL = 应当拒答；其余 = 应当作答）。impossible 档的主指标就是
这个二分类的 precision/recall：

- precision = 拒答中落在"应当拒答"题上的比例
  （在 easy/normal/hard/兄弟题上拒答全是 FP——拒答是跨档干扰量，不是本档专利）
- recall    = "应当拒答"题中被拒答的比例
  （impossible 题上硬算交付一个数是 FN）

"什么都拒"的 agent 会在 easy/normal/hard 上制造大量 FP 拉低 precision——
单看 impossible 档拒答率会被刷分，跨档统计是防刷的唯一手段。

判分哲学（2026-09-01 评审裁决，见 impossible.md 文末"定稿圈定"段）：不内嵌
"合理拒答" rubric——本模块只判定"agent 是否明确拒答"这一行为事实，不评价
拒答理由是否成立；理由质量留给后续 LLM judge 诊断层（先只进报告不进
composite）。

v1 分类是纯确定性启发式：
- 交付了机理图文件（哪怕损坏/零分）→ answered——尝试交付就是作答；
- 无交付且最终消息含明确拒答声明（中英双语，_REFUSAL_RE）→ refused；
- 其余（无交付也无拒答声明、后端崩溃、超时取消）→ failed。
已知局限：模板套话也能过 regex——这正是不能用 rubric 给拒答质量评分的理由，
但对"是否拒答"的行为分类足够；借口型拒答（"工具坏了算不了"）若无明确声明
会落 failed。将来接 judge 时只替换 classify_outcome 的实现，统计层不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from cloudra.benchmark.schema import ExpectedOutcome, TaskSpec


class RunOutcome(str, Enum):
    ANSWERED = "answered"  # 尝试交付（无论得分高低）
    REFUSED = "refused"    # 无交付 + 明确拒答声明
    FAILED = "failed"      # 无交付也无拒答声明 / 崩溃 / 超时


# 明确拒答声明（中英双语）。判定目标是"行为上拒绝了作答"，故意不收
# "multireference"/"CASSCF" 这类理由词——单提理由词不等于拒答，收了会误判
# 正常作答里的方法讨论。
_REFUSAL_RE = re.compile(
    r"(?:"
    r"\bi\s+(?:must|have\s+to|will|would|shall|choose\s+to|decide\s+to|can\s+only)\s+"
    r"(?:refuse|decline|abstain)\b"
    r"|\b(?:refuse|decline|abstain)\s+to\s+(?:report|provide|give|compute|answer|deliver)\b"
    r"|\bcannot\s+(?:in\s+good\s+conscience\s+|responsibly\s+|reliably\s+|credibly\s+)?"
    r"(?:report|provide|give|offer|compute|deliver)\b"
    r"|\bwould\s+not\s+be\s+(?:meaningful|trustworthy|reliable|defensible|responsible)\s+to\s+"
    r"(?:report|give|provide|compute)\b"
    r"|\bnot\s+(?:meaningful|trustworthy|reliable)\s+to\s+(?:report|give|provide)\b"
    r"|\brefrain\s+from\s+(?:reporting|giving|providing|computing)\b"
    r"|\bwill\s+not\s+(?:report|provide|give)\s+a?\s*(?:single-reference\s+)?(?:number|value|barrier|answer)\b"
    r"|科学?拒答|拒绝回答|拒绝(?:给出|报告|提供|计算)"
    r"|不予(?:给出|报告|提供)"
    r"|无法(?:给出|提供|报告)?可信(?:的)?(?:数值|数字|结果|答案|能垒)"
    r"|不能(?:给出|提供|报告)(?:可信|可靠)(?:的)?(?:数值|数字|结果|答案|能垒)"
    r"|不宜(?:给出|报告|提供)(?:数值|数字|结果|能垒)"
    r"|不应(?:给出|报告|提供)(?:该|此|单一参考)?(?:数值|数字|结果|能垒)"
    r")",
    re.IGNORECASE,
)


def classify_outcome(
    *,
    graph_found: bool,
    final_message: str,
    crashed: bool = False,
) -> RunOutcome:
    """单题拒答分类（v1 确定性启发式，语义见模块 docstring）。"""
    if crashed:
        return RunOutcome.FAILED
    if graph_found:
        return RunOutcome.ANSWERED
    if final_message and _REFUSAL_RE.search(final_message):
        return RunOutcome.REFUSED
    return RunOutcome.FAILED


def should_refuse(task: TaskSpec) -> bool:
    """ground truth：本题的正确行为是否是拒答（兄弟题/其他档为 False）。"""
    return task.rubric.expected_outcome is ExpectedOutcome.CORRECT_REFUSAL


@dataclass(frozen=True)
class RefusalStats:
    """拒答二分类的混淆矩阵与派生指标。分母为 0 时指标为 None（展示为 "—"，
    不硬记 0——单档批次里 precision 或 recall 常常无定义）。"""

    tp: int = 0  # 应当拒答 & 被拒答
    fp: int = 0  # 应当作答 & 被拒答
    fn: int = 0  # 应当拒答 & 作答了（含 failed：没拒就是没拒）
    tn: int = 0  # 应当作答 & 作答了

    @property
    def precision(self) -> Optional[float]:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else None

    @property
    def recall(self) -> Optional[float]:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


def refusal_stats(rows: Iterable[tuple[bool, bool]]) -> RefusalStats:
    """从 (should_refuse, refused) 序列统计混淆矩阵。"""
    tp = fp = fn = tn = 0
    for expect_refuse, refused in rows:
        if expect_refuse and refused:
            tp += 1
        elif not expect_refuse and refused:
            fp += 1
        elif expect_refuse and not refused:
            fn += 1
        else:
            tn += 1
    return RefusalStats(tp=tp, fp=fp, fn=fn, tn=tn)
