"""类型化证据事实（contract_version=2）：EvidenceFact 与事实适配器协议。

普通工具结果只是 payload；事实是适配器从结果中抽出的、针对某个检查项
（check）的确定性判断（supports/refutes/inconclusive）。事实不可变：
payload 进 ``dag_evidence_facts`` 后不改写，解析口径演进靠
``adapter_version`` 区分新事实。反证（refutes）照常保存——同一候选的
支持/反证并存，由结论层（requirements）裁决，不在存储层隐藏。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloudra.dag.models import (
    CHECK_VOCABULARY,
    CHECK_VOCABULARY_VERSION,
    GraphRef,
)

# 事实适配器版本：解析口径变化时递增（新事实与旧事实并存，不回写）。
FACT_ADAPTER_VERSION = "1"


class FactSubject(BaseModel):
    """事实作用的主体；固定四键，可为空串（无 target 提示的关键事实待归属）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = ""
    geometry_hash: str = ""
    method_signature: str = ""
    target_hint: str = ""


class EvidenceFact(BaseModel):
    """一条针对某个检查项的确定性事实。

    check 必须属于版本化词表（CHECK_VOCABULARY），不允许自造检查；
    outcome 是 supports/refutes/inconclusive 三态（是否已复核是另一回事，
    复核状态在审查协议层记录）；details 是解析得到的原始事实（如
    n_imag、能量、几何 hash）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(min_length=1)
    check: str
    outcome: Literal["supports", "refutes", "inconclusive"]
    subject: FactSubject = Field(default_factory=FactSubject)
    source_refs: list[GraphRef] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    adapter_version: str = FACT_ADAPTER_VERSION

    @field_validator("check")
    @classmethod
    def _check_in_vocabulary(cls, value: str) -> str:
        if value not in CHECK_VOCABULARY:
            raise ValueError(
                f"unknown check {value!r}; vocabulary v{CHECK_VOCABULARY_VERSION}: "
                f"{sorted(CHECK_VOCABULARY)}"
            )
        return value


def fact_dedup_key(fact: EvidenceFact) -> str:
    """幂等键：同一来源 + 同一实际尝试 + 同一解析版本 ⇒ 同一事实。

    重复解析同一文件（相同 source_refs 与 content_hash）得到相同键而
    去重；一次真实重算（不同来源文件或不同内容 hash）是不同的尝试，
    绝不合并。键不含 fact_id，使调用方无需先查库即可幂等重放。
    """
    identity = {
        "check": fact.check,
        "subject": fact.subject.model_dump(),
        "sources": [
            {"ref_type": ref.ref_type, "ref_id": ref.ref_id, "hash": ref.content_hash}
            for ref in fact.source_refs
        ],
        "details": fact.details,
        "adapter_version": fact.adapter_version,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
