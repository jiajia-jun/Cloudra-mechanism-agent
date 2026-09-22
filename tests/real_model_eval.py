"""可选的真实模型行为评测（评审 5.8 后半条）：**手工运行，不进普通 pytest/CI**。

评审原话：「另设可选的真实模型行为评测，用于比较 prompt/model/protocol 版本，
但不进入要求 API key 的普通 CI。它应记录模型版本、prompt revision、tool catalog
revision 和随机性参数，结果只做趋势分析。任何科学评分阈值仍需用户确认。」

先例：``scripts/smoke_compaction.py``（真实 key、手工运行、不在 tests/ 内、不进
CI）。本模块是它的评测版：入口在 ``scripts/eval_real_model.py``，本模块只提供
可被脚本与单测共同复用的部分。

设计约束：

- **复用同一套 harness**：``tests/agent_scenarios.py`` 的 ``ScenarioHarness``
  （core + store + runner + CommandBus + 默认 PolicyStage + 真实工具执行器）与
  同一批场景「杠杆」；差别只在 provider 与 prompt 装配：
  * fake 路径（自检/取证）：``ScriptedProvider``，零 API key；
  * real 路径（趋势对比）：``cloudra.runtime_v2.adapters.LegacyLLMProvider``
    （仓库既有 OpenAI-compatible 传输层，模型/url/key 读 config 槽位）；
  * 两条路径都装真实 prompt 前缀（``LegacyPromptProvider``），与 api_v2 生产
    装配一致——否则 prompt revision 无从谈起。
- **断言纪律与场景 harness 一致**：只断言事件序列 / 结构化字段 / 状态不变量，
  不断言模型措辞；涉及文字的检查只作 observation 记录（如「最终答复是否含
  fixture token」），供人工做趋势分析。
- **不做科学评分**：结果里只有「通过/失败 + 结构化观测」，任何阈值都留给用户
  确认。
- **评测范围**：五个场景只覆盖通用 Agent 行为；不评价 DAG 的
  ``delivery_targets``、逐文件认可或交付完成依据。

单测见 ``tests/test_real_model_eval.py``：只覆盖 fake 路径与「无 key 拒绝」路径，
绝不要求真实 key。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable
from unittest.mock import patch
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:  # 脚本直跑（非 pytest）时也能 import cloudra/tests
    sys.path.insert(0, str(REPO_ROOT))

from tests.agent_scenarios import (  # noqa: E402  （sys.path 先就位）
    ScenarioHarness,
    ScriptedProvider,
    Step,
)

SCHEMA = "cloudra.real_model_eval/v1"

#: prompt 文本源：对源文件做稳定 sha256（仓库没有 prompt 版本号机制；运行时
#: 的 ``PromptAssembler.prompt_revision`` 是主信号，这里是可追责的补充）。
PROMPT_SOURCE_FILES = (
    "cloudra/runtime/prompt_assembler.py",  # identity/protocol 段装配
    "cloudra/runtime_v2/tool_catalog.py",  # JS 调用协议文本 + 工具声明
)
PROMPT_SOURCE_GLOB = "cloudra/prompts/*.md"

#: tool catalog 源（注册表 / 能力投影 / 线缆 schema / 角色权限）。
TOOL_CATALOG_SOURCE_FILES = (
    "cloudra/tools/registry.py",
    "cloudra/tools/capabilities.py",
    "cloudra/runtime_v2/tool_catalog.py",
    "cloudra/runtime_v2/roles.py",
)


# --------------------------------------------------------------------- 基础工具


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def canonical_sha256(payload: Any) -> str:
    """稳定 JSON 摘要：key 排序 + 紧凑分隔符（跨进程/跨平台同值）。"""
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(dumped.encode('utf-8')).hexdigest()}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_endpoint(url: str) -> dict[str, Any]:
    """endpoint 脱敏：只留 scheme/host/port，丢弃 userinfo、path、query、fragment。

    脱敏是硬要求：key 可能出现在 userinfo 或 query 里，绝不能进结果 JSON。
    """
    raw = (url or "").strip()
    if not raw:
        return {"redacted": "", "scheme": "", "host": ""}
    parts = urlsplit(raw if "//" in raw else f"//{raw}")
    scheme = parts.scheme or ""
    host = parts.hostname or ""
    port = parts.port
    netloc = host
    if port:
        netloc = f"{host}:{port}"
    redacted = f"{scheme}://{netloc}" if scheme and netloc else (netloc or "<unparsable>")
    return {"redacted": redacted, "scheme": scheme, "host": host, "port": port}


_URL_IN_TEXT = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s<>'\"`]+", re.IGNORECASE)
_QUERY_URL_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])[^\s<>'\"`?]*[/:.][^\s<>'\"`?]*"
    r"\?[^\s<>'\"`=]+=[^\s<>'\"`]+"
)
_BEARER_IN_TEXT = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)"
    r"\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_SECRET_FIELD = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)",
    re.IGNORECASE,
)


def _result_secrets() -> tuple[str, ...]:
    from cloudra.infra.config import get_config

    cfg = get_config()
    return tuple(
        sorted({key for key in (cfg.coordinator.key, cfg.follower.key) if key}, key=len, reverse=True)
    )


def _redact_result_text(value: str, secrets: tuple[str, ...]) -> str:
    def hide_url(match: re.Match[str]) -> str:
        try:
            return redact_endpoint(match.group(0))["redacted"]
        except ValueError:
            return "<redacted-url>"

    text = _URL_IN_TEXT.sub(hide_url, value)
    # 无协议头的内部主机名无法可靠解析；见到 URL 式查询赋值就整段脱敏。
    text = _QUERY_URL_TOKEN.sub("<redacted-url>", text)
    text = _BEARER_IN_TEXT.sub("Bearer <redacted>", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    for secret in secrets:
        text = text.replace(secret, "<redacted>")
    return text


def redact_result(document: Any) -> Any:
    """脱敏整个评测结果，包括嵌套的检查、异常和运行观测。"""
    secrets = _result_secrets()

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return _redact_result_text(value, secrets)
        if isinstance(value, dict):
            return {
                key: "<redacted>" if _SECRET_FIELD.fullmatch(str(key)) else walk(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, tuple):
            return tuple(walk(item) for item in value)
        return value

    return walk(document)


def _git(*args: str, root: Path = REPO_ROOT) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception:  # noqa: BLE001 —— 元数据尽力而为，不因缺 git 让评测失败
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _source_hashes(relpaths: Iterable[str], *, root: Path = REPO_ROOT) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in relpaths:
        path = root / rel
        if path.is_file():
            out[rel] = sha256_file(path)
    return out


def prompt_revision_record(root: Path = REPO_ROOT) -> dict[str, Any]:
    """prompt revision：prompt 源文件的稳定 hash（逐文件哈希一起落盘）。"""
    sources = _source_hashes(PROMPT_SOURCE_FILES, root=root)
    for path in sorted((root / "cloudra" / "prompts").glob("*.md")):
        sources[f"cloudra/prompts/{path.name}"] = sha256_file(path)
    return {"sha256": canonical_sha256(sources), "sources": sources}


def tool_catalog_revision_record(root: Path = REPO_ROOT) -> dict[str, Any]:
    """tool catalog revision：工具注册/能力投影/schema 生成/角色权限源文件的稳定 hash。"""
    sources = _source_hashes(TOOL_CATALOG_SOURCE_FILES, root=root)
    return {"sha256": canonical_sha256(sources), "sources": sources}


def wire_tools_sha256(agent: Any) -> str:
    """该 agent 实际「看到」的线缆工具 schema 的稳定 hash（权限隐藏后的形态）。"""
    from cloudra.runtime_v2.tool_catalog import wire_tool_schemas

    try:
        schemas = wire_tool_schemas(agent, agent.capabilities.tools)
    except Exception:  # noqa: BLE001 —— 观测项尽力而为，不拖垮评测
        return ""
    return canonical_sha256(schemas)


# --------------------------------------------------------------------- 前置条件


@dataclass(frozen=True)
class ConfigSlotSummary:
    model: str
    endpoint: dict[str, Any]
    key_set: bool
    timeout: int
    context_window: int
    reasoning_effort: str | None
    native_search: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            "key_set": self.key_set,
            "timeout": self.timeout,
            "context_window": self.context_window,
            "reasoning_effort": self.reasoning_effort,
            "native_search": self.native_search,
        }


def config_slot_summary(*, slot: str = "coordinator") -> ConfigSlotSummary:
    """读当前 config 槽位（coordinator/follower）。绝不返回 key 本身。"""
    from cloudra.infra.config import get_config

    cfg = get_config()
    legacy = cfg.coordinator if slot == "coordinator" else cfg.follower
    return ConfigSlotSummary(
        model=legacy.model,
        endpoint=redact_endpoint(legacy.url),
        key_set=bool(legacy.key),
        timeout=legacy.timeout,
        context_window=legacy.context_window,
        reasoning_effort=legacy.reasoning_effort,
        native_search=legacy.native_search,
    )


def real_run_precondition(*, opt_in: bool, spawns_children: bool = False) -> str | None:
    """真实路径的前置条件：None = 可跑；否则返回「必须显式报错」的原因。

    两条硬规则（评审 5.8：不进需要 key 的普通 CI；不静默跳过）：
    1. 未显式开启（``--confirm-real-api``）→ 拒绝；
    2. 槽位没有 key → 拒绝并给出设置路径，绝不静默降级到 fake。
    """
    if not opt_in:
        return (
            "真实模型评测需要显式开启：加 --confirm-real-api（会产生真实 API 调用与费用）。"
            " 只想验证评测链路本身请用 --provider fake（零 key）。"
        )
    coord = config_slot_summary(slot="coordinator")
    if not coord.key_set:
        return (
            "config 槽位 llm.coordinator.key 为空：拒绝静默跳过/静默降级。"
            " 请通过 config.yaml（cloudra config set coordinator.key ...）或环境变量"
            " COORDINATOR_KEY / CLOUDRA_COORDINATOR_KEY 提供，然后重跑。"
        )
    if not coord.model or not coord.endpoint["redacted"]:
        return "config 槽位缺少 model/url，无法发起真实调用。"
    if spawns_children:
        follower = config_slot_summary(slot="follower")
        if not follower.key_set:
            return (
                "选中的场景会派发子 Agent（走 llm.follower 槽位），但该槽位没有 key："
                " 拒绝部分可跑。请补 follower.key，或去掉 --scenarios 里的派发场景。"
            )
    return None


# ------------------------------------------------------------------ provider 包装


class EvalBudgetExceeded(RuntimeError):
    """单场景 LLM 调用预算耗尽（防真实 key 被无界烧掉）。"""


@dataclass
class ProviderStats:
    calls: int = 0
    failures: int = 0
    errors: list[str] = field(default_factory=list)
    latencies_s: list[float] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "llm_failures": self.failures,
            "errors": self.errors[:5],
            "latency_s_total": round(sum(self.latencies_s), 3),
            "latency_s_max": round(max(self.latencies_s), 3) if self.latencies_s else 0.0,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class BudgetedProvider:
    """provider 装饰器：统计调用/耗时/usage，并限制 complete 尝试次数。

    任何 provider 都能被它包；``__getattr__`` 透传内层可选钩子
    （``resolve_effective_settings`` / ``summarize`` / fake 的 ``call_count``）。
    底层 HTTP 重试与压缩摘要调用不计入这个逻辑调用预算。
    """

    def __init__(self, inner: Any, *, max_calls: int, label: str = "") -> None:
        self._inner = inner
        self.max_calls = int(max_calls)
        self.label = label
        self.stats = ProviderStats()

    def __getattr__(self, name: str) -> Any:  # 只在常规查找失败时触发
        return getattr(self._inner, name)

    @property
    def inner(self) -> Any:
        return self._inner

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None) or {}
        if isinstance(usage, dict):
            self.stats.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.stats.completion_tokens += int(usage.get("completion_tokens") or 0)

    async def complete(self, agent: Any, messages: list[dict[str, Any]], tools: list[str], **kwargs: Any):
        if self.stats.calls >= self.max_calls:
            raise EvalBudgetExceeded(
                f"LLM call budget exhausted ({self.max_calls}) in scenario "
                f"{self.label!r}; refusing further real calls"
            )
        # 预算约束 provider.complete 尝试次数；失败请求也可能已送达远端。
        self.stats.calls += 1
        started = time.monotonic()
        try:
            response = await self._inner.complete(agent, messages, tools, **kwargs)
        except BaseException as exc:  # noqa: BLE001 —— 统计后原样抛出（重试语义归 pipeline）
            self.stats.failures += 1
            self.stats.latencies_s.append(time.monotonic() - started)
            if len(self.stats.errors) < 5:
                self.stats.errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            raise
        self.stats.latencies_s.append(time.monotonic() - started)
        self._record_usage(response)
        return response


def build_fake_provider(spec: "Scenario", *, token: str = "") -> ScriptedProvider:
    """fake 路径 provider：脚本化轨迹，零 key（链路自检 / 单测取证）。"""
    def render(steps: Iterable[Step]) -> list[Step]:
        return [replace(step, text=step.text.replace("{token}", token)) for step in steps]

    return ScriptedProvider(
        by_role={role: render(steps) for role, steps in spec.fake_script.items()},
        default=render(spec.fake_default),
    )


def build_real_provider() -> Any:
    """real 路径 provider：仓库既有 LLM 传输层（OpenAI-compatible，读 config 槽位）。"""
    from cloudra.runtime_v2.adapters import LegacyLLMProvider

    return LegacyLLMProvider()


def build_prompt_provider() -> Any:
    """真实 prompt 装配（与 api_v2/benchmark 生产装配一致）。"""
    from cloudra.runtime_v2.adapters import LegacyPromptProvider

    return LegacyPromptProvider()


# --------------------------------------------------------------------- 检查面


class Checks:
    """只记结构化判定，不抛异常——一条场景里所有不变量都要留下证据。"""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    @property
    def passed(self) -> bool:
        return bool(self.rows) and all(row["ok"] for row in self.rows)


@dataclass
class ScenarioContext:
    spec: "Scenario"
    harness: ScenarioHarness
    agent: Any
    provider: BudgetedProvider
    checks: Checks
    observations: dict[str, Any]

    def completion(self) -> dict[str, Any] | None:
        from cloudra.services.api_v2.views import agent_dict

        try:
            return agent_dict(self.harness.core, self.agent).get("completion")
        except Exception:  # noqa: BLE001
            return None

    def emitted_text(self) -> str:
        return "".join(
            str(event.data.get("content") or "")
            for event in self.harness.events(self.agent)
            if event.type == "agent.message_emitted"
        )

    def tool_rows(self) -> list[dict[str, Any]]:
        return self.harness.tool_events(self.agent)

    def outcomes(self) -> list[Any]:
        return [row["outcome"] for row in self.harness.run_rows(self.agent)]

    def state_transitions(self) -> list[Any]:
        return [
            event.data.get("to")
            for event in self.harness.events(self.agent)
            if event.type == "agent.state_changed"
        ]

    def add_common_observations(self) -> None:
        """结构化观测：只为趋势分析留证据，不做断言。"""
        ctx = self
        self.observations.update(
            {
                "state": ctx.agent.state.value,
                "runs": ctx.harness.run_rows(ctx.agent),
                "tool_calls": [
                    {
                        "tool_name": row["tool_name"],
                        "started": row["started"],
                        "blocked": row["blocked"],
                        "block_stage": row["block_stage"],
                        "is_success": row["is_success"],
                    }
                    for row in ctx.tool_rows()
                ],
                "event_types": ctx.harness.types(ctx.agent),
                "final_message": ctx.emitted_text()[:500],
                "completion": ctx.completion(),
                "prefix_meta": prefix_meta(ctx),
                "wire_tools_sha256": wire_tools_sha256(ctx.agent),
            }
        )


def prefix_meta(ctx: ScenarioContext) -> dict[str, Any]:
    """运行时 prompt/capability revision（仓库既有机制：PromptAssembler 装配元数据）。

    由 ``context.prefix_installed`` 事件承载，与生产链路同一来源。
    """
    for event in ctx.harness.events(ctx.agent):
        if event.type == "context.prefix_installed":
            meta = dict(event.data.get("meta") or {})
            return {
                "prompt_revision": meta.get("prompt_revision"),
                "capability_revision": meta.get("capability_revision"),
                "dynamic_revisions": meta.get("revisions"),
                "prefix_len": meta.get("prefix_len"),
            }
    return {}


# --------------------------------------------------------------------- 场景定义


@dataclass(frozen=True)
class Scenario:
    """一个行为评测场景：真实模型收到同一段指令时，轨迹必须满足的不变量。

    ``fake_script`` 是该场景在 fake 路径下的脚本化轨迹（自检用）；断言与 real
    路径逐字相同——fake 通过证明「检查面 + 链路」本身是通的。
    """

    name: str
    role_id: str
    query: str
    check: Callable[[ScenarioContext], Awaitable[None]]
    protocol: str | None = None  # None = 默认 invocation protocol
    settings: dict[str, Any] = field(default_factory=dict)
    workspace_files: dict[str, str] = field(default_factory=dict)
    fake_script: dict[str, list[Step]] = field(default_factory=dict)
    fake_default: list[Step] = field(default_factory=list)
    spawns_children: bool = False
    timeout_s: float = 180.0
    max_llm_calls: int = 12
    tags: tuple[str, ...] = ()


# --- 1. 普通问答（默认 protocol：纯文本收尾，依据 = declared）


async def _check_plain_qa(ctx: ScenarioContext) -> None:
    outcomes = ctx.outcomes()
    ctx.checks.add("run_succeeded", bool(outcomes) and all(o == "succeeded" for o in outcomes), str(outcomes))
    completion = ctx.completion() or {}
    ctx.checks.add(
        "completion_basis_declared",
        completion.get("completion_basis") == "declared",
        json.dumps(completion, ensure_ascii=False)[:200],
    )
    blocked = [row for row in ctx.tool_rows() if row["blocked"]]
    ctx.checks.add("no_blocked_tools", not blocked, str([row["tool_name"] for row in blocked]))
    ctx.checks.add("provider_called", ctx.provider.stats.calls >= 1, str(ctx.provider.stats.calls))


# --- 2. 工具使用 + 证据读取（traditional protocol）


async def _check_read_token(ctx: ScenarioContext) -> None:
    rows = ctx.tool_rows()
    by_name = {row["tool_name"]: row for row in rows}
    read = by_name.get("read")
    ctx.checks.add("read_tool_requested", read is not None, str([row["tool_name"] for row in rows]))
    if read is not None:
        ctx.checks.add("read_tool_started", read["started"] is True, str(read))
        ctx.checks.add("read_tool_succeeded", read["is_success"] is True, str(read.get("status")))
    outcomes = ctx.outcomes()
    ctx.checks.add("run_succeeded", bool(outcomes) and all(o == "succeeded" for o in outcomes), str(outcomes))
    token = ctx.observations.get("fixture_token") or ""
    mentioned = bool(token) and token in ctx.emitted_text()
    ctx.checks.add("answer_mentions_fixture_token", mentioned, f"token_present={mentioned}")
    blocked = [row for row in rows if row["blocked"]]
    ctx.checks.add("no_blocked_tools", not blocked, str([row["tool_name"] for row in blocked]))


# --- 3. unattended：绝不进入 waiting_input


async def _check_unattended(ctx: ScenarioContext) -> None:
    states = ctx.state_transitions()
    ctx.checks.add("never_waiting_input", "waiting_input" not in states, str(states))
    outcomes = ctx.outcomes()
    ctx.checks.add("run_succeeded", bool(outcomes) and all(o == "succeeded" for o in outcomes), str(outcomes))
    rows = ctx.tool_rows()
    started_direct_controls = [
        row for row in rows if row["tool_name"] == "ask_user" and row["started"]
    ]
    ctx.checks.add("ask_user_never_executed", not started_direct_controls, str(started_direct_controls))
    ctx.observations["ask_user_attempted"] = any(row["tool_name"] == "ask_user" for row in rows)


# --- 4. 子 Agent 派发：恰好一次回传


async def _check_delegation(ctx: ScenarioContext) -> None:
    parent = ctx.agent
    children = ctx.harness.children_of(parent)
    ctx.checks.add("exactly_one_child", len(children) == 1, str([child.id for child in children]))
    ctx.checks.add(
        "child_terminal_succeeded",
        bool(children) and all(child.state.value == "succeeded" for child in children),
        str([child.state.value for child in children]),
    )
    reports = ctx.harness.child_reports(parent)
    ctx.checks.add("exactly_one_completion_report", len(reports) == 1, str(len(reports)))
    outcomes = ctx.outcomes()
    ctx.checks.add("parent_run_succeeded", bool(outcomes) and all(o == "succeeded" for o in outcomes), str(outcomes))
    blocked = [row for row in ctx.tool_rows() if row["blocked"]]
    ctx.checks.add("no_blocked_tools", not blocked, str([row["tool_name"] for row in blocked]))


# --- 5. 重启：不重放副作用、不重复派发


async def _check_restart(ctx: ScenarioContext) -> None:
    rows = ctx.tool_rows()
    writes = [row for row in rows if row["tool_name"] == "todo_write"]
    ctx.checks.add("todo_write_once", len(writes) == 1 and writes[0]["is_success"] is True, str(writes))
    ctx.checks.add(
        "no_duplicate_children",
        len(ctx.harness.children_of(ctx.agent)) == 1,
        str([child.id for child in ctx.harness.children_of(ctx.agent)]),
    )
    outcomes = ctx.outcomes()
    ctx.checks.add("parent_run_succeeded", bool(outcomes) and all(o == "succeeded" for o in outcomes), str(outcomes))


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="plain_qa",
        role_id="coordinator",
        query=(
            "In one short paragraph, explain why the boiling point of n-alkanes increases with chain length. "
            "Answer in prose and finish the task when your answer is complete."
        ),
        check=_check_plain_qa,
        tags=("default_protocol", "completion_gate"),
        fake_script={"coordinator": [Step(text="(fake) alkanes: dispersion forces scale with chain length.")]},
    ),
    Scenario(
        name="read_fixture_token",
        role_id="coordinator",
        protocol="traditional",
        query=(
            "Your working directory contains a file named EVAL_FIXTURE.txt. "
            "Use the `read` tool to read it, then repeat its exact single line back to me in your final message. "
            "Finish the task when you have answered."
        ),
        workspace_files={"EVAL_FIXTURE.txt": "cloudra-real-model-eval-token:{token}\n"},
        check=_check_read_token,
        tags=("tool_use", "evidence_read"),
        fake_script={
            "coordinator": [
                Step(tools=[("read", {"path": "EVAL_FIXTURE.txt"})]),
                Step(text="The file EVAL_FIXTURE.txt contains: cloudra-real-model-eval-token:{token}"),
            ]
        },
    ),
    Scenario(
        name="unattended_never_waits",
        role_id="coordinator",
        protocol="traditional",
        settings={"unattended": True},
        query=(
            "You are running unattended: no human can answer questions. "
            "Decide the solvent for a retro-aldol control run yourself, tell me your choice, "
            "and finish the task. Do not ask the user anything."
        ),
        check=_check_unattended,
        tags=("unattended", "permission_matrix"),
        fake_script={
            "coordinator": [
                Step(tools=[("ask_user", {"question": "Which solvent should I use?"})]),
                Step(text="(fake) proceeding with water as the documented default solvent."),
            ]
        },
    ),
    Scenario(
        name="delegation_report_once",
        role_id="coordinator",
        protocol="traditional",
        query=(
            "Delegate one exploration task: call `subagent_launcher` with agent_id \"a-1\" (explorer), "
            "is_wait=false, asking it to list the files in the working directory and report back. "
            "Then finish your turn with a one-line status."
        ),
        check=_check_delegation,
        spawns_children=True,
        tags=("subagent", "wakeup"),
        fake_script={
            "coordinator": [
                Step(
                    tools=[
                        (
                            "subagent_launcher",
                            {
                                "agent_id": "a-1",
                                "query": "List the files in the working directory and report back.",
                                "is_wait": False,
                            },
                        )
                    ]
                ),
                Step(text="(fake) explorer dispatched; waiting for its report."),
            ],
            "explorer": [Step(text="(fake) workspace inspected: no files.")],
        },
    ),
    Scenario(
        name="restart_no_replay",
        role_id="coordinator",
        protocol="traditional",
        query=(
            "Do exactly two things and then finish: (1) call `todo_write` with one item "
            "{content: \"record the eval step\", status: \"in_progress\"}; "
            "(2) call `subagent_launcher` with agent_id \"a-1\", is_wait=false, asking it to report "
            "that the process restarted cleanly. Finish with a one-line summary."
        ),
        check=_check_restart,
        spawns_children=True,
        tags=("restart", "no_replay"),
        fake_script={
            "coordinator": [
                Step(
                    tools=[
                        ("todo_write", {"todos": [{"content": "record the eval step", "status": "in_progress"}]}),
                        (
                            "subagent_launcher",
                            {
                                "agent_id": "a-1",
                                "query": "Report that the process restarted cleanly.",
                                "is_wait": False,
                            },
                        ),
                    ]
                ),
                Step(text="(fake) step recorded and explorer dispatched."),
            ],
            "explorer": [Step(text="(fake) restart looks clean.")],
        },
    ),
)


def scenario_by_name(name: str) -> Scenario | None:
    for spec in SCENARIOS:
        if spec.name == name:
            return spec
    return None


def select_scenarios(names: Iterable[str] | None) -> list[Scenario]:
    if not names:
        return list(SCENARIOS)
    wanted = [name.strip() for name in names if name and name.strip()]
    unknown = [name for name in wanted if scenario_by_name(name) is None]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(unknown)}")
    return [scenario_by_name(name) for name in wanted]  # type: ignore[misc]


# ------------------------------------------------------------------------ 运行器


def _render_workspace_files(files: dict[str, str], *, token: str) -> dict[str, str]:
    return {name: content.format(token=token) for name, content in files.items()}


def _seed_workspace(workspace_dir: str, files: dict[str, str]) -> dict[str, str]:
    """把 fixture 写进该项目显式指定的评测工作区。"""
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for name, content in files.items():
        target = workspace / name
        target.write_text(content, encoding="utf-8")
        written[name] = str(target)
    return written


@dataclass
class RunOptions:
    provider_kind: str = "fake"
    work_dir: Path = field(default_factory=lambda: REPO_ROOT / "var" / "real_model_eval")
    timeout_s: float = 180.0
    max_llm_calls: int = 12
    max_turn_retries: int = 2
    retry_backoff: tuple[float, ...] = (0.01,)
    temperature: float | None = None
    model: str | None = None
    base_url: str | None = None
    prompt_provider: bool = True
    scenario_names: list[str] | None = None


def _provider_for(spec: Scenario, options: RunOptions, *, token: str = "") -> BudgetedProvider:
    if options.provider_kind == "real":
        inner: Any = build_real_provider()
    else:
        inner = build_fake_provider(spec, token=token)
    return BudgetedProvider(inner, max_calls=options.max_llm_calls, label=spec.name)


async def run_scenario(spec: Scenario, options: RunOptions, *, token: str) -> dict[str, Any]:
    """跑一个场景：真跑一次 Agent 任务，然后逐条核对不变量。"""
    started = time.monotonic()
    result: dict[str, Any] = {
        "name": spec.name,
        "role_id": spec.role_id,
        "protocol": spec.protocol or "default",
        "settings": dict(spec.settings),
        "query": spec.query,
        "tags": list(spec.tags),
        "checks": [],
        "observations": {},
        "error": "",
    }
    checks = Checks()
    provider = _provider_for(spec, options, token=token)
    scenario_dir = (Path(options.work_dir) / "scenarios" / spec.name).resolve()
    scenario_dir.mkdir(parents=True, exist_ok=True)
    harness: ScenarioHarness | None = None
    observations: dict[str, Any] = {"fixture_token": token}
    try:
        harness = await ScenarioHarness.start(
            scenario_dir,
            provider=provider,
            workspace_dir=scenario_dir / "workspace",
            retry_backoff=options.retry_backoff,
            max_turn_retries=options.max_turn_retries,
        )
        if options.prompt_provider:
            # ScenarioHarness 不暴露 prompt_provider 注入点（TurnPipeline 有）：
            # 与 api_v2 生产装配一致地挂上真实 prompt 前缀，prompt revision 才有意义。
            harness.pipeline.prompt_provider = build_prompt_provider()
        files = _render_workspace_files(spec.workspace_files, token=token)
        if files:
            observations["workspace_files"] = _seed_workspace(harness.project.workspace_dir, files)
        settings: dict[str, Any] = dict(spec.settings)
        if options.temperature is not None:
            settings["temperature"] = options.temperature
        if options.model:
            settings["model"] = options.model
        if options.base_url:
            settings["base_url"] = options.base_url
        agent = await harness.spawn(spec.role_id, spec.query, protocol=spec.protocol, **settings)
        ctx = ScenarioContext(
            spec=spec, harness=harness, agent=agent, provider=provider,
            checks=checks, observations=observations,
        )
        try:
            await harness.wait_terminal(agent, timeout=options.timeout_s or spec.timeout_s)
            checks.add("terminal_state_succeeded", agent.state.value == "succeeded", agent.state.value)
        except AssertionError as exc:
            checks.add("terminal_state_reached", False, f"timeout after {options.timeout_s or spec.timeout_s}s: {exc}")
            await _cancel_quietly(harness, agent)
        try:
            await spec.check(ctx)
        except Exception as exc:  # noqa: BLE001 —— 检查器自身异常也是失败证据
            checks.add("checker_ran", False, f"{type(exc).__name__}: {exc}")
        if options.provider_kind == "real":
            await _attach_effective_settings(ctx, observations)
        ctx.add_common_observations()
        if options.provider_kind == "real":
            await _restart_and_audit(spec, options, harness, agent, checks, observations)
    except Exception as exc:  # noqa: BLE001 —— 基建错误（装配/派发）也要落进结果
        checks.add("scenario_completed", False, f"{type(exc).__name__}: {exc}")
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if harness is not None:
            try:
                await harness.aclose()
            except Exception:  # noqa: BLE001
                pass
    result["checks"] = checks.rows
    result["passed"] = checks.passed
    result["duration_s"] = round(time.monotonic() - started, 3)
    result["provider"] = provider.stats.as_dict()
    result["observations"] = observations
    result["budget"] = {
        "max_llm_calls": options.max_llm_calls,
        "counted_calls": "provider.complete_attempts",
        "timeout_s": options.timeout_s,
    }
    return result


async def _cancel_quietly(harness: ScenarioHarness, agent: Any) -> None:
    try:
        await harness.runner.cancel(agent.id)
    except Exception:  # noqa: BLE001
        pass


async def _attach_effective_settings(ctx: ScenarioContext, observations: dict[str, Any]) -> None:
    """记录真实生效的随机性参数（provider 桥接后的值）。"""
    resolver = getattr(ctx.provider, "resolve_effective_settings", None)
    if resolver is None:
        return
    try:
        settings = resolver(ctx.agent)
    except Exception:  # noqa: BLE001
        return
    observations["effective_settings"] = {
        "model": settings.model,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout,
        "context_window": settings.context_window,
        "reasoning_effort": settings.reasoning_effort,
        "native_search": settings.native_search,
    }


async def _restart_and_audit(
    spec: Scenario,
    options: RunOptions,
    harness: ScenarioHarness,
    agent: Any,
    checks: Checks,
    observations: dict[str, Any],
) -> None:
    """重启复核（真实路径）：store 重放不得重放副作用 / 不重复 spawn。

    fake 路径不重复这一步（场景测试已覆盖、且 fake 脚本会写库）。
    """
    if not spec.spawns_children:
        return
    try:
        restored = await ScenarioHarness.restore(
            Path(options.work_dir) / "scenarios" / spec.name,
            provider=_provider_for(spec, options),
        )
    except Exception as exc:  # noqa: BLE001
        checks.add("restart_restored", False, f"{type(exc).__name__}: {exc}")
        return
    try:
        restored_agent = restored.core.agents.get(agent.id)
        checks.add("restart_restored", restored_agent is not None, str(restored_agent is not None))
        if restored_agent is None:
            return
        writes = [row for row in restored.tool_events(restored_agent) if row["tool_name"] == "todo_write"]
        if spec.name == "restart_no_replay":
            checks.add("restart_no_replay_todo_write", len(writes) == 1, str(len(writes)))
        observations["restored_children"] = [child.id for child in restored.children_of(restored_agent)]
        observations["restored_state"] = restored_agent.state.value
    finally:
        try:
            await restored.aclose()
        except Exception:  # noqa: BLE001
            pass


async def run_all(options: RunOptions) -> dict[str, Any]:
    """跑完整套场景，返回可落盘的结果文档。"""
    from cloudra.infra.config import get_config

    token = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    metadata = collect_metadata(options, run_id=run_id)
    results: list[dict[str, Any]] = []
    # 手工脚本没有 pytest 的 data_dir fixture；只在本次评测进程内临时改路径，
    # 让 goal/todo 等工具状态也落在 work_dir，退出时恢复，绝不改用户 YAML。
    eval_data_dir = (Path(options.work_dir) / "data").resolve()
    with patch.object(get_config(), "data_dir", eval_data_dir):
        for spec in select_scenarios(getattr(options, "scenario_names", None)):
            spec_options = RunOptions(**{**options.__dict__, "timeout_s": options.timeout_s or spec.timeout_s,
                                         "max_llm_calls": options.max_llm_calls})
            results.append(await run_scenario(spec, spec_options, token=token))
    passed = [row for row in results if row["passed"]]
    return redact_result({
        "schema": SCHEMA,
        "run_id": run_id,
        "generated_at": utc_now(),
        "provider_kind": options.provider_kind,
        "evaluation_scope": {
            "domain": "generic_agent_behavior",
            "dag_delivery_semantics": "not_evaluated",
        },
        "fixture_token": token,
        "metadata": metadata,
        "scenarios": results,
        "summary": {
            "total": len(results),
            "passed": len(passed),
            "failed": len(results) - len(passed),
            "duration_s": round(sum(row["duration_s"] for row in results), 3),
            "failed_scenarios": [row["name"] for row in results if not row["passed"]],
        },
    })


def collect_metadata(options: RunOptions, *, run_id: str = "") -> dict[str, Any]:
    """结果 JSON 的元数据：模型 / endpoint（脱敏）/ revision / 随机性参数 / 版本。"""
    coord = config_slot_summary(slot="coordinator")
    follower = config_slot_summary(slot="follower")
    return {
        "run_id": run_id,
        "generated_at": utc_now(),
        "provider_kind": options.provider_kind,
        "model": {
            "configured": coord.model,
            "override": options.model,
            "follower_configured": follower.model,
        },
        "endpoint": {
            "coordinator": coord.endpoint,
            "follower": follower.endpoint,
            "override": redact_endpoint(options.base_url) if options.base_url else None,
        },
        "api_key_present": {"coordinator": coord.key_set, "follower": follower.key_set},
        "prompt_revision": prompt_revision_record(),
        "tool_catalog_revision": tool_catalog_revision_record(),
        "randomness": {
            "temperature": options.temperature if options.temperature is not None else "config_slot_default(1.0)",
            "top_p": "config_slot_default(None)",
            "reasoning_effort": coord.reasoning_effort,
            "max_turn_retries": options.max_turn_retries,
            "retry_backoff_s": list(options.retry_backoff),
            "max_llm_calls_per_scenario": options.max_llm_calls,
            "timeout_s_per_scenario": options.timeout_s,
        },
        "harness": {
            "prompt_provider": "LegacyPromptProvider" if options.prompt_provider else None,
            "provider_fake": "ScriptedProvider",
            "provider_real": "cloudra.runtime_v2.adapters.LegacyLLMProvider",
            "scenario_module": "tests/agent_scenarios.py",
        },
        "versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "git_commit": _git("rev-parse", "HEAD"),
            "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain")),
        },
    }


def write_results(document: dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    safe_document = redact_result(document)
    out_path.write_text(json.dumps(safe_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def summarize_lines(document: dict[str, Any]) -> list[str]:
    """终端摘要（人工看趋势用；细节都在 JSON 里）。"""
    document = redact_result(document)
    meta = document["metadata"]
    lines = [
        f"schema={document['schema']} provider={document['provider_kind']} run_id={document['run_id']}",
        "scope=generic agent behavior; DAG delivery semantics not evaluated",
        f"model={meta['model']['configured']!r} endpoint={meta['endpoint']['coordinator']['redacted']!r} "
        f"key_set={meta['api_key_present']['coordinator']}",
        f"prompt_revision={meta['prompt_revision']['sha256'][:23]} "
        f"tool_catalog_revision={meta['tool_catalog_revision']['sha256'][:23]}",
        f"git={meta['versions']['git_commit'][:12] or 'n/a'} dirty={meta['versions']['git_dirty']}",
        "",
    ]
    for row in document["scenarios"]:
        mark = "PASS" if row["passed"] else "FAIL"
        lines.append(f"[{mark}] {row['name']:<24} {row['duration_s']:>7.2f}s llm_calls={row['provider']['llm_calls']}")
        for check in row["checks"]:
            if not check["ok"]:
                lines.append(f"        - {check['name']}: {check['detail']}")
        if row.get("error"):
            lines.append(f"        ! {row['error']}")
    summary = document["summary"]
    lines.append("")
    lines.append(f"{summary['passed']}/{summary['total']} scenarios passed in {summary['duration_s']}s")
    if summary["failed_scenarios"]:
        lines.append(f"failed: {', '.join(summary['failed_scenarios'])}")
    return lines
