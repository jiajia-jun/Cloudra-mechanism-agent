"""web_launcher 回归测试。"""

from __future__ import annotations

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
    argv = web_launcher._uvicorn_argv(18999)

    assert argv[argv.index("--port") + 1] == "18999"
    timeout = int(argv[argv.index("--timeout-graceful-shutdown") + 1])
    assert timeout > 0
