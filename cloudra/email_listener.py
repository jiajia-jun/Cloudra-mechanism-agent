import asyncio
import logging
import os
import re
import time

from cloudra.config import get_config
from cloudra.context_manager import ContextManager
from cloudra.conversation_class import Conversation
from cloudra.conversation_repo import latest_active_conversation
from cloudra.service import CloudraService
from cloudra.tools.Interactool.email_reader import EmailReader, EmailReader_input_schema

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="email_listener.log",
)
logger = logging.getLogger("EmailListener")

WAKEUP_PREFIX = "CLOUDRA:"


class EmailListener:
    def __init__(self, interval: int = 60):
        self.interval = interval
        self.config = get_config().email
        self.reader = EmailReader()
        self.service = CloudraService()

    def start(self):
        if not self.config.user or not self.config.password:
            print("[错误] 邮件配置不完整，请确保 SMTP/IMAP 用户名和密码已设置。")
            return

        print(f"[*] Cloudra 邮件唤醒监听中... (前缀: {WAKEUP_PREFIX})")

        while True:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"监听循环异常: {e}")

            time.sleep(self.interval)

    def _get_last_conversation_id(self) -> str:
        return latest_active_conversation()

    def _poll_once(self):
        emails = self.reader._read_imap(self.config, EmailReader_input_schema(count=1, only_unread=True))

        if not emails:
            return

        msg = emails[0]

        if self.config.whitelist:
            sender_email = msg.sender
            match = re.search(r"<(.*)>", sender_email)
            if match:
                sender_email = match.group(1)

            if sender_email not in self.config.whitelist:
                logger.warning(f"拦截到非法发件人的唤醒指令: {sender_email}")
                return

        subject = msg.subject.strip()
        body = msg.body.strip()

        query = None
        if subject.upper().startswith(WAKEUP_PREFIX):
            query = subject[len(WAKEUP_PREFIX):].strip()
        elif body.upper().startswith(WAKEUP_PREFIX):
            first_line = body.split("\n")[0]
            query = first_line[len(WAKEUP_PREFIX):].strip()

        if query:
            print(f"\n[!] 唤醒指令触发: {query} (来自: {msg.sender})")

            logger.warning(f"触发任务: {query} | 来源: {msg.sender}")

            try:
                conv_id = self._get_last_conversation_id()
                if conv_id:
                    conversation = Conversation(conv_id)
                    if conversation.state == "running":
                        asyncio.run(ContextManager.inject_event(
                            conversation_id=conv_id,
                            agent_id="a-0",
                            event_type="email",
                            content=f"收到来自 {msg.sender} 的新邮件，主题：{subject}，正文：{body}",
                        ))
                        print(f"[+] 已向运行中的会话 {conv_id} 注入邮件事件")
                        return
                asyncio.run(self.service.run_task(query, conversation_id=conv_id, interactive_approval=False))
            except Exception as e:
                logger.error(f"执行唤醒任务失败: {e}")
                print(f"[错误] 任务执行中断: {e}")


if __name__ == "__main__":
    interval = int(os.environ.get("CLOUDRA_POLL_INTERVAL", 60))
    listener = EmailListener(interval=interval)
    listener.start()
