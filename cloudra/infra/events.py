"""事件门面：把进程内/进程间事件统一成 subscribe + emit。

旧的 `_TaskNotifier` 线程事件包装已经删除；现在的门面基于 `cloudra.infra.ipc`
Unix domain socket 总线，真正实现了跨进程事件投递，不再靠轮询数据库。
"""

from __future__ import annotations

from cloudra.infra.ipc import (
    ThreadSub,
    aemit,
    emit,
    ensure_listener,
    shutdown_all_listeners,
    shutdown_listener,
    subscribe_async,
    subscribe_thread,
    wait_any,
)

__all__ = [
    "ThreadSub",
    "aemit",
    "emit",
    "ensure_listener",
    "shutdown_all_listeners",
    "shutdown_listener",
    "subscribe_async",
    "subscribe_thread",
    "wait_any",
]
