"""email_sender: SMTP send path with monkeypatched smtplib."""

import pytest

from cloudra.infra.config import get_config
from cloudra.tools.Interactool.email_sender import EmailSender, EmailSender_input_schema


@pytest.fixture
def smtp_config(monkeypatch):
    email = get_config().email
    monkeypatch.setattr(email, "user", "bot@example.com")
    monkeypatch.setattr(email, "password", "secret")
    monkeypatch.setattr(email, "smtp_server", "smtp.example.com")
    monkeypatch.setattr(email, "smtp_port", 465)
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


@pytest.mark.asyncio
async def test_email_sent_and_missing_attachment_skipped(smtp_config, smtp_spy, tmp_path):
    present = tmp_path / "report.txt"
    present.write_text("result", encoding="utf-8")
    missing = str(tmp_path / "ghost.png")

    result = await EmailSender().tool_call(
        EmailSender_input_schema(
            to_email="user@example.com",
            subject="job done",
            body="see attachment",
            attachments=[str(present), missing],
        ),
        session=None,
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
    monkeypatch.setattr(email, "user", "")
    monkeypatch.setattr(email, "password", "")

    result = await EmailSender().tool_call(
        EmailSender_input_schema(to_email="u@e.com", subject="s", body="b"),
        session=None,
    )
    assert result.is_success is False
    assert "Config error" in result.message
