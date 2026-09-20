"""web_launcher 回归测试。"""

from __future__ import annotations

import pytest

import cloudra.web_launcher as web_launcher


class _FakeProc:
    def wait(self) -> int:
        return 0

    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        pass


def test_uvicorn_subprocess_pins_cwd_to_frontend(tmp_path, monkeypatch):
    """uvicorn 子进程必须固定 cwd（frontend 目录），不能继承用户 shell 的 cwd：
    `python -m` 会把 cwd 放到 sys.path 最前面，cwd 下一个无 __init__.py 的
    `cloudra` 目录会把已安装包遮蔽成 namespace 包（__version__ 缺失、
    api_v2 却能被 editable finder 加载，报 "unknown location"）。"""
    frontend = tmp_path / "frontend"
    frontend.mkdir()

    captured: dict = {}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr(web_launcher.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(web_launcher, "_ensure_frontend", lambda *a, **k: None)
    monkeypatch.setattr(web_launcher, "ensure_daemons", lambda: None)
    monkeypatch.setattr(web_launcher, "_wait_healthy", lambda url: None)
    monkeypatch.setenv("CLOUDRA_API_PORT", "18999")
    monkeypatch.setenv("CLOUDRA_NO_BROWSER", "1")

    rc = web_launcher.launch_browser(frontend, rebuild=False, skip_build=True)

    assert rc == 0
    assert captured.get("cwd") == frontend
    # 关停上界必须真的传进 uvicorn（GH #38），不能只在 helper 里存在
    assert "--timeout-graceful-shutdown" in captured["cmd"]


def test_uvicorn_argv_bounds_graceful_shutdown():
    """必须给 uvicorn 一个有界的关停等待：常驻 SSE（SPA 的 EventSource）不会自己结束，
    默认（None）会无限等活跃连接，`cloudra stop` 报「API: 已停止」却关不死进程（GH #38）。"""
    argv = web_launcher._uvicorn_argv(18999, "127.0.0.1")

    assert argv[argv.index("--port") + 1] == "18999"
    timeout = int(argv[argv.index("--timeout-graceful-shutdown") + 1])
    assert timeout > 0


def test_uvicorn_argv_binds_requested_host():
    """--host 必须真的传进 uvicorn，否则自定义地址只是摆设。"""
    argv = web_launcher._uvicorn_argv(18999, "0.0.0.0")
    assert argv[argv.index("--host") + 1] == "0.0.0.0"


def _patch_launch(monkeypatch, captured):
    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return _FakeProc()

    def _fake_wait_healthy(url):
        captured["health_url"] = url

    monkeypatch.setattr(web_launcher.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(web_launcher, "_ensure_frontend", lambda *a, **k: None)
    monkeypatch.setattr(web_launcher, "ensure_daemons", lambda: None)
    monkeypatch.setattr(web_launcher, "_wait_healthy", _fake_wait_healthy)
    monkeypatch.setenv("CLOUDRA_NO_BROWSER", "1")


def test_launch_refuses_auth_off_on_non_loopback(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "off")
    with pytest.raises(RuntimeError, match="loopback"):
        web_launcher.launch_browser(
            frontend, rebuild=False, skip_build=True, host="0.0.0.0", port=18999
        )
    assert "cmd" not in captured


def test_launch_browser_passes_bind_host_to_child(tmp_path, monkeypatch):
    """自定义地址要同时落到两处：uvicorn 的 --host，以及子进程 env 里的
    CLOUDRA_API_BIND_HOST（app 的 Host 校验白名单据此放开）。"""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")

    rc = web_launcher.launch_browser(
        frontend, rebuild=False, skip_build=True, host="0.0.0.0", port=18999
    )

    assert rc == 0
    argv = captured["cmd"]
    assert argv[argv.index("--host") + 1] == "0.0.0.0"
    assert captured["env"]["CLOUDRA_API_BIND_HOST"] == "0.0.0.0"
    # 通配绑定下本机浏览器/健康探测仍走回环
    assert captured["health_url"] == "http://127.0.0.1:18999/api/v2/runtime/health"


def test_launch_browser_defaults_to_loopback(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)

    rc = web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, port=18999)

    assert rc == 0
    argv = captured["cmd"]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert captured["env"]["CLOUDRA_API_BIND_HOST"] == "127.0.0.1"


def test_wildcard_bind_prints_reachable_url(tmp_path, monkeypatch, capsys):
    """通配绑定常常是「服务在远端、浏览器在别处」：控制台必须同时给出对外
    地址（否则从 SSH 里复制出去的 127.0.0.1 在另一台机器上打不开）。"""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "_primary_address", lambda: "192.168.1.50")
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-secret-token")

    web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, host="0.0.0.0", port=18999)

    out = capsys.readouterr().out
    assert "[cloudra] web UI: http://127.0.0.1:18999" in out
    assert "reachable from other machines: http://192.168.1.50:18999" in out


def test_loopback_bind_prints_no_reachable_url(tmp_path, monkeypatch, capsys):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "_primary_address", lambda: "192.168.1.50")

    web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, port=18999)

    assert "192.168.1.50" not in capsys.readouterr().out


def test_probe_host_uses_bound_address_for_specific_host():
    """绑具体网卡地址时回环上没有监听，探测/访问地址必须是绑定地址本身。"""
    assert web_launcher._probe_host("0.0.0.0") == "127.0.0.1"
    assert web_launcher._probe_host("::") == "127.0.0.1"
    assert web_launcher._probe_host("192.168.1.5") == "192.168.1.5"
    assert web_launcher._probe_host("::1") == "[::1]"

def test_wildcard_rebind_does_not_reuse_loopback_only_runtime(monkeypatch):
    """已有一个只绑回环的实例占着 8000 时，`cloudra web --host 0.0.0.0` 不能
    判定为「复用」——回环探测分辨不出对端绑的是 127.0.0.1 还是 0.0.0.0，复用
    会让改绑静默失效（用户以为已可从网络访问，实际仍在回环上）。"""
    monkeypatch.delenv("CLOUDRA_API_PORT", raising=False)
    monkeypatch.setattr(web_launcher, "_runtime_is_healthy", lambda host, port: True)
    monkeypatch.setattr(web_launcher, "_runtime_serves_spa", lambda host, port: True)
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda bind_host, port: port != 8000)

    assert web_launcher._find_api_port(8000, "CLOUDRA_API_PORT", "127.0.0.1") == (8000, True)
    assert web_launcher._find_api_port(8000, "CLOUDRA_API_PORT", "0.0.0.0") == (8001, False)
    # 具体网卡地址的探测地址就是绑定地址本身，复用判定照旧可信
    assert web_launcher._find_api_port(8000, "CLOUDRA_API_PORT", "192.168.1.5") == (8000, True)
