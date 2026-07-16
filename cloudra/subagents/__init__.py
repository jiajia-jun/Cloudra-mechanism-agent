import importlib.util
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).parent

# 全局缓存，避免每次实例化 Subagent_hash 都重新扫描/导入子 agent 模块
_SUBAGENTS_DICT_CACHE = None


def get_subagents_lst():
    '''
    从 subagents 目录下递归加载子 agent 类，返回一个子 agent 类列表。
    遍历所有子目录中的 .py 文件，查找并调用 get_class() 获取类。
    '''
    subagents = []
    project_root = str(CURRENT_DIR.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    for py_file in CURRENT_DIR.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        # 把文件路径转成模块名，如 subagents.explorer
        rel_path = py_file.relative_to(CURRENT_DIR.parent)
        module_name = ".".join(rel_path.with_suffix("").parts)

        # 复用已加载的模块，避免重复执行 side-effects
        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        get_class = getattr(module, "get_class", None)
        if get_class is not None:
            subagent_class = get_class()
            # NOTE: subagent 模板实例化时需要 conversation_id，否则 Pydantic 校验失败。
            # 这里用 'default' 作为占位值，实际运行时会由调用方（如 SubAgentLauncher）覆盖。
            subagent_instance = subagent_class(query="", conversation_id='default')
            subagents.append(subagent_instance)

    return subagents

def get_dict():
    '''
    将子agent类加载为json，返回dict。
    使用模块级缓存，保证同进程内只加载一次。
    '''
    global _SUBAGENTS_DICT_CACHE
    if _SUBAGENTS_DICT_CACHE is None:
        subagents = get_subagents_lst()
        _SUBAGENTS_DICT_CACHE = {}
        for subagent in subagents:
            _SUBAGENTS_DICT_CACHE[subagent.id] = subagent
    return _SUBAGENTS_DICT_CACHE

class Subagent_hash:

     def __init__(self):
         self.subagents_dict = get_dict()
         for subagent_id, subagent in self.subagents_dict.items():
             setattr(self, subagent_id, subagent)
