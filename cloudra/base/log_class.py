import os

from cloudra.base.session_class import Session
from cloudra.infra.config import get_config


class Log:
    '''
    LOG类用于记录和管理reAct的日志信息，包括推理过程、行动结果和观察结果等。
    '''
    name: str = 'default.log'
    session: Session
    level: int
    is_main: bool
    path: str
    # 类级开关：TUI 模式置 False，终端输出改由 TUI 事件渲染器负责；
    # 日志文件写入不受此开关影响。
    terminal_output: bool = True

    def __init__(self, log_name: str = 'default.log', log_path: str = None):
        self.name = log_name
        if log_path:
            self.path = log_path
        else:
            self.path = os.path.join(get_config().data_dir, 'logs', log_name)
        self.session = None
        self.level = 0
        self.is_main = False
        # 流式输出期间持有的文件句柄（见 begin_stream/end_stream）
        self._stream_file = None

    def get_content(self) -> list:
        '''
        获取日志内容，返回一个列表。
        '''
        if os.path.exists(self.path):
            with open(self.path, 'r', encoding='utf-8') as f:
                content = f.readlines()
                return content
        else:
            with open(self.path, 'w', encoding='utf-8') as f:
                f.write('')
                return []

    def begin_stream(self) -> None:
        """流式输出开始时持有文件句柄，避免每个 token 都 open/write/close。"""
        if self._stream_file is None:
            self._stream_file = open(self.path, 'a', encoding='utf-8')

    def end_stream(self) -> None:
        """流式输出结束，关闭句柄（close 会顺带 flush 缓冲）。"""
        if self._stream_file is not None:
            self._stream_file.close()
            self._stream_file = None

    def update_content(self, new_content: str, print_to_console: bool = True) -> None:
        '''
        更新日志内容，追加新的内容。
        '''
        if print_to_console and self.is_main and Log.terminal_output:
            print(new_content, end='', flush=True)

        # 流式期间复用已持有的句柄；非流式维持原有一次一开的写法
        if self._stream_file is not None:
            self._stream_file.write(new_content)
            return
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(new_content)
