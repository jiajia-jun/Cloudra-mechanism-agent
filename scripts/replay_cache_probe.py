"""缓存连续性实测回放驱动（计划 2026-09-13-harness-cache-continuity Task 6）。

对同一固定场景分别在新版（当前工作树）与旧版（``--worktree`` 指向的 HEAD
检出）上跑真实 provider 调用，产出逐请求的原始计量 JSON（线缆消息哈希、
usage 原样字段、TTFT/延迟、轮次边界标记），供报告脚本汇总：

    uv run python scripts/replay_cache_probe.py --version new --output /tmp/new_g1.json
    uv run python scripts/replay_cache_probe.py --version old \
        --worktree .worktrees/head-old --output /tmp/old_g1.json

约定：
- 数据目录隔离到 /tmp 下的临时目录（CLOUDRA_CONFIG_FILE 不动——模型/密钥
  仍取真实用户配置），绝不写真实 data_dir。
- 工具执行本地打桩（两个版本看到逐字节相同的工具结果）；只有 LLM 调用是
  真实的。模型/协议在驱动内钉死（traditional + native_search=off，两版一致）。
- 摘要类请求（旧版 run 收尾 finalize / stop compact、新版 compact）走
  真实模型——摘要调用成本是实测指标的一部分。
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path


def _hash_message(message: dict) -> str:
    canonical = json.dumps(message, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# 驱动级计量槽（模块级，ProbeClient 工厂从模块属性取——兼容 summarize 路径
# 在调用期 import LLMClient 的旧/新实现）。
_SINK: list[dict] = []


class _TTFTStream:
    """包装流式响应：记录首 chunk 到达时间（time-to-first-token）。"""

    def __init__(self, stream, entry: dict, started: float) -> None:
        self._stream = stream
        self._entry = entry
        self._started = started

    def __aiter__(self):
        return self

    async def __anext__(self):
        chunk = await self._stream.__anext__()
        if "ttft_s" not in self._entry:
            self._entry["ttft_s"] = round(time.monotonic() - self._started, 3)
        return chunk

    async def aclose(self):
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()


def _install_probe_client(llm_client_module):
    """把计量 client 装到指定版本的 llm_client 模块上；返回工厂。

    汇总/摘要路径在调用期 ``from cloudra.infra.llm_client import LLMClient``，
    patch 模块属性即可覆盖；主 agent 路径由 LegacyLLMProvider 的
    client_factory 注入同一工厂。
    """

    real_client_cls = llm_client_module.LLMClient

    class ProbeClient(real_client_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._entry: dict | None = None

        def _open_entry(self, kwargs, transport=None):
            entry = {
                "stream": bool(kwargs.get("stream")),
                "model": kwargs.get("model"),
                "max_tokens": kwargs.get("max_tokens"),
                "message_hashes": [
                    _hash_message(m) for m in kwargs.get("messages") or []
                ],
                "message_roles": [
                    str(m.get("role")) for m in kwargs.get("messages") or []
                ],
                "tools_hash": _hash_message(kwargs.get("tools") or []),
            }
            if transport:
                entry["transport"] = transport
            _SINK.append(entry)
            self._entry = entry
            return entry

        async def create_with_retry(self, **kwargs):
            entry = self._open_entry(kwargs)
            started = time.monotonic()
            response = await super().create_with_retry(**kwargs)
            if kwargs.get("stream"):
                return _TTFTStream(response, entry, started)
            entry["latency_s"] = round(time.monotonic() - started, 3)
            return response

        async def create_responses_with_retry(self, **kwargs):
            entry = self._open_entry(kwargs, transport="responses")
            started = time.monotonic()
            response = await super().create_responses_with_retry(**kwargs)
            if kwargs.get("stream"):
                return _TTFTStream(response, entry, started)
            entry["latency_s"] = round(time.monotonic() - started, 3)
            return response

        async def aclose(self):
            # provider 与 summarize 路径都在用完时 aclose：此时 last_usage
            # 已就绪（流式在迭代结束后、非流式在 create 返回时）。每个
            # ProbeClient 恰好对应一条 sink 记录（finalize 等后台摘要请求
            # 与下一轮主请求交错时也不会写错条目）。
            if self._entry is not None:
                self._entry["usage"] = copy.deepcopy(self.last_usage)
            await super().aclose()

    llm_client_module.LLMClient = ProbeClient

    def factory(settings):
        return ProbeClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
        )

    return factory


# ---------------------------------------------------------------------------
# 固定场景（两个版本逐字节相同的输入与工具结果；环境变更由驱动侧执行）
# ---------------------------------------------------------------------------

_SCENARIO = [
    # (标签, 消息内容, 驱动侧环境变更)
    (
        "user-tool-round",
        "Create a file named alpha.txt with the content 'aldol v1' using the "
        "write tool, then confirm in one sentence.",
        None,
    ),
    (
        "user-correction",
        "Correction: use 'aldol v2' instead. Rewrite alpha.txt accordingly, "
        "then confirm in one sentence.",
        "workspace+memory",
    ),
    (
        "schedule-wake-1",
        "[Reminder] Check the current state and report one sentence.",
        "workspace2",
    ),
    (
        "user-pin-push",
        "Reply briefly.",
        "pin+push",
    ),
    (
        "schedule-wake-2",
        "[Reminder] Confirm alpha.txt now says 'aldol v2', one sentence.",
        "unpin",
    ),
    (
        "explicit-compact",
        "Summarize the current state in one sentence and stop.",
        "compact",
    ),
    (
        "user-final",
        "Final one-line status.",
        None,
    ),
]


async def _wait_state(agent, state: str, timeout: float = 180.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.05)


async def _run_scenario(version: str) -> None:
    from cloudra.infra.config import get_config
    from cloudra.persistence.paths import memory_path
    from cloudra.runtime_v2.adapters import LegacyLLMProvider, LegacyPromptProvider
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.policies.base import ToolResult
    from cloudra.runtime_v2.schemas import Command, InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    # 数据目录隔离：真实配置的模型/密钥保留，data_dir 指到临时目录。
    scratch = Path(tempfile.mkdtemp(prefix=f"cache-probe-{version}-"))
    get_config().data_dir = scratch / "data"

    class FakeTools:
        """本地打桩的工具执行：两个版本看到逐字节相同的工具结果。"""

        async def execute(self, agent, call, **_kwargs):
            return ToolResult(
                is_success=True,
                summary=f"tool {call.name} completed with canned result r1",
                data={},
            )

    import cloudra.infra.llm_client as llm_client_module

    client_factory = _install_probe_client(llm_client_module)

    core = RuntimeCore(strict_events=True)
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=LegacyLLMProvider(client_factory=client_factory),
        tools=FakeTools(),
        prompt_provider=LegacyPromptProvider(),
        notices=core.notices,
    )
    core.runner = AgentRunner(core, pipeline, retry_backoff=(0.5,))
    bus = CommandBus(core)
    compacted_seen = 0
    await bus.execute(
        Command(type="project.create", payload={"name": f"cache probe {version}"})
    )
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    agent = result.data
    # 钉死模型/协议/预算：两个版本走同一传输与线缆协议。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    agent.settings.native_search = "off"
    agent.settings.max_tokens = 256

    workspace = Path(project.workspace_dir)
    memory = memory_path(data_dir=get_config().data_dir)

    def _compacted_count() -> int:
        return len(
            [
                e
                for e in core.event_log.query_session(agent.id)
                if e.type == "compaction.finished" and e.data.get("compacted")
            ]
        )

    for label, content, mutation in _SCENARIO:
        # 上一步 run 收尾期发生的 compact（旧版 schedule-stop 自动 compact）：
        # 本步首个主请求是 post-compact 冷启动边界。
        if _compacted_count() > compacted_seen:
            compacted_seen = _compacted_count()
            _SINK.append({"marker": "compact", "detail": "before_step"})
        if mutation == "workspace+memory":
            (workspace / "intermediate_a.txt").write_text(
                "stage A intermediate\n", encoding="utf-8"
            )
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text(
                "# Memory\n\n- Keep cache prefixes stable across turns.\n",
                encoding="utf-8",
            )
        elif mutation == "workspace2":
            (workspace / "intermediate_b.txt").write_text(
                "stage B intermediate\n", encoding="utf-8"
            )
        elif mutation == "pin+push":
            core.notices.pin(
                agent.id,
                "review",
                "[Review policy] keep answers under two sentences",
            )
            core.notices.push(agent.id, "one-shot: mention the word checkpoint once")
        elif mutation == "unpin":
            core.notices.unpin(agent.id, "review")
        elif mutation == "compact":
            # 显式 compact：新版在下一轮次边界应用（pending 跨 run 存活）；
            # 旧版 pending 在 run.started 即过期——这是被实测的旧行为，
            # 报告里如实标注。
            await bus.execute(
                Command(
                    type="agent.compact",
                    target={"session_id": agent.id},
                    payload={"keep_recent": 4},
                )
            )
        step_request_index = len(_SINK) + 1  # 本步首个请求即将落入的位置
        _SINK.append({"marker": "step", "label": label})
        await bus.execute(
            Command(
                type="agent.message",
                target={"session_id": agent.id},
                payload={"content": content},
            )
        )
        await _wait_state(agent, "succeeded")
        # 轮次边界应用的 compact（本步的显式 compact，新版 trigger=manual）
        # 发生在本步首个请求之前：事后确认事件，把边界标记补插到本步请求
        # 之前。旧版 schedule-stop compact（trigger=stop）在 run 收尾才发生，
        # 由下一步开头的 before_step 检查标记。
        if _compacted_count() > compacted_seen:
            finished = [
                e
                for e in core.event_log.query_session(agent.id)
                if e.type == "compaction.finished" and e.data.get("compacted")
            ]
            if finished[-1].data.get("trigger") != "stop":
                compacted_seen = _compacted_count()
                _SINK.insert(
                    step_request_index,
                    {"marker": "compact", "detail": finished[-1].data.get("trigger")},
                )
    # run 收尾的 finalize（旧版真实摘要调用）是后台任务：等它落完。
    runner = core.runner
    for _ in range(200):
        if not runner._background.get(agent.id):
            break
        await asyncio.sleep(0.05)
    await core.runner.cancel_all()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=["old", "new"], required=True)
    parser.add_argument(
        "--worktree",
        default=None,
        help="旧版检出路径（--version old 时必需，插到 sys.path 首位）",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.version == "old":
        if not args.worktree:
            parser.error("--version old requires --worktree")
        sys.path.insert(0, str(Path(args.worktree).resolve()))

    import cloudra  # noqa: F401  — sys.path 调整之后的首次导入

    with open(args.output + ".meta", "w", encoding="utf-8") as fh:
        fh.write(f"cloudra_module={cloudra.__file__}\n")

    asyncio.run(_run_scenario(args.version))

    out = {
        "version": args.version,
        "cloudra_module": cloudra.__file__,
        "requests": [
            {k: v for k, v in entry.items() if k != "started"} for entry in _SINK
        ],
    }
    Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.output} ({len(out['requests'])} requests)")


if __name__ == "__main__":
    main()
