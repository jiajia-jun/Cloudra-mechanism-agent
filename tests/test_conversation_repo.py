"""测试 conversation_repo：list / latest / messages 三种查询语义。"""

import json

import pytest

from cloudra import conversation_repo


def _write_meta(data_dir, conv_id, **meta):
    conv_dir = data_dir / "conversations" / conv_id
    conv_dir.mkdir(parents=True, exist_ok=True)
    meta.setdefault("id", conv_id)
    (conv_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return conv_dir


def test_list_conversations_sorted_by_last_active(tmp_path):
    _write_meta(tmp_path, "conv_old", last_active="2026-01-01T00:00:00", state="sleeping")
    _write_meta(tmp_path, "conv_new", last_active="2026-02-01T00:00:00", state="running")

    result = conversation_repo.list_conversations(data_dir=tmp_path)
    assert [c["id"] for c in result] == ["conv_new", "conv_old"]


def test_list_conversations_skips_broken_meta_and_fills_id(tmp_path):
    good = _write_meta(tmp_path, "conv_good", last_active="2026-01-01T00:00:00")
    bad = tmp_path / "conversations" / "conv_bad"
    bad.mkdir(parents=True)
    (bad / "meta.json").write_text("{not json", encoding="utf-8")
    # 目录存在但缺少 meta.json
    (tmp_path / "conversations" / "conv_nometa").mkdir(parents=True)
    # 散文件不应被当作会话
    (tmp_path / "conversations" / "stray.txt").write_text("x", encoding="utf-8")

    result = conversation_repo.list_conversations(data_dir=tmp_path)
    assert [c["id"] for c in result] == ["conv_good"]

    # meta 缺 id 时以目录名补齐
    (good / "meta.json").write_text(json.dumps({"last_active": "2026-01-01"}), encoding="utf-8")
    result = conversation_repo.list_conversations(data_dir=tmp_path)
    assert result[0]["id"] == "conv_good"


def test_list_conversations_empty(tmp_path):
    assert conversation_repo.list_conversations(data_dir=tmp_path) == []


def test_latest_active_conversation_prefers_config(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
    reload_config()
    cfg = get_config()
    cfg.data_dir = tmp_path
    cfg.last_conversation_id = "conv_sticky"
    assert conversation_repo.latest_active_conversation() == "conv_sticky"
    cfg.last_conversation_id = None


def test_latest_active_conversation_picks_newest_non_archived(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
    reload_config()
    cfg = get_config()
    cfg.data_dir = tmp_path
    cfg.last_conversation_id = None

    _write_meta(tmp_path, "conv_archived", last_active="2026-03-01T00:00:00", state="archived")
    _write_meta(tmp_path, "conv_sleeping", last_active="2026-02-01T00:00:00", state="sleeping")
    _write_meta(tmp_path, "conv_active", last_active="2026-01-01T00:00:00", state="active")

    assert conversation_repo.latest_active_conversation() == "conv_sleeping"


def test_latest_active_conversation_none_when_all_archived(tmp_path, monkeypatch):
    from cloudra.config import get_config, reload_config

    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
    reload_config()
    cfg = get_config()
    cfg.data_dir = tmp_path
    cfg.last_conversation_id = None

    _write_meta(tmp_path, "conv_archived", last_active="2026-03-01T00:00:00", state="archived")
    assert conversation_repo.latest_active_conversation() is None


def test_conversation_messages_reads_a0_context(tmp_path):
    conv_dir = _write_meta(tmp_path, "conv_msg", last_active="2026-01-01T00:00:00")
    ctx_dir = conv_dir / "contexts"
    ctx_dir.mkdir()
    messages = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "hello"},
    ]
    (ctx_dir / "a-0.json").write_text(json.dumps(messages), encoding="utf-8")

    assert conversation_repo.conversation_messages("conv_msg", data_dir=tmp_path) == messages


def test_conversation_messages_missing_file_returns_empty(tmp_path):
    _write_meta(tmp_path, "conv_empty", last_active="2026-01-01T00:00:00")
    assert conversation_repo.conversation_messages("conv_empty", data_dir=tmp_path) == []


def test_conversation_messages_rejects_non_list(tmp_path):
    conv_dir = _write_meta(tmp_path, "conv_broken", last_active="2026-01-01T00:00:00")
    ctx_dir = conv_dir / "contexts"
    ctx_dir.mkdir()
    (ctx_dir / "a-0.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    with pytest.raises(ValueError, match="格式错误"):
        conversation_repo.conversation_messages("conv_broken", data_dir=tmp_path)
