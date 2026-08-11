"""审批双通道行为一致性钉板：main.apply_approval_decision vs service.decide_approval。

两条写入路径（CLI 同步通道与 Web/API 异步通道）现在都会对 denial_reason
做 ``_sanitize_db_text`` 净化：孤立代理符被替换为 U+FFFD，写库总是可行。
在干净文本上两者行为一致（状态 + 原因 + pending 守卫），这里一并钉住。
"""

import pytest


def _setup_data_dir(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config, reload_config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    reload_config()
    get_config().data_dir = data_dir
    get_config()._ensure_dirs()
    return data_dir


def _make_pending_approval(conv_id="conv-parity"):
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(conv_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO approvals (session_id, agent_name, details, state) "
            "VALUES ('s-1', 'a-2', 'rm -rf build/', 'pending')"
        )
        req_id = con.execute("SELECT id FROM approvals").fetchone()[0]
        con.commit()
    return db, req_id


def _read_approval(db, req_id):
    with db.connect() as con:
        return con.execute(
            "SELECT state, denial_reason FROM approvals WHERE id=?", (req_id,)
        ).fetchone()


# 终端粘贴 GBK 字节时产生的孤立代理符（surrogateescape）
DIRTY_REASON = "拒绝: " + "中文".encode("gbk").decode("utf-8", errors="surrogateescape")
SANITIZED_REASON = "拒绝: ????"


class TestCleanTextParity:
    """干净文本上两条通道的写入结果一致。"""

    def test_cli_channel_writes_decision(self, tmp_path, monkeypatch):
        from cloudra.runtime.workers import apply_approval_decision

        _setup_data_dir(tmp_path, monkeypatch)
        db, req_id = _make_pending_approval()
        assert apply_approval_decision(db.path, req_id, "denied", "太危险") is True
        assert _read_approval(db, req_id) == ("denied", "太危险")

    @pytest.mark.asyncio
    async def test_service_channel_writes_decision(self, tmp_path, monkeypatch):
        from cloudra.services.service import CloudraService

        _setup_data_dir(tmp_path, monkeypatch)
        db, req_id = _make_pending_approval()
        service = CloudraService()
        assert await service.decide_approval("conv-parity", req_id, "denied", "太危险") is True
        assert _read_approval(db, req_id) == ("denied", "太危险")

    @pytest.mark.asyncio
    async def test_both_channels_guard_non_pending(self, tmp_path, monkeypatch):
        """两条通道都有 pending 守卫：已决定的审批返回 False 且不覆盖。"""
        from cloudra.runtime.workers import apply_approval_decision
        from cloudra.services.service import CloudraService

        _setup_data_dir(tmp_path, monkeypatch)
        db, req_id = _make_pending_approval()
        service = CloudraService()

        assert await service.decide_approval("conv-parity", req_id, "approved") is True
        # 第二通道（CLI）再决定：被拒且不覆盖第一通道的结果
        assert apply_approval_decision(db.path, req_id, "denied", "改主意") is False
        assert _read_approval(db, req_id) == ("approved", "")


class TestSurrogateParity:
    """孤立代理符拒绝原因：两条通道都净化后写入，行为一致。"""

    def test_cli_channel_sanitizes_and_writes(self, tmp_path, monkeypatch):
        from cloudra.runtime.workers import apply_approval_decision

        _setup_data_dir(tmp_path, monkeypatch)
        db, req_id = _make_pending_approval()
        assert apply_approval_decision(db.path, req_id, "denied", DIRTY_REASON) is True
        assert _read_approval(db, req_id) == ("denied", SANITIZED_REASON)

    @pytest.mark.asyncio
    async def test_service_channel_sanitizes_and_writes(self, tmp_path, monkeypatch):
        from cloudra.services.service import CloudraService

        _setup_data_dir(tmp_path, monkeypatch)
        db, req_id = _make_pending_approval()
        service = CloudraService()

        assert await service.decide_approval("conv-parity", req_id, "denied", DIRTY_REASON) is True
        assert _read_approval(db, req_id) == ("denied", SANITIZED_REASON)
