"""logging 统一配置入口。

所有 cloudra 进程（Web API / CLI / scheduler 守护进程）经 ``setup_logging``
配置命名 logger（惯例 ``"cloudra"``；包内模块一律 ``getLogger(__name__)``
挂到 ``cloudra.*`` 树下继承）。不碰 root logger，避免吞掉 uvicorn 等第三方
日志。detach 进程（scheduler，stdout/stderr 已被 ``spawn_detached`` 重定向进
各自 log 文件）传 ``stream`` 而非 ``log_file``，避免与重定向双写同一文件。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3
# 只给本模块装的 handler 打标：幂等去重不动外部（uvicorn/测试）已挂的 handler。
_MANAGED = "_cloudra_managed"


def setup_logging(
    name: str,
    *,
    log_file: Path | None = None,
    stream=None,
    level: str | None = None,
) -> logging.Logger:
    """配置命名 logger 并返回它（幂等：同名重复调用不叠加 handler）。

    level 缺省取环境变量 ``CLOUDRA_LOG_LEVEL``（再缺省 INFO），每次调用都
    生效（后调用者可调级）；handler 只在首次调用时装一只——log_file 时装
    RotatingFileHandler（5MB×3，utf-8，父目录自动创建），stream 时装
    StreamHandler，两者都给时 log_file 优先，都不给则只调级别。
    """
    logger = logging.getLogger(name)
    logger.setLevel((level or os.environ.get("CLOUDRA_LOG_LEVEL") or "INFO").upper())
    if any(getattr(h, _MANAGED, False) for h in logger.handlers):
        return logger
    handler: logging.Handler
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    elif stream is not None:
        handler = logging.StreamHandler(stream)
    else:
        return logger
    handler.setFormatter(logging.Formatter(_FORMAT))
    setattr(handler, _MANAGED, True)
    logger.addHandler(handler)
    return logger
