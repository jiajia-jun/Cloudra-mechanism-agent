from agent import Follower

class researcher(Follower):
    id: str = 'a-3'
    name: str = 'researcher'
    type: str = 'follower'
    prompt: str = '''
你是一个学术研究 agent。你的任务是帮助用户进行文献调研和信息检索。
1. 使用 paper_searcher 在 arXiv 上搜索化学、材料科学相关学术论文。
2. 可以使用 bashtools 执行简单的终端命令（如 git clone 下载代码仓）。
3. 对于 PDF 文献，可以先用 bashtools 下载，再用 pdf2md 转换为 Markdown 阅读。
4. 返回结构化的信息：标题、作者、摘要、链接等。
'''

    def has_read_permission(self) -> bool:
        return True
    
    def has_write_permission(self) -> bool:
        return False
    
    def script_run_permission(self) -> bool:
        return True
    
    def destructive_permission(self) -> bool:
        return False


def get_class():
    return researcher