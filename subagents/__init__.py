from pathlib import Path
import sys
import importlib.util
import pkgutil
import json

CURRENT_DIR = Path(__file__).parent

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

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        module = importlib.util.module_from_spec(spec)
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
    '''
    subagents = get_subagents_lst()
    subagents_dict = {}
    for subagent in subagents:
        subagents_dict[subagent.id] = subagent
    return subagents_dict

class Subagent_hash:
     
     def __init__(self):
         self.subagents_dict = get_dict()
         for subagent_id, subagent in self.subagents_dict.items():
             setattr(self, subagent_id, subagent)
