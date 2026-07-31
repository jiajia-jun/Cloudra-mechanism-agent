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
from cloudra.tools.Interactool.email_sender import EmailSender, EmailSender_input_schema

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
        emails = self.reader._read_imap(
            self.config,
            EmailReader_input_schema(count=1, only_unread=True),
            mark_seen=True,
        )

        if not emails:
            return

        msg = emails[0]

        sender_email = msg.sender
        match = re.search(r"<(.*)>", sender_email or "")
        if match:
            sender_email = match.group(1)

        if self.config.whitelist:
            if sender_email not in self.config.whitelist:
                logger.warning(f"拦截到非法发件人的唤醒指令: {sender_email}")
                return

        subject = msg.subject.strip()
        body = msg.body.strip()

        query = None
        if subject.upper().startswith(WAKEUP_PREFIX):
            instruction = subject[len(WAKEUP_PREFIX):].strip()
            # 主题指令 + 完整正文（正文不再是摆设）
            query = instruction
            if body:
                query = f"{instruction}\n\n{body}" if instruction else body
        elif body.upper().startswith(WAKEUP_PREFIX):
            lines = body.split("\n")
            instruction = lines[0][len(WAKEUP_PREFIX):].strip()
            rest = "\n".join(lines[1:]).strip()
            query = f"{instruction}\n{rest}".strip() if rest else instruction

        if query:
            # 附上发件人地址，agent 需要主动回邮/回复时知道对象是谁
            query = f"{query}\n\n[邮件来源: {sender_email}]"
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
                asyncio.run(self._run_and_reply(query, conv_id, msg))
            except Exception as e:
                logger.error(f"执行唤醒任务失败: {e}")
                print(f"[错误] 任务执行中断: {e}")

    async def _run_and_reply(self, query: str, conv_id, msg):
        """执行唤醒任务并把结果回邮给发件人（远程无人值守场景的闭环）。"""
        result = await self.service.run_task(query, conversation_id=conv_id, interactive_approval=False)

        sender_email = msg.sender
        match = re.search(r"<(.*)>", sender_email or "")
        if match:
            sender_email = match.group(1)
        if not sender_email:
            logger.warning("无法解析发件人地址，跳过回邮")
            return

        body = result or "（任务已完成，无文本结果）"
        if len(body) > 5000:
            body = body[:5000] + "\n\n[... 结果过长已截断，完整内容请到会话中查看 ...]"

        out = await EmailSender().tool_call(EmailSender_input_schema(
            to_email=sender_email,
            subject=f"Re: {msg.subject}",
            body=body,
        ), None)
        if out.success:
            print(f"[+] 结果已回邮至 {sender_email}")
            logger.warning(f"结果已回邮至 {sender_email}")
        else:
            logger.error(f"回邮失败: {out.message}")


if __name__ == "__main__":
    interval = int(os.environ.get("CLOUDRA_POLL_INTERVAL", 60))
    listener = EmailListener(interval=interval)
    listener.start()
