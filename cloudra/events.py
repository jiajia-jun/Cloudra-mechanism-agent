"""进程内事件通知：用 threading.Event 取代固定间隔轮询，消灭 sleep 循环。"""

# TODO: 所以你还在用愚蠢的轮询对吗？？？我要的是IPC，线程间的通信单独包装一层的意义在哪里？？？
# 需要重写，你可以保留线程事件包装，但是你绝对不能不写进程间通信而是靠轮询数据库来查询其他进程信息。
# 你需要彻底启用session生命周期**状态**在代码中的实际作用，改用事件

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
