import os
import json
import uuid
from datetime import datetime

from cloudra.config import get_config


class Conversation:
    """
    用户级会话容器，隔离不同对话的上下文和历史记录。
    一个 Conversation 包含：
      - contexts/   : 该会话下各 agent 的上下文文件
      - sessions/   : 该会话下 reAct 执行记录
      - meta.json   : 会话元数据（创建时间、最后活跃时间、状态）
    
    状态说明：
      - active  : 新建或刚恢复，尚未开始运行
      - running : Coordinator 正在运行中
      - sleeping: Coordinator 已完成任务，处于休眠等待唤醒状态
      - archived: 已归档，不再活跃
    """

    id: str
    path: str
    create_time: datetime
    last_active: datetime
    state: str = 'active'

    VALID_STATES = {'active', 'running', 'sleeping', 'archived'}

    def __init__(self, conv_id: str = None):
        data_dir = get_config().data_dir
        if conv_id:
            # 恢复已有对话
            self.id = conv_id
            self.path = os.path.join(data_dir, 'conversations', conv_id)
            self._load_meta()
        else:
            # 新建对话
            self.id = self._generate_id()
            self.path = os.path.join(data_dir, 'conversations', self.id)
            self.create_time = datetime.now()
            self.last_active = self.create_time
            self.state = 'active'
            self._ensure_dirs()
            self._save_meta()

    def _generate_id(self) -> str:
        return f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def _ensure_dirs(self):
        os.makedirs(os.path.join(self.path, 'contexts'), exist_ok=True)
        os.makedirs(os.path.join(self.path, 'sessions'), exist_ok=True)

    def _meta_path(self) -> str:
        return os.path.join(self.path, 'meta.json')

    def _save_meta(self):
        with open(self._meta_path(), 'w', encoding='utf-8') as f:
            json.dump({
                'id': self.id,
                'create_time': self.create_time.isoformat(),
                'last_active': self.last_active.isoformat(),
                'state': self.state,
            }, f, ensure_ascii=False, indent=4)

    def _load_meta(self):
        meta_path = self._meta_path()
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                self.create_time = datetime.fromisoformat(meta['create_time'])
                self.last_active = datetime.fromisoformat(meta['last_active'])
                self.state = meta.get('state', 'active')
        else:
            self.create_time = datetime.now()
            self.last_active = self.create_time
            self.state = 'active'

    def touch(self):
        """更新最后活跃时间并持久化。"""
        self.last_active = datetime.now()
        self._ensure_dirs()
        self._save_meta()

    def set_state(self, state: str):
        """更新会话状态，仅接受预定义状态。"""
        if state not in self.VALID_STATES:
            raise ValueError(f"无效的会话状态: {state}，必须是 {self.VALID_STATES} 之一")
        self.state = state
        self.touch()

    def get_context_path(self, agent_id: str) -> str:
        return os.path.join(self.path, 'contexts', f'{agent_id}.json')

    def get_session_path(self, session_id: str) -> str:
        return os.path.join(self.path, 'sessions', f'{session_id}.json')

    def list_contexts(self) -> list[str]:
        """列出该会话下所有已有的 agent context 文件。"""
        ctx_dir = os.path.join(self.path, 'contexts')
        if not os.path.exists(ctx_dir):
            return []
        return [f for f in os.listdir(ctx_dir) if f.endswith('.json')]

    def archive(self):
        """归档会话，不再活跃。"""
        self.set_state('archived')
