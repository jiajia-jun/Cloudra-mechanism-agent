import asyncio
import email
import imaplib
from email.header import decode_header
from typing import Any, List, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config

description = (
    "从收件箱读取最新邮件，可按发件人过滤、指定数量、只看未读。"
    "适用：查看用户的远程回复或指令更新。"
    "不适用：发送邮件（用 email_sender）。需要在配置中先配好 IMAP 邮箱凭据。"
)

class EmailReader_input_schema(input_schema):
    count: int = Field(default=5, description="读取最近邮件的数量")
    filter_sender: Optional[str] = Field(default=None, description="可选：按发件人邮箱过滤")
    only_unread: bool = Field(default=True, description="是否仅读取未读邮件")

class EmailMessage(output_schema):
    subject: str
    sender: str
    date: str
    body: str

class EmailReader_output_schema(output_schema):
    success: bool = Field(description="是否成功读取邮件")
    emails: List[EmailMessage] = Field(default_factory=list, description="读取到的邮件列表")
    message: str = Field(description="状态或错误信息")

class EmailReader(Tool):
    tool_id: str = 't-30'
    tool_name: str = 'email_reader'
    tool_description: str = description
    input_schema: Any = EmailReader_input_schema
    output_schema: Any = EmailReader_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: EmailReader_input_schema, session: Session) -> EmailReader_output_schema:
        config = get_config().email

        if not config.user or not config.password:
            return EmailReader_output_schema(
                success=False,
                message="【配置错误】IMAP 用户名或密码未设置。"
            )

        try:
            emails = await asyncio.to_thread(self._read_imap, config, user_input)
            return EmailReader_output_schema(
                success=True,
                emails=emails,
                message=f"成功读取 {len(emails)} 封邮件"
            )
        except Exception as e:
            return EmailReader_output_schema(success=False, message=f"读取邮件失败: {str(e)}")

    def _read_imap(self, config, user_input, mark_seen: bool = False) -> List[EmailMessage]:
        r"""同步执行 IMAP 读取。

        mark_seen=True 时把读取过的邮件显式置 \Seen（部分服务器如 QQ 邮箱
        不会在 fetch 后自动标记已读，监听器依赖此避免重复触发）。
        """
        mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        mail.login(config.user, config.password)
        mail.select("inbox")

        # 构建搜索准则
        search_criteria = "UNSEEN" if user_input.only_unread else "ALL"
        if user_input.filter_sender:
            search_criteria = f'({search_criteria} FROM "{user_input.filter_sender}")'

        status, messages = mail.search(None, search_criteria)
        if status != "OK":
            return []

        email_ids = messages[0].split()
        # 仅取最近的 count 封
        email_ids = email_ids[-user_input.count:]
        email_ids.reverse()

        result_list = []
        for e_id in email_ids:
            status, data = mail.fetch(e_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            if mark_seen:
                mail.store(e_id, '+FLAGS', '\\Seen')
            msg = email.message_from_bytes(raw_email)

            # 解码主题
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else "utf-8")

            sender = msg.get("From")
            date = msg.get("Date")

            # 提取正文
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                body = msg.get_payload(decode=True).decode()

            result_list.append(EmailMessage(
                subject=subject,
                sender=sender,
                date=date,
                body=body
            ))

        mail.close()
        mail.logout()
        return result_list

def get_class():
    return EmailReader
