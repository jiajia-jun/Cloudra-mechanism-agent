import asyncio
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config

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
    attachments: Optional[List[str]] = Field(default_factory=list, description="Absolute paths of attachment files")

class EmailSender_output_schema(output_schema):
    success: bool = Field(description="Whether the email was sent")
    message: str = Field(description="Result details or error message")

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

        if not config.user or not config.password:
            return EmailSender_output_schema(
                success=False,
                message="[Config error] SMTP username or password is not set. Configure it via config or environment variables."
            )

        # 准备邮件内容
        msg = MIMEMultipart()
        msg['From'] = f"{config.sender_name} <{config.user}>"
        msg['To'] = user_input.to_email
        msg['Subject'] = user_input.subject

        # 添加正文
        part = MIMEText(user_input.body, 'html' if user_input.is_html else 'plain', 'utf-8')
        msg.attach(part)

        # 添加附件
        for file_path in (user_input.attachments or []):
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        attachment = MIMEApplication(f.read())
                    attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file_path))
                    msg.attach(attachment)
                except Exception as e:
                    print(f"无法添加附件 {file_path}: {e}")
            else:
                print(f"附件路径不存在: {file_path}")

        # 异步发送
        try:
            await asyncio.to_thread(self._send_smtp, config, msg)
            return EmailSender_output_schema(success=True, message=f"Email sent to {user_input.to_email}")
        except Exception as e:
            return EmailSender_output_schema(success=False, message=f"Failed to send email: {str(e)}")

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

def get_class():
    return EmailSender
