from agent import Follower

class writer(Follower):
    id: str = 'a-2'
    name: str = 'writer'
    type: str = 'follower'
    prompt: str = '''
你是一个文件写入 agent。你的任务是帮助用户写入或修改代码、文档等。
1. 使用 text_writer 将内容写入指定文件。
2. 合理规划文件结构，保持代码可维护性。
3. 注意文件编码和格式。
'''

    def has_read_permission(self) -> bool:
        return True
    
    def has_write_permission(self) -> bool:
        return True
    
    def script_run_permission(self) -> bool:
        return False
    
    def destructive_permission(self) -> bool:
        return True


def get_class():
    return writer