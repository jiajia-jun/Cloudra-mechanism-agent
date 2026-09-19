"""email_sender: SMTP send path with monkeypatched smtplib + 安全闸门。"""

from types import SimpleNamespace

import pytest

from cloudra.infra.config import get_config
from cloudra.tools.Interactool.email_sender import EmailSender, EmailSender_input_schema


async def _approve(self, session, **_kwargs):
    return True, ""


@pytest.fixture
def smtp_config(monkeypatch):
    email = get_config().email
    monkeypatch.setattr(email, "enabled", True)
    monkeypatch.setattr(email, "user", "bot@example.com")
    monkeypatch.setattr(email, "password", "secret")
    monkeypatch.setattr(email, "smtp_server", "smtp.example.com")
    monkeypatch.setattr(email, "smtp_port", 465)
    monkeypatch.setattr(email, "whitelist", ["user@example.com"])
    monkeypatch.setattr(EmailSender, "ensure_safety", _approve)
    return email


@pytest.fixture
def smtp_spy(monkeypatch):
    sent = {}

    class FakeSMTPSSL:
        def __init__(self, host, port):
            sent["host"] = host
            sent["port"] = port

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["msg"] = msg

        def quit(self):
            sent["quit"] = True

    monkeypatch.setattr("cloudra.tools.Interactool.email_sender.smtplib.SMTP_SSL", FakeSMTPSSL)
    return sent


def _tool(workdir) -> EmailSender:
    return EmailSender(subagent=SimpleNamespace(working_directory=str(workdir)))


@pytest.mark.asyncio
async def test_email_sent_and_missing_attachment_skipped(smtp_config, smtp_spy, tmp_path):
    present = tmp_path / "report.txt"
    present.write_text("result", encoding="utf-8")
    missing = str(tmp_path / "ghost.png")

    result = await _tool(tmp_path).tool_call(
        EmailSender_input_schema(
            to_email="user@example.com",
            subject="job done",
            body="see attachment",
            attachments=[str(present), missing],
        ),
        session=SimpleNamespace(id="s1"),
    )

    assert result.is_success is True, result.message
    assert result.skipped_attachments == [missing]
    assert smtp_spy["login"] == ("bot@example.com", "secret")
    assert smtp_spy["quit"] is True
    msg = smtp_spy["msg"]
    assert msg["To"] == "user@example.com"
    # 存在的附件照常附上
    filenames = [part.get_filename() for part in msg.walk()]
    assert "report.txt" in filenames


@pytest.mark.asyncio
async def test_email_without_credentials_fails(monkeypatch):
    email = get_config().email
    monkeypatch.setattr(email, "enabled", True)
    monkeypatch.setattr(email, "user", "")
    monkeypatch.setattr(email, "password", "")

    result = await EmailSender().tool_call(
        EmailSender_input_schema(to_email="u@e.com", subject="s", body="b"),
        session=None,
    )
    assert result.is_success is False
    assert "Config error" in result.message


@pytest.mark.asyncio
async def test_email_disabled_by_default_gate(monkeypatch):
    """email.enabled=false（默认）时工具硬失败，无需凭据检查。"""
    monkeypatch.setattr(get_config().email, "enabled", False)

    result = await EmailSender().tool_call(
        EmailSender_input_schema(to_email="u@e.com", subject="s", body="b"),
        session=None,
    )
    assert result.is_success is False
    assert "email.enabled" in result.message


@pytest.mark.asyncio
async def test_empty_whitelist_refuses_everything(smtp_config, smtp_spy, monkeypatch, tmp_path):
    """空白名单 = 拒绝一切，message 提示配置 email.whitelist。"""
    monkeypatch.setattr(get_config().email, "whitelist", [])

    result = await _tool(tmp_path).tool_call(
        EmailSender_input_schema(to_email="user@example.com", subject="s", body="b"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "email.whitelist" in result.message
    assert "msg" not in smtp_spy  # 未触网


@pytest.mark.asyncio
async def test_recipient_outside_whitelist_refused(smtp_config, smtp_spy, tmp_path):
    result = await _tool(tmp_path).tool_call(
        EmailSender_input_schema(to_email="attacker@evil.example", subject="s", body="b"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "[Safety block]" in result.message
    assert "msg" not in smtp_spy


@pytest.mark.asyncio
async def test_attachment_outside_workdir_refused(smtp_config, smtp_spy, tmp_path):
    """附件解析后必须落在 agent 工作目录内；区外直接拒发。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    workdir = tmp_path / "ws"
    workdir.mkdir()

    result = await _tool(workdir).tool_call(
        EmailSender_input_schema(
            to_email="user@example.com",
            subject="s",
            body="b",
            attachments=[str(secret), "../outside/secret.txt"],
        ),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "[Safety block]" in result.message
    assert "msg" not in smtp_spy


@pytest.mark.asyncio
async def test_send_requires_approval(smtp_config, smtp_spy, monkeypatch, tmp_path):
    """审批拒绝 → 不发送，返回 [Safety block] 说明。"""

    async def _deny(self, session, **_kwargs):
        return False, "user said no"

    monkeypatch.setattr(EmailSender, "ensure_safety", _deny)

    result = await _tool(tmp_path).tool_call(
        EmailSender_input_schema(to_email="user@example.com", subject="s", body="b"),
        session=SimpleNamespace(id="s1"),
    )
    assert result.is_success is False
    assert "[Safety block]" in result.message
    assert "user said no" in result.message
    assert "msg" not in smtp_spy
