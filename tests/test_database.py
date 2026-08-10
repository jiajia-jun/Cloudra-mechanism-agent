"""测试 ConversationDB 路径隔离与初始化。"""

import os
import sqlite3

import pytest

from cloudra.config import get_config, reload_config
from cloudra.database import (
    SCHEMA_VERSION,
    ConversationDB,
    aretry_on_locked,
    get_database_path,
    retry_on_locked,
)


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


def test_conversation_db_data_dir_override(tmp_path):
    """显式注入 data_dir 时不读全局配置。"""
    db = ConversationDB("conv_ovr", data_dir=tmp_path)
    expected = tmp_path / "conversations" / "conv_ovr" / "tasks" / "database.db"
    assert db.path == str(expected)
    db.init()
    assert os.path.exists(db.path)
    with db.connect() as con:
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].upper() == "WAL"
        cur.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 60000


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
    assert "session_events" in tables
    assert "client_commands" in tables
    assert "interactions" in tables
    assert "artifacts" in tables
    assert "artifact_download_tokens" in tables
    assert "hub_posts" in tables
    assert "schema_migrations" in tables
    with sqlite3.connect(db.path) as con:
        session_columns = {row[1] for row in con.execute("PRAGMA table_info(session)")}
    assert {"agent_id", "query", "error", "pid", "started_at", "finished_at"} <= session_columns
    with sqlite3.connect(db.path) as con:
        compute_columns = {row[1] for row in con.execute("PRAGMA table_info(compute_jobs)")}
        subagent_columns = {row[1] for row in con.execute("PRAGMA table_info(subagent_requests)")}
        approval_columns = {
            row[1] for row in con.execute("PRAGMA table_info(approvals)")
        }
        version = con.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
    assert "session_id" in compute_columns
    assert {"session_id", "parent_session_id"} <= subagent_columns
    assert {
        "tool_name",
        "normalized_arguments",
        "risk_summary",
        "candidate_diff",
        "requested_at",
        "expires_at",
        "decided_by",
        "decided_at",
    } <= approval_columns
    assert version == SCHEMA_VERSION


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


def test_conversation_db_connect_closes_on_context_exit(isolated_db):
    """同步连接离开上下文后必须关闭，避免长测试进程耗尽文件描述符。"""
    db = ConversationDB("conv_close").init()
    with db.connect() as con:
        assert con.execute("SELECT 1").fetchone() == (1,)

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        con.execute("SELECT 1")


@pytest.mark.asyncio
async def test_conversation_db_aconnect_sets_busy_timeout(isolated_db):
    db = ConversationDB("conv_async_pragma").init()
    async with db.aconnect(timeout=20) as con:
        cur = await con.execute("PRAGMA journal_mode")
        assert (await cur.fetchone())[0].upper() == "WAL"
        cur = await con.execute("PRAGMA busy_timeout")
        assert (await cur.fetchone())[0] == 20000


def test_retry_on_locked_retries_transient_lock():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    assert retry_on_locked(operation, retries=3, base_delay=0) == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_aretry_on_locked_retries_transient_lock():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is busy")
        return "ok"

    assert await aretry_on_locked(operation, retries=3, base_delay=0) == "ok"
    assert attempts == 3


def test_init_migrates_legacy_session_table_without_losing_rows(isolated_db):
    db = ConversationDB("conv_legacy")
    db.ensure_dir()
    with sqlite3.connect(db.path) as con:
        con.execute("CREATE TABLE session (session_id TEXT PRIMARY KEY, state TEXT, result TEXT)")
        con.execute(
            "INSERT INTO session (session_id, state, result) VALUES (?, ?, ?)",
            ("legacy-1", "sleeping", "old result"),
        )
        con.commit()

    db.init()

    with sqlite3.connect(db.path) as con:
        row = con.execute(
            "SELECT session_id, state, result, agent_id, pid FROM session WHERE session_id = ?",
            ("legacy-1",),
        ).fetchone()
    assert row == ("legacy-1", "sleeping", "old result", None, None)


class TestApprovalSanitize:
    """终端粘贴的 GBK 字节会以孤立代理符残留，审批写库前必须净化。"""

    def test_apply_approval_decision_with_surrogate(self, tmp_path):
        from cloudra.runtime.workers import apply_approval_decision

        db = ConversationDB.from_path(str(tmp_path / "t.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO approvals (session_id, details, state, denial_reason) VALUES ('s1', 'd', 'pending', '')"
            )
            con.commit()

        dirty = "直接 跳过\udce8其实塞不下"
        assert apply_approval_decision(db.path, 1, "denied", dirty) is True

        with db.connect() as con:
            reason = con.execute("SELECT denial_reason FROM approvals WHERE id=1").fetchone()[0]
        # 孤立代理符被替换为 U+FFFD，其余字符保留，且字符串可安全 UTF-8 编码
        assert "\udce8" not in reason
        assert "跳过" in reason and "塞不下" in reason
        reason.encode("utf-8")

    def test_sanitize_db_text_passthrough_clean(self):
        from cloudra import session_store

        assert session_store.sanitize_db_text("正常中文 abc 123") == "正常中文 abc 123"
        assert session_store.sanitize_db_text("") == ""
