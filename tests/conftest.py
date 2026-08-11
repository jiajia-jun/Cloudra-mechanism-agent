import os

import pytest
import pytest_asyncio

from cloudra.base.session_class import Session


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """测试隔离：默认把全局配置的数据目录重定向到临时目录，
    避免测试在真实用户数据目录（~/.local/share/cloudra）累积垃圾文件。
    需要自定义数据目录的测试可在测试内再 monkeypatch 覆盖（后应用者生效）。
    """
    from cloudra.infra.config import get_config

    # 有些测试会 reload_config()，重建单例时 YAML 配置（优先级高于环境变量）
    # 会把 data_dir 重置回真实目录；把配置文件指到不存在路径，从源头隔离。
    monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(get_config(), "data_dir", tmp_path / "data")


@pytest.fixture
def mock_session(tmp_path):
    session_path = tmp_path / "test_session.json"
    return Session(id="test-session", path=str(session_path))

@pytest.fixture
def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest_asyncio.fixture(autouse=True)
async def _drain_virtual_chat_surfaces():
    """Wait for any pending ChatLog compiler shutdowns before the next test.

    The virtual transcript starts an async close task in ``on_unmount``; this
    fixture drains those tasks so worker threads do not leak between tests.
    """
    yield
    from cloudra.tui.new.widgets.virtual_chat_log import ChatLog

    for surface in list(ChatLog._instances):
        task = surface._close_task
        if task is not None and not task.done():
            try:
                await task
            except Exception:
                pass
