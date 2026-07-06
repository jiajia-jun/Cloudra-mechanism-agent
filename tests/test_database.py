"""测试 ConversationDB 路径隔离与初始化。"""

import os
import sqlite3

import pytest

from cloudra.database import ConversationDB, get_database_path
from cloudra.config import get_config, reload_config


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """使用临时数据目录隔离数据库。"""
    data_dir = tmp_path / "cloudra_data"
    data_dir.mkdir()
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    cfg = get_config()
    cfg.data_dir = data_dir
    return str(data_dir)


def test_conversation_db_path(isolated_db):
    """ConversationDB 路径应包含 conversation_id。"""
    db = ConversationDB("conv_abc")
    expected_suffix = os.path.join("conversations", "conv_abc", "tasks", "database.db")
    assert db.path.endswith(expected_suffix)


def test_get_database_path_default():
    """默认 conversation_id 为 'default'。"""
    path = get_database_path()
    assert "conversations" in path and "default" in path


def test_conversation_db_init_creates_tables(isolated_db):
    """init() 应创建所有必要表并启用 WAL。"""
    db = ConversationDB("conv_init").init()
    assert os.path.exists(db.path)

    with sqlite3.connect(db.path) as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}

    assert "session" in tables
    assert "subagent_requests" in tables
    assert "approvals" in tables
    assert "compute_jobs" in tables
    assert "context_events" in tables


def test_conversation_db_isolation(isolated_db):
    """不同 conversation 的数据库应物理隔离。"""
    db_a = ConversationDB("conv_a").init()
    db_b = ConversationDB("conv_b").init()

    assert db_a.path != db_b.path
    assert os.path.exists(db_a.path)
    assert os.path.exists(db_b.path)

    # 向 A 写入 session，B 不应读到
    with db_a.connect() as con:
        con.execute("INSERT INTO session (session_id, state, result) VALUES (?, ?, ?)",
                    ("s1", "sleeping", "hello"))
        con.commit()

    with db_b.connect() as con:
        cur = con.execute("SELECT COUNT(*) FROM session WHERE session_id = ?", ("s1",))
        assert cur.fetchone()[0] == 0


def test_conversation_db_connect_sets_wal_and_busy_timeout(isolated_db):
    """connect() 应自动设置 WAL 和 busy_timeout。"""
    db = ConversationDB("conv_pragma").init()
    with db.connect(timeout=20) as con:
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].upper() == "WAL"
        cur.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 20000
