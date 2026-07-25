"""Cloudra 任务执行入口（薄封装，实际逻辑在 cloudra.runtime）。"""

from cloudra.runtime.runner import (  # noqa: F401
    _wait_for_background_tasks,
    run_task,
    run_task_async,
)
