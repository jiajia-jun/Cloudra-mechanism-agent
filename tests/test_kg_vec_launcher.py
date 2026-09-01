"""daemon_supervisor.ensure_kg_vec：kg_vec 向量微服务自启动判定链。

测试绝不真起 .venv-trans 服务：spawn_detached 一律 monkeypatch 拦截；健康
探测走本地临时 HTTP 服务或死端口（127.0.0.1:1 立即拒连）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cloudra.infra.config import get_config
from cloudra.knowledge.plugin import PLUGIN_SPEC
from cloudra.services import daemon_supervisor


@pytest.fixture(autouse=True)
def _data_dir_exists():
    """conftest 只把 data_dir 重定向到 tmp（未建目录）；锁文件 O_CREAT 不建父目录，
    生产里 data_dir 由 config._ensure_dirs 保证存在，测试这里补齐。"""
    Path(get_config().data_dir).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def spawn_calls(monkeypatch):
    """拦截 compute_utils.spawn_detached（ensure_kg_vec 惰性导入源模块属性）。"""
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        "cloudra.infra.compute_utils.spawn_detached",
        lambda cmd, log_path: calls.append((list(cmd), str(log_path))),
    )
    return calls


@pytest.fixture
def plugin_installed(monkeypatch):
    monkeypatch.setattr(get_config(), "plugins", [PLUGIN_SPEC])


@pytest.fixture
def dead_vec_url(monkeypatch):
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            body = json.dumps({"ok": True, "model": "bge-m3", "count": 3}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def healthy_vec_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield server
    server.shutdown()


def test_off_switch_never_spawns(spawn_calls, plugin_installed, dead_vec_url, monkeypatch):
    monkeypatch.setenv("CLOUDRA_KG_VEC", "off")
    daemon_supervisor.ensure_kg_vec()
    assert spawn_calls == []


def test_plugin_not_installed_skips(spawn_calls, dead_vec_url, monkeypatch):
    monkeypatch.setattr(get_config(), "plugins", [])
    daemon_supervisor.ensure_kg_vec()
    assert spawn_calls == []


def test_healthy_service_not_respawned(spawn_calls, plugin_installed, healthy_vec_server):
    daemon_supervisor.ensure_kg_vec()
    assert spawn_calls == []


def test_lock_held_skips(spawn_calls, plugin_installed, dead_vec_url):
    from cloudra.infra.flocks import try_acquire_lock

    fd = try_acquire_lock(daemon_supervisor.kg_vec_lock_path())
    assert fd is not None
    try:
        daemon_supervisor.ensure_kg_vec()
        assert spawn_calls == []
    finally:
        os.close(fd)


def test_missing_vec_python_warns_and_skips(
    spawn_calls, plugin_installed, dead_vec_url, monkeypatch, caplog
):
    monkeypatch.setattr(daemon_supervisor, "resolve_vec_python", lambda _configured="": None)
    with caplog.at_level(logging.WARNING, logger="cloudra.services.daemon_supervisor"):
        daemon_supervisor.ensure_kg_vec()
    assert spawn_calls == []
    assert "kg_vec" in caplog.text


def test_spawns_detached_when_all_clear(spawn_calls, plugin_installed, monkeypatch, tmp_path):
    fake_py = tmp_path / ".venv-trans" / "bin" / "python"
    fake_py.parent.mkdir(parents=True)
    fake_py.touch()
    monkeypatch.setattr(daemon_supervisor, "resolve_vec_python", lambda _configured="": str(fake_py))
    # 死端口（无人监听）但端口号必须透传给 spawn argv
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:19123")
    daemon_supervisor.ensure_kg_vec()
    assert len(spawn_calls) == 1
    cmd, log_path = spawn_calls[0]
    assert cmd[0] == str(fake_py)
    assert cmd[1].endswith(os.path.join("scripts", "kg_vec_service.py"))
    assert cmd[cmd.index("--port") + 1] == "19123"
    assert cmd[cmd.index("--lock-file") + 1] == daemon_supervisor.kg_vec_lock_path()
    assert log_path.endswith("kg_vec.log")


def test_resolve_vec_python_prefers_configured(tmp_path):
    py = tmp_path / "bin" / "python"
    py.parent.mkdir()
    py.touch()
    assert daemon_supervisor.resolve_vec_python(str(py)) == str(py)


def test_resolve_vec_python_configured_missing_returns_none(tmp_path):
    # 显式配置的路径不存在 → None（不静默回落默认探测，错误配置要暴露）
    assert daemon_supervisor.resolve_vec_python(str(tmp_path / "nope" / "python")) is None


def test_knowledge_vec_python_env_override(monkeypatch, tmp_path):
    from cloudra.infra.config import CloudraConfig

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLOUDRA_KNOWLEDGE_VEC_PYTHON", "/custom/venv/bin/python")
    assert CloudraConfig().knowledge_vec_python == "/custom/venv/bin/python"


def test_knowledge_vec_python_yaml_roundtrip(monkeypatch, tmp_path):
    """config set 写入 YAML 后重建配置必须读回（_load_yaml_config 白名单覆盖）。"""
    from cloudra.infra.config import CloudraConfig

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("knowledge_vec_python: /yaml/venv/bin/python\n", encoding="utf-8")
    monkeypatch.setenv("CLOUDRA_CONFIG_FILE", str(cfg_file))
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path / "data"))
    assert CloudraConfig().knowledge_vec_python == "/yaml/venv/bin/python"
