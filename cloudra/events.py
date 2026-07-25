"""进程内事件通知：用 threading.Event 取代固定间隔轮询，消灭 sleep 循环。"""

import threading


class _TaskNotifier:
    """线程安全的事件通知器，供 workers 线程与 asyncio runner 间通信。"""

    def __init__(self):
        self._task_inserted = threading.Event()
        self._compute_inserted = threading.Event()
        self._approval_pending = threading.Event()
        self._lock = threading.Lock()

    # ── set（生产者调用）──────────────────────────────────────────

    def notify_task_inserted(self):
        self._task_inserted.set()

    def notify_compute_inserted(self):
        self._compute_inserted.set()

    def notify_approval_pending(self):
        self._approval_pending.set()

    # ── wait + clear（消费者调用）─────────────────────────────────

    def wait_task(self, timeout: float):
        self._task_inserted.wait(timeout)

    def clear_task(self):
        self._task_inserted.clear()

    def wait_compute(self, timeout: float):
        self._compute_inserted.wait(timeout)

    def clear_compute(self):
        self._compute_inserted.clear()

    def wait_approval(self, timeout: float):
        self._approval_pending.wait(timeout)

    def clear_approval(self):
        self._approval_pending.clear()


notifier = _TaskNotifier()
