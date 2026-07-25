import os

import pytest

from cloudra.session_class import Session


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """测试隔离：默认把全局配置的数据目录重定向到临时目录，
    避免测试在真实用户数据目录（~/.local/share/cloudra）累积垃圾文件。
    需要自定义数据目录的测试可在测试内再 monkeypatch 覆盖（后应用者生效）。
    """
    from cloudra.config import get_config

    monkeypatch.setattr(get_config(), "data_dir", tmp_path / "data")


@pytest.fixture
def mock_session(tmp_path):
    session_path = tmp_path / "test_session.json"
    return Session(id="test-session", path=str(session_path))

@pytest.fixture
def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
