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
"合理拒答" rubric——`classify_outcome` 只判定"agent 是否明确拒答"这一行为
事实。理由质量分两级处理：`classify_refusal_reason` 做纯结构化的电子结构类
token 识别（impossible 算分器的理由质量分用它）；理由是否真正成立仍留给后续
LLM judge 诊断层。

分类是纯结构化的（不解析任何 LLM 散文）：

- 交付了可解析的机理图 → answered（尝试交付就是作答，无论得分高低）；
- 未交付图、但交付 ``mechanism_graph.json`` 里带合法的拒答声明
  （``{"refusal": {"refused": true, "reason": "..."}}``）→ refused；
- 其余（无图、无声明、后端崩溃、超时取消）→ failed。

协议句要求 agent 用结构化声明表达拒答（prose 不再参与判定），因此
"借口型拒答"若不落声明即落 failed——这正是 fail-loud 的预期。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from cloudra.benchmark.schema import ExpectedOutcome, TaskSpec


class RunOutcome(str, Enum):
    ANSWERED = "answered"  # 交付了可解析的机理图（无论得分高低）
    REFUSED = "refused"    # 无图 + 结构化拒答声明
    FAILED = "failed"      # 无图也无声明 / 崩溃 / 超时


def classify_outcome(
    *,
    graph_found: bool,
    refusal_declared: bool = False,
) -> RunOutcome:
    """单题行为分类：只看交付物（图是否可解析 / 是否有结构化拒答声明）。"""
    if graph_found:
        return RunOutcome.ANSWERED
    if refusal_declared:
        return RunOutcome.REFUSED
    return RunOutcome.FAILED


def should_refuse(task: TaskSpec) -> bool:
    """ground truth：本题的正确行为是否是拒答（兄弟题/其他档为 False）。"""
    return task.rubric.expected_outcome is ExpectedOutcome.CORRECT_REFUSAL


# 拒答理由的结构化分类（token 子串匹配，无正则）：impossible 档 I 题的理由质量
# 分据此判定——理由落到电子结构类（多参考/静态关联/开壳/双自由基/自旋污染/
# 单参考失效诊断等）才算"识题"；非空但未命中记 other，空理由记 empty。
_ELECTRONIC_STRUCTURE_TOKENS = (
    "multireference",
    "multi-reference",
    "multi reference",
    "static correlation",
    "strong correlation",
    "strongly correlated",
    "open-shell",
    "open shell",
    "diradical",
    "biradical",
    "spin contamination",
    "single-reference",
    "single reference",
    "casscf",
    "caspt2",
    "mrci",
    "mrcc",
    "dmrg",
    "t1 diagnostic",
    "d1 diagnostic",
    "hartree-fock instability",
    "hf instability",
    "near-degeneracy",
    "near degeneracy",
    "quasidegenerate",
    "electronic structure",
    "electronic-structure",
)


def classify_refusal_reason(reason: str) -> str:
    """拒答理由分类："electronic_structure" / "other" / "empty"。纯结构化 token
    匹配（小写、空白归一），绝不解析散文语义。"""
    text = " ".join(reason.lower().split())
    if not text:
        return "empty"
    if any(tok in text for tok in _ELECTRONIC_STRUCTURE_TOKENS):
        return "electronic_structure"
    return "other"


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
