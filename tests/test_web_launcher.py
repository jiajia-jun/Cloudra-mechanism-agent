"""web_launcher 回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import cloudra.web_launcher as web_launcher
from cloudra.cli import cli
from cloudra.persistence.paths import runtime_api_lock_path
from cloudra.services import runtime_ownership


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
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: True)
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
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: True)
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

def test_free_port_selection_never_reuses_an_occupied_port(monkeypatch):
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: port != 8000)
    assert web_launcher._find_api_port(8000, "127.0.0.1") == 8001
    assert web_launcher._find_api_port(8000, "0.0.0.0") == 8001


def test_launch_refuses_when_store_owned_by_non_reusable_api(tmp_path, monkeypatch):
    """主库已被别家占着时必须点名占用者，而不是让 uvicorn 子进程撞锁。

    实测（2026-10-15）：launchd 自启的 API 占着主库（8000），但它的
    CLOUDRA_FRONTEND_SERVE_DIR 指向已失效的旧仓库（GET / 404），于是
    前端探测判它「不可复用」→ CLI 悄悄换到空闲的 8001 起子进程 →
    子进程在 create_default_v2_app 的排他 flock 上退出，用户只看到一句
    "database is already in use"，既不知道是谁占的，也不知道 `cloudra stop`
    之后会被 KeepAlive 立刻拉起。端口空闲并不代表能另起实例。
    """
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    # 占用者必然创建过锁文件；这里把它摆出来，模拟「主库已被别家持有」。
    store_path = tmp_path / "runtime-v2.db"
    monkeypatch.setenv("CLOUDRA_RUNTIME_STORE", str(store_path))
    runtime_api_lock_path(store_path).write_text("")
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    phases: list[str] = []
    monkeypatch.setattr(web_launcher, "_ensure_frontend", lambda *a, **k: phases.append("build"))
    monkeypatch.delenv("CLOUDRA_API_PORT", raising=False)
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda bind_host, port: port != 8000)
    monkeypatch.setattr(web_launcher, "is_lock_held", lambda path: True)
    monkeypatch.setattr(
        web_launcher,
        "find_store_owner",
        lambda store_path, *, probe_host="127.0.0.1": runtime_ownership.StoreOwner(
            11956, 8000, False
        ),
    )

    with pytest.raises(RuntimeError) as excinfo:
        web_launcher.launch_browser(frontend, rebuild=False, skip_build=True)

    message = str(excinfo.value)
    assert "11956" in message and "8000" in message
    assert "cloudra stop" in message and "自启" in message
    # 子进程与前端构建都不该发生：必须在拉起之前就 fail loud
    assert "cmd" not in captured
    assert phases == []


def test_launch_starts_when_store_is_free(tmp_path, monkeypatch):
    """无人持锁时照旧拉起子进程——拒绝逻辑不能误伤正常启动。"""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "is_lock_held", lambda path: False)

    assert web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, port=18999) == 0
    assert captured["cmd"][captured["cmd"].index("--port") + 1] == "18999"


def test_cli_reports_store_conflict_without_traceback(tmp_path, monkeypatch):
    """`cloudra web` 撞上主库占用要以红字提示 + 退出码 1 收场，不甩 traceback。"""

    def _raise(*args, **kwargs):
        raise RuntimeError("Cloudra 主库已被其他实例占用：/tmp/runtime-v2.db")

    monkeypatch.setattr("cloudra.cli._frontend_or_exit", lambda: tmp_path / "frontend")
    monkeypatch.setattr("cloudra.cli.launch_browser", _raise)

    result = CliRunner().invoke(cli, ["web", "--skip-build"])

    assert result.exit_code == 1
    assert "Cloudra 主库已被其他实例占用" in result.output
    assert "Traceback" not in result.output


def test_find_store_owner_reads_pid_and_listen_port(monkeypatch, tmp_path):
    """占用者定位靠 lsof 字段行：`-t` 给 PID，`-F n` 给监听端口。"""

    def _fake_lsof(args):
        if args[0] == "-t":
            return "11956\n"
        return "p11956\nn127.0.0.1:8000\nn[::1]:8000\n"

    monkeypatch.setattr(runtime_ownership, "_lsof", _fake_lsof)
    monkeypatch.setattr(runtime_ownership, "api_is_healthy", lambda host, port: port == 8000)
    monkeypatch.setattr(runtime_ownership, "api_serves_spa", lambda host, port: False)

    owner = runtime_ownership.find_store_owner(tmp_path / "runtime-v2.db")

    assert owner == runtime_ownership.StoreOwner(11956, 8000, False)


def test_find_store_owner_keeps_pid_when_api_unresponsive(monkeypatch, tmp_path):
    """持锁进程不健康应答时仍要报出 PID，不能谎称「查不到占用者」。"""
    monkeypatch.setattr(
        runtime_ownership, "_lsof", lambda args: "11956\n" if args[0] == "-t" else "p11956\n"
    )
    monkeypatch.setattr(runtime_ownership, "api_is_healthy", lambda host, port: False)

    owner = runtime_ownership.find_store_owner(tmp_path / "runtime-v2.db")

    assert owner == runtime_ownership.StoreOwner(11956, None, False)
    assert "11956" in runtime_ownership.describe_store_conflict("runtime-v2.db", owner)


def test_find_store_owner_returns_none_without_holder(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_ownership, "_lsof", lambda args: "")

    assert runtime_ownership.find_store_owner(tmp_path / "runtime-v2.db") is None

    message = runtime_ownership.describe_store_conflict(tmp_path / "runtime-v2.db", None)
    assert "lsof" in message and "cloudra stop" in message


def test_describe_store_conflict_explains_wildcard_refusal():
    """提供 SPA 但被通配绑定策略挡下时，文案要说清原因，不能笼统说「不可复用」。"""
    owner = runtime_ownership.StoreOwner(11956, 8000, True)

    message = runtime_ownership.describe_store_conflict(
        "runtime-v2.db", owner, reuse_allowed=False
    )

    assert "8000" in message and "通配绑定" in message


@pytest.mark.parametrize("explicit_store", [False, True])
def test_healthy_foreign_runtime_does_not_override_requested_store(tmp_path, monkeypatch, explicit_store):
    from cloudra.infra.config import get_config

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    requested = tmp_path / "other-runtime.db"
    if explicit_store:
        monkeypatch.setenv("CLOUDRA_RUNTIME_STORE", str(requested))
    else:
        monkeypatch.delenv("CLOUDRA_RUNTIME_STORE", raising=False)
        requested = Path(get_config().data_dir) / "runtime-v2.db"
    monkeypatch.delenv("CLOUDRA_API_PORT", raising=False)
    captured = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: port != 8000)

    assert web_launcher.launch_browser(frontend, rebuild=False, skip_build=True) == 0
    assert captured["env"]["CLOUDRA_RUNTIME_STORE"] == str(requested.resolve())
    assert captured["cmd"][captured["cmd"].index("--port") + 1] == "8001"


def test_launcher_reuses_requested_store_owner_on_its_actual_port(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    requested = tmp_path / "owned.db"
    monkeypatch.setenv("CLOUDRA_RUNTIME_STORE", str(requested))
    monkeypatch.delenv("CLOUDRA_API_PORT", raising=False)
    runtime_api_lock_path(requested).write_text("")
    captured = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "is_lock_held", lambda path: True)
    monkeypatch.setattr(web_launcher, "find_store_owner", lambda *a, **kw: runtime_ownership.StoreOwner(42, 8005, True))
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: True)

    assert web_launcher.launch_browser(frontend, rebuild=False, skip_build=True) == 0
    assert "cmd" not in captured
    assert captured["health_url"] == "http://127.0.0.1:8005/api/v2/runtime/health"


@pytest.mark.parametrize("bind_host, port", [("0.0.0.0", None), ("127.0.0.1", 8000)])
def test_owned_runtime_does_not_silently_ignore_bind_or_port(tmp_path, monkeypatch, bind_host, port):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    requested = tmp_path / "owned.db"
    monkeypatch.setenv("CLOUDRA_RUNTIME_STORE", str(requested))
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "test-token")
    monkeypatch.delenv("CLOUDRA_API_PORT", raising=False)
    runtime_api_lock_path(requested).write_text("")
    captured = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "is_lock_held", lambda path: True)
    monkeypatch.setattr(web_launcher, "find_store_owner", lambda *a, **kw: runtime_ownership.StoreOwner(42, 8005, True))

    with pytest.raises(RuntimeError, match="8005"):
        web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, host=bind_host, port=port)
    assert "cmd" not in captured


def test_foreign_runtime_on_explicit_port_is_not_opened(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured = {}
    _patch_launch(monkeypatch, captured)
    monkeypatch.setattr(web_launcher, "_port_is_bindable", lambda host, port: False)

    with pytest.raises(RuntimeError, match="8000.*another service"):
        web_launcher.launch_browser(frontend, rebuild=False, skip_build=True, port=8000)
    assert "cmd" not in captured
    assert "health_url" not in captured
