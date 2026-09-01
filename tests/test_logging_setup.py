"""logging 统一入口（cloudra.infra.logging_setup）的行为测试。

logging 是进程全局态：每个测试用独立命名的 logger，结束把自己装的
handler 摘掉并关闭，不污染其他测试。
"""

from __future__ import annotations

import io
import logging
import re

import pytest

from cloudra.infra.logging_setup import setup_logging


@pytest.fixture
def fresh_logger():
    """独立命名的 logger，测试后还原 handlers/level。"""
    logger = logging.getLogger("cloudra.test_logging_setup.fresh")
    old_handlers, old_level = list(logger.handlers), logger.level
    try:
        yield logger
    finally:
        for handler in list(logger.handlers):
            if handler not in old_handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(old_level)


def _managed_count(logger: logging.Logger) -> int:
    return sum(1 for h in logger.handlers if getattr(h, "_cloudra_managed", False))


def test_setup_logging_is_idempotent(fresh_logger):
    setup_logging(fresh_logger.name, stream=io.StringIO())
    setup_logging(fresh_logger.name, stream=io.StringIO())  # 新 stream 对象也不叠加
    assert _managed_count(fresh_logger) == 1


def test_setup_logging_log_file_writes_formatted_lines(fresh_logger, tmp_path):
    log_file = tmp_path / "logs" / "test.log"  # 父目录不存在，应由 setup 创建
    setup_logging(fresh_logger.name, log_file=log_file)
    fresh_logger.info("hello-file")
    content = log_file.read_text(encoding="utf-8")
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", content), content
    assert f"INFO {fresh_logger.name}: hello-file" in content


def test_setup_logging_respects_env_level(fresh_logger, monkeypatch):
    monkeypatch.setenv("CLOUDRA_LOG_LEVEL", "DEBUG")
    stream = io.StringIO()
    setup_logging(fresh_logger.name, stream=stream)
    assert fresh_logger.level == logging.DEBUG
    fresh_logger.debug("debug-visible")
    assert "debug-visible" in stream.getvalue()


def test_default_v2_app_factory_does_not_stack_handlers():
    from cloudra.services.api_v2 import create_default_v2_app

    logger = logging.getLogger("cloudra")
    # logging 是进程全局态：先于本测试跑过的 app 工厂测试可能留下 managed
    # handler，先清场再断言，保证与测试执行顺序无关。
    for handler in list(logger.handlers):
        if getattr(handler, "_cloudra_managed", False):
            logger.removeHandler(handler)
            handler.close()
    try:
        create_default_v2_app()
        assert _managed_count(logger) == 1
        create_default_v2_app()
        assert _managed_count(logger) == 1
    finally:
        for handler in list(logger.handlers):
            if getattr(handler, "_cloudra_managed", False):
                logger.removeHandler(handler)
                handler.close()
