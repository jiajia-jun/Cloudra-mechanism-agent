
import os
from datetime import datetime

from cloudra.persistence.fs_utils import atomic_write_json


class Session:
    """内存态会话镜像；数据库（session 表）是唯一持久化事实来源。

    默认不再写 per-session JSON 快照文件；调试时可设置环境变量
    ``CLOUDRA_DEBUG_SESSION_JSON=1`` 恢复写文件行为（upload_json 仍可显式调用）。
    """
    id: str
    path: str
    create_time: datetime
    state: str = 'sleeping'

    def __init__(self, id: str, path: str) -> None:
        self.create_time = datetime.now()
        self.id = id
        self.path = path
        self.state = 'sleeping'
        if os.environ.get("CLOUDRA_DEBUG_SESSION_JSON") == "1":
            dir_name = os.path.dirname(self.path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            self.upload_json()


    def to_json(self) -> dict:
        create_time = self.create_time
        if isinstance(create_time, datetime):
            create_time = create_time.isoformat()
        json_dict = {
            'id': self.id,
            'path': self.path,
            'create_time': create_time,
            'state': self.state,
        }
        return json_dict

    def upload_json(self):
        atomic_write_json(self.path, self.to_json())

