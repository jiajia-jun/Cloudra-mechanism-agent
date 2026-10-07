import asyncio
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config
from cloudra.persistence.workspace import resolve_existing_tool_path

description = (
    "Send email via SMTP, with plain-text or HTML body and optional local-file attachments. "
    "Use for: remotely delivering result notices, molecular structure figures, data reports, etc. after a long task. "
    "Do not use for: reading the inbox or checking user replies (use email_reader); SMTP credentials must be configured first."
)

class EmailSender_input_schema(input_schema):
    to_email: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body")
    is_html: bool = Field(default=False, description="Whether the body is HTML")
    attachments: Optional[List[str]] = Field(default_factory=list, description="Attachment file paths; each must resolve inside the agent working directory")

class EmailSender_output_schema(output_schema):
    is_success: bool = Field(description="Whether the email was sent")
    message: str = Field(description="Result details or error message")
    skipped_attachments: List[str] = Field(
        default_factory=list,
        description="Attachment paths that were skipped (missing file or unreadable). Empty means all attachments were included."
    )

class EmailSender(Tool):
    tool_id: str = 't-29'
    tool_name: str = 'email_sender'
    tool_description: str = description
    input_schema: Any = EmailSender_input_schema
    output_schema: Any = EmailSender_output_schema

    def is_write(self) -> bool:
        """发送邮件被视为一种向外写入操作"""
        return True

    async def tool_call(self, user_input: EmailSender_input_schema, session: Session) -> EmailSender_output_schema:
        config = get_config().email

        if not config.enabled:
            return EmailSender_output_schema(
                is_success=False,
                message="[Config error] email is disabled (email.enabled=false). Set email.enabled=true and configure SMTP credentials first."
            )
        if not config.user or not config.password:
            return EmailSender_output_schema(
                is_success=False,
                message="[Config error] SMTP username or password is not set. Configure it via config or environment variables."
            )

        # 收件人白名单是唯一出口闸门：空名单 = 拒绝一切（fail-closed）。
        whitelist = {w.strip().lower() for w in (config.whitelist or []) if w.strip()}
        if not whitelist:
            return EmailSender_output_schema(
                is_success=False,
                message=(
                    "[Config error] email.whitelist is empty; refusing to send to any recipient. "
                    "Configure allowed recipients first, e.g. "
                    "`cloudra config set email.whitelist user@example.com`."
                ),
            )
        if user_input.to_email.strip().lower() not in whitelist:
            return EmailSender_output_schema(
                is_success=False,
                message=(
                    f"[Safety block] Recipient {user_input.to_email!r} is not in email.whitelist; "
                    "the email was not sent. Ask the user to add it to email.whitelist if this "
                    "recipient is intended."
                ),
            )

        # 附件只允许 agent 工作目录内的文件（防任意本地文件外泄）；缺失文件
        # 保持既有语义：记入 skipped_attachments。
        workdir = Path(
            getattr(self.subagent, "working_directory", None) or os.getcwd()
        ).resolve()
        resolved_attachments: List[str] = []
        skipped_attachments = []
        for file_path in (user_input.attachments or []):
            try:
                resolved = Path(resolve_existing_tool_path(self, file_path)).resolve()
            except FileNotFoundError:
                skipped_attachments.append(file_path)
                continue
            try:
                resolved.relative_to(workdir)
            except ValueError:
                return EmailSender_output_schema(
                    is_success=False,
                    message=(
                        f"[Safety block] Attachment {file_path!r} resolves to {resolved}, which is "
                        f"outside the working directory {workdir}; the email was not sent. "
                        "Copy the file into the working directory and reference it from there."
                    ),
                )
            resolved_attachments.append(str(resolved))

        # 发送前审批：外发动作一律经安全闸门。
        details = (
            f"Action: Send email to {user_input.to_email}\n"
            f"Subject: {user_input.subject}\n"
            f"Attachments: {resolved_attachments or '[]'}"
        )
        approved, denial_reason = await self.ensure_safety(
            session,
            details=details,
            tool_args=user_input.model_dump(mode="json"),
        )
        if not approved:
            message = (
                "[Safety block] The email was rejected and was not sent. "
                "Next: explain to the user why the email was needed, adjust the recipient or "
                "content, or choose a safer alternative."
            )
            if denial_reason:
                message += f"\nRejection reason: {denial_reason}"
            return EmailSender_output_schema(is_success=False, message=message)

        # 准备邮件内容
        msg = MIMEMultipart()
        msg['From'] = f"{config.sender_name} <{config.user}>"
        msg['To'] = user_input.to_email
        msg['Subject'] = user_input.subject

        # 添加正文
        part = MIMEText(user_input.body, 'html' if user_input.is_html else 'plain', 'utf-8')
        msg.attach(part)

        # 添加附件；读取失败的附件记入返回值，让模型和用户可见
        for file_path in resolved_attachments:
            try:
                with open(file_path, 'rb') as f:
                    attachment = MIMEApplication(f.read())
                attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file_path))
                msg.attach(attachment)
            except Exception:
                skipped_attachments.append(file_path)

        # 异步发送
        try:
            await asyncio.to_thread(self._send_smtp, config, msg)
            message = f"Email sent to {user_input.to_email}"
            if skipped_attachments:
                message += f"; skipped attachments (missing or unreadable): {skipped_attachments}"
            return EmailSender_output_schema(
                is_success=True, message=message, skipped_attachments=skipped_attachments
            )
        except Exception as e:
            return EmailSender_output_schema(
                is_success=False, message=f"Failed to send email: {str(e)}",
                skipped_attachments=skipped_attachments
            )

    def _send_smtp(self, config, msg):
        """同步执行 SMTP 发送"""
        if config.smtp_port == 465:
            server = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port)
        else:
            server = smtplib.SMTP(config.smtp_server, config.smtp_port)
            server.starttls()

        server.login(config.user, config.password)
        server.send_message(msg)
        server.quit()
