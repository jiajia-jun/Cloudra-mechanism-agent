"""CLI `sessions` 命令：跨 conversation 聚合 Session（与 /api/sessions 同路径）。"""

import json

from click.testing import CliRunner

from cloudra.cli import cli
from cloudra.persistence.database import ConversationDB


def _setup_data_dir(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    return data_dir


def _make_conversation_with_session(data_dir, conv_id, session_id, state, result):
    conv_dir = data_dir / "conversations" / conv_id
    conv_dir.mkdir(parents=True)
    (conv_dir / "meta.json").write_text(json.dumps({"id": conv_id}), encoding="utf-8")
    db = ConversationDB(conv_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state, result, created_at) "
            "VALUES (?, 'a-0', 'coordinator', 'q', ?, ?, '2026-01-01T00:00:00')",
            (session_id, state, result),
        )
        con.commit()


def test_sessions_aggregates_conversations(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    _make_conversation_with_session(data_dir, "conv-cli-a", "sess-a", "completed", "done-a")
    _make_conversation_with_session(data_dir, "conv-cli-b", "sess-b", "failed", "boom")

    runner = CliRunner()
    output = runner.invoke(cli, ["sessions"]).output
    assert "sess-a" in output
    assert "sess-b" in output
    assert "conv-cli-a" in output

    filtered = runner.invoke(cli, ["sessions", "--state", "failed"]).output
    assert "sess-b" in filtered
    assert "sess-a" not in filtered


def test_sessions_empty(tmp_path, monkeypatch):
    _setup_data_dir(tmp_path, monkeypatch)

    result = CliRunner().invoke(cli, ["sessions"])
    assert result.exit_code == 0
    assert "暂无 Session" in result.output
