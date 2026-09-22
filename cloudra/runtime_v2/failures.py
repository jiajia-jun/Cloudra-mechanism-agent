"""失败分类（评审 5.10）：``run.finished.failure_kind`` 的唯一转换点。

- ``is_retryable``：一个异常是否值得就地重试（同一输入上会同样失败的 4xx 不值得）；
- ``classify_failure``：异常 → 有限枚举，供 UI、遥测与恢复提示分流。

分类只看**结构化信号**（异常类型、``status_code`` 属性、异常的来源包），绝不解析
异常文本或 Agent 输出；LLM SDK 不进内核，provider 判定一律走属性探针。
"""

from __future__ import annotations

from enum import Enum

from cloudra.runtime_v2.event_writer import EventPersistenceError


class RunFailureKind(str, Enum):
    """run 失败的有限分类。

    新增取值必须同时给出 UI 的下一步说明（前端 ``failureKind.ts``），否则用户只
    会看到一条没有出路的报错。``error`` 文本仍随事件保留，只供人阅读。

    注：评审列出的 ``policy_terminal`` 目前没有任何生产者——被策略拦下的调用是
    工具级 block（run 继续），不是 run 级终态，所以不预先加一个死取值。
    """

    PROVIDER_TRANSIENT_EXHAUSTED = "provider_transient_exhausted"
    PROVIDER_PERMANENT = "provider_permanent"
    EVENT_PERSISTENCE = "event_persistence"
    PIPELINE_INTERNAL = "pipeline_internal"
    COMPLETION_NO_PROGRESS = "completion_no_progress"
    RUNTIME_INTERRUPTED = "runtime_interrupted"


# provider / 传输层的已知包：这些异常既没有 status_code，也不是内核 bug。
_PROVIDER_MODULES = frozenset({"openai", "httpx", "httpcore", "requests", "aiohttp", "urllib3"})


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status


def is_retryable(exc: Exception) -> bool:
    """Only transient failures are worth an in-place retry.

    HTTP 4xx (bad key, insufficient balance, invalid request) will fail again on
    every retry — fail fast instead of burning the retry budget.  408/429 and
    5xx / connection errors stay retryable.  Event persistence failures never
    retry: the event stream and the world may have diverged, so replaying the
    turn could repeat an unaudited effect.
    """
    if isinstance(exc, EventPersistenceError):
        return False
    status = _status_code(exc)
    if status is not None and 400 <= status < 500 and status not in (408, 429):
        return False
    return True


def classify_failure(exc: BaseException) -> RunFailureKind:
    """异常 → 有限枚举。所有调用点共用这一处，不许各自拼字符串判定。

    - 事件落盘失败 → ``event_persistence``（不可重试）
    - provider 的 4xx（非 408/429）→ ``provider_permanent``（重试无用）
    - 其它 provider / 传输层错误 → ``provider_transient_exhausted``（只有重试
      预算耗尽，才会带着可重试错误走到收尾）
    - 其余 → ``pipeline_internal``（harness 自身的问题，不是 provider 也不是
      科学结论失败）
    """
    if isinstance(exc, EventPersistenceError):
        return RunFailureKind.EVENT_PERSISTENCE
    if _is_provider_error(exc):
        if is_retryable(exc):
            return RunFailureKind.PROVIDER_TRANSIENT_EXHAUSTED
        return RunFailureKind.PROVIDER_PERMANENT
    return RunFailureKind.PIPELINE_INTERNAL


def _is_provider_error(exc: BaseException) -> bool:
    if _status_code(exc) is not None:
        return True
    module = (type(exc).__module__ or "").split(".", 1)[0]
    return module in _PROVIDER_MODULES
