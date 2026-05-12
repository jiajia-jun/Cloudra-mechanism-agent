from agent import Follower

class explorer(Follower):
    id: str = 'a-1'
    name: str = 'explorer'
    type: str = 'follower'
    prompt: str = '''
你是一个项目内容探索 agent。你的任务是探索项目结构并总结关键信息。
1. 使用 text_reader 读取项目的各个模块文件，了解项目的架构和实现细节。
2. 重点关注：agent.py, reAct.py, tools_class.py 等核心文件。
3. 在结果中清晰说明项目的整体结构和功能模块。
'''

    def has_read_permission(self) -> bool:
        return True
    
    def has_write_permission(self) -> bool:
        return False
    
    def script_run_permission(self) -> bool:
        return False
    
    def destructive_permission(self) -> bool:
        return False


def get_class():
    return explorer