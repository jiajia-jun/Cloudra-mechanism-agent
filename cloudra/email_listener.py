import time
import os
import sys
import logging
import asyncio
import json
import re
from cloudra.config import get_config
from cloudra.main import run_task
from cloudra.conversation_class import Conversation
from cloudra.context_manager import ContextManager
from cloudra.tools.Interactool.email_reader import EmailReader, EmailReader_input_schema

# 设置静默日志：仅打印关键错误
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='email_listener.log'
)
logger = logging.getLogger("EmailListener")

# 唤醒指令前缀
WAKEUP_PREFIX = "CLOUDRA:"

class EmailListener:
    def __init__(self, interval: int = 60):
        self.interval = interval
        self.config = get_config().email
        
        # 初始化读取器所需的 dummy agent
        from cloudra.agent import Coordinator
        # 避免监听器启动时产生冗余的 context 文件
        self.dummy_agent = Coordinator(query="listener_init", conversation_id="system_listener")
        self.reader = EmailReader(subagent=self.dummy_agent)

    def start(self):
        """静默启动监听循环"""
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
        """获取最近一次活跃的 conversation id，优先使用配置中的 last_conversation_id。"""
        cfg = get_config()
        if cfg.last_conversation_id:
            return cfg.last_conversation_id
        # 否则从 conversations 目录找最新非归档的
        conv_dir = cfg.data_dir / "conversations"
        if not conv_dir.exists():
            return None
        candidates = []
        for entry in conv_dir.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if meta.get("state") in ("running", "sleeping", "active"):
                        candidates.append((meta.get("last_active", ""), entry.name))
                except Exception:
                    continue
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
        return None

    def _poll_once(self):
        # 仅读取 1 封最新的未读邮件
        # IMAP 的 _read_imap 方法在读取后会自动将邮件设为已读
        emails = self.reader._read_imap(self.config, EmailReader_input_schema(count=1, only_unread=True))
        
        if not emails:
            return

        msg = emails[0]
        
        # 白名单校验
        if self.config.whitelist:
            # 提取发件人邮箱 (处理 "Name <email@example.com>" 格式)
            sender_email = msg.sender
            match = re.search(r'<(.*)>', sender_email)
            if match:
                sender_email = match.group(1)
            
            if sender_email not in self.config.whitelist:
                logger.warning(f"拦截到非法发件人的唤醒指令: {sender_email}")
                return

        subject = msg.subject.strip()
        body = msg.body.strip()

        # 检测唤醒指令：优先查主题，其次查正文第一行
        query = None
        if subject.upper().startswith(WAKEUP_PREFIX):
            query = subject[len(WAKEUP_PREFIX):].strip()
        elif body.upper().startswith(WAKEUP_PREFIX):
            # 提取第一行作为指令，正文完整递送给agent
            first_line = body.split('\n')[0]
            query = first_line[len(WAKEUP_PREFIX):].strip()

        if query:
            print(f"\n[!] 唤醒指令触发: {query} (来自: {msg.sender})")
            
            # 记录到日志
            logger.warning(f"触发任务: {query} | 来源: {msg.sender}")

            try:
                conv_id = self._get_last_conversation_id()
                if conv_id:
                    conversation = Conversation(conv_id)
                    if conversation.state == 'running':
                        # 会话正在运行，注入邮件事件到 Coordinator 上下文
                        asyncio.run(ContextManager.inject_event(
                            conversation_id=conv_id,
                            agent_id='a-0',
                            event_type='email',
                            content=f"收到来自 {msg.sender} 的新邮件，主题：{subject}，正文：{body}"
                        ))
                        print(f"[+] 已向运行中的会话 {conv_id} 注入邮件事件")
                        return
                # 未找到运行中会话，启动新任务
                # 注意：此处为同步执行，执行期间监听会暂停，防止并发冲突
                run_task(body, verbose=True)
            except Exception as e:
                logger.error(f"执行唤醒任务失败: {e}")
                print(f"[错误] 任务执行中断: {e}")

if __name__ == "__main__":
    # 可以通过环境变量自定义轮询间隔
    interval = int(os.environ.get("CLOUDRA_POLL_INTERVAL", 60))
    listener = EmailListener(interval=interval)
    listener.start()
