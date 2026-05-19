import os
from cloudra.session_class import Session
from cloudra.config import get_config

class Log:
    '''
    LOG类用于记录和管理reAct的日志信息，包括推理过程、行动结果和观察结果等。
    '''
    name: str = 'default.log'
    session: Session
    level: int
    is_main: bool
    path: str

    def __init__(self, log_name: str = 'default.log', log_path: str = None):
        self.name = log_name
        if log_path:
            self.path = log_path
        else:
            self.path = os.path.join(get_config().data_dir, 'logs', log_name)
        self.session = None
        self.level = 0
        self.is_main = False

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

    def update_content(self, new_content: str, print_to_console: bool = True) -> None:
        '''
        更新日志内容，追加新的内容。
        '''
        if print_to_console and self.is_main:
            print(new_content, end='', flush=True)
            
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(new_content)
