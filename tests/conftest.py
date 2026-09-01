import os

import pytest

from cloudra.base.session_class import Session


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """测试隔离：默认把全局配置的数据目录重定向到临时目录，
    避免测试在真实用户数据目录（~/.local/share/cloudra）累积垃圾文件。
    需要自定义数据目录的测试可在测试内再 monkeypatch 覆盖（后应用者生效）。
    """
    from cloudra.infra.config import get_config

    # 有些测试会 _reset_for_tests()，重建单例时 YAML 配置（优先级高于环境变量）
    # 会把 data_dir 重置回真实目录；把配置文件指到不存在路径，从源头隔离。
    monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(tmp_path / "config.yaml"))
    # 避免宿主环境残留的 runtime URL 让 Textual 测试误走隔离 HTTP 路径
    monkeypatch.delenv("CLOUDRA_TUI_RUNTIME_URL", raising=False)
    # 守护进程自愈巡检默认关闭：测试进程绝不承担拉起 scheduler/kg_vec 的职责
    monkeypatch.setenv("CLOUDRA_DAEMON_WATCHDOG", "off")
    monkeypatch.setattr(get_config(), "data_dir", tmp_path / "data")


@pytest.fixture
def mock_session(tmp_path):
    session_path = tmp_path / "test_session.json"
    return Session(id="test-session", path=str(session_path))

@pytest.fixture
def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


