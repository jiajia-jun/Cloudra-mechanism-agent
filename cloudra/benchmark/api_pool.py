"""API endpoint pool for benchmark runs.

Anti-429 for parallel benchmark execution: every LLM call picks a random
endpoint from the pool (spreading load), and if the call still exhausts the
client-level backoff retries with a rate-limit error, the next endpoint takes
over (no repeats within one call).

Scope by design: pool members share the *model* from the agent's settings —
only the transport (base_url / api_key) is pinned per endpoint. Empty fields
fall back to the agent's settings, so a pool can be just a list of extra keys
for the same gateway. Non-429 errors are not retried here: they fail the turn
(the runner's own turn-retry handles transient crashes as before).
"""

from __future__ import annotations

import contextvars
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cloudra.runtime_v2.adapters import LegacyLLMProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Endpoint:
    """One pool member; empty fields fall back to the agent's settings."""

    base_url: str = ""
    api_key: str = ""
    label: str = ""  # 日志用；空则取 base_url

    def display(self) -> str:
        return self.label or self.base_url or "(settings default)"


# 当前调用钉住的端点。contextvars 按 asyncio task / 线程隔离——并行跑题时
# 共享同一个 provider 实例也不会串端点。
_current_endpoint: contextvars.ContextVar[Optional[Endpoint]] = contextvars.ContextVar(
    "benchmark_api_pool_endpoint", default=None
)


def load_endpoints(path: Path | str) -> list[Endpoint]:
    """Load a pool JSON: [{"base_url": ..., "api_key": ..., "label": ...}, ...]."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"api pool file must be a non-empty JSON list: {path}")
    endpoints = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"api pool entry #{i} must be an object: {item!r}")
        endpoints.append(
            Endpoint(
                base_url=str(item.get("base_url") or ""),
                api_key=str(item.get("api_key") or ""),
                label=str(item.get("label") or ""),
            )
        )
    return endpoints


def _is_rate_limit(exc: BaseException) -> bool:
    try:
        import openai
    except Exception:  # pragma: no cover - openai 是核心依赖
        return False
    return isinstance(exc, openai.RateLimitError)


class PooledLLMProvider(LegacyLLMProvider):
    """LegacyLLMProvider whose transport endpoint is pinned per call from a pool."""

    def __init__(self, endpoints: list[Endpoint], *, rng: Any = None) -> None:
        super().__init__()
        self._endpoints = list(endpoints)
        # rng 可注入（测试用固定顺序）；生产默认 Random()
        self._rng = rng if rng is not None else random.Random()

    def _make_client(self, settings):
        ep = _current_endpoint.get()
        if ep is None:
            return super()._make_client(settings)
        from cloudra.infra.llm_client import LLMClient

        return LLMClient(
            api_key=ep.api_key or settings.api_key,
            base_url=ep.base_url or settings.base_url,
            timeout=settings.timeout,
        )

    async def complete(self, agent, messages, tools, on_delta=None):
        if not self._endpoints:
            return await super().complete(agent, messages, tools, on_delta)
        # 每次调用随机洗牌端点顺序：既摊初始负载，又保证 429 时不重复试同一个
        order = self._rng.sample(self._endpoints, k=len(self._endpoints))
        last_exc: Optional[BaseException] = None
        for ep in order:
            token = _current_endpoint.set(ep)
            try:
                return await super().complete(agent, messages, tools, on_delta)
            except BaseException as exc:
                if not _is_rate_limit(exc):
                    raise
                last_exc = exc
                logger.warning("endpoint %s rate-limited (429); trying next", ep.display())
            finally:
                _current_endpoint.reset(token)
        assert last_exc is not None
        raise last_exc
