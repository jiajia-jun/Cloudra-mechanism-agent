from pydantic import Field
from typing import Any, List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import asyncio

from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session
from cloudra.config import get_config

description = (
    "发送电子邮件通知。支持发送纯文本或 HTML 内容，并可携带多个文件作为附件。"
    "适用于向用户发送实验完成通知、分子结构图、数据报表等。"
)

class EmailSender_input_schema(input_schema):
    to_email: str = Field(description="收件人邮箱地址")
    subject: str = Field(description="邮件主题")
    body: str = Field(description="邮件正文内容")
    is_html: bool = Field(default=False, description="正文是否为 HTML 格式")
    attachments: Optional[List[str]] = Field(default_factory=list, description="附件文件的绝对路径列表")

class EmailSender_output_schema(output_schema):
    success: bool = Field(description="邮件是否发送成功")
    message: str = Field(description="执行结果详情或错误信息")

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
                message="【配置错误】SMTP 用户名或密码未设置。请通过 config 设置或环境变量配置。"
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
            return EmailSender_output_schema(success=True, message=f"邮件已成功发送至 {user_input.to_email}")
        except Exception as e:
            return EmailSender_output_schema(success=False, message=f"邮件发送失败: {str(e)}")

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
