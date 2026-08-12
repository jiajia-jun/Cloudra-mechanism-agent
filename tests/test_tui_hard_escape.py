"""TUI 硬逃生：SIGQUIT / touch tui.force_exit 在 loop 卡死时仍能退回 shell。"""

from __future__ import annotations

import signal
import time
from unittest.mock import patch


def test_force_exit_path_under_data_dir(tmp_path):
    from cloudra.tui.new.hard_escape import force_exit_path

    assert force_exit_path(tmp_path) == tmp_path / "tui.force_exit"


def test_install_registers_sigquit_and_file_watcher(tmp_path, monkeypatch):
    from cloudra.tui.new import hard_escape as he

    he.uninstall_hard_escape_for_tests()
    monkeypatch.setattr("cloudra.infra.config.get_config", lambda: type("C", (), {"data_dir": tmp_path, "save": lambda self: None})())

    path = he.install_hard_escape(data_dir=tmp_path)
    assert path == tmp_path / "tui.force_exit"
    assert signal.getsignal(signal.SIGQUIT) is he.emergency_exit

    with patch.object(he, "emergency_exit") as emergency:
        path.write_text("1", encoding="utf-8")
        deadline = time.time() + 3.0
        while not emergency.called and time.time() < deadline:
            time.sleep(0.05)
        assert emergency.called

    he.uninstall_hard_escape_for_tests()


def test_emergency_exit_persists_config_and_leaves_process(tmp_path, monkeypatch):
    from cloudra.tui.new import hard_escape as he

    saved = {"ok": False}

    class _Cfg:
        data_dir = tmp_path

        def save(self):
            saved["ok"] = True

    monkeypatch.setattr("cloudra.infra.config.get_config", lambda: _Cfg())
    with patch.object(he.os, "_exit") as exit_mock:
        he.emergency_exit(signal.SIGQUIT)
        assert saved["ok"] is True
        exit_mock.assert_called_once()
        assert exit_mock.call_args.args[0] == 128 + int(signal.SIGQUIT)


def test_app_binds_ctrl_q_soft_quit():
    from cloudra.tui.new.app import CloudraTextualApp

    keys = []
    for binding in CloudraTextualApp.BINDINGS:
        key = getattr(binding, "key", None) or (binding[0] if isinstance(binding, tuple) else None)
        action = getattr(binding, "action", None) or (binding[1] if isinstance(binding, tuple) else None)
        keys.append((key, action))
    assert ("ctrl+q", "soft_quit") in keys
