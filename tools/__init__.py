import importlib.util
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).parent


def get_tools_lst():
    '''
    从 tools 目录下递归加载工具类，返回一个工具类列表。
    遍历所有子目录中的 .py 文件，查找并调用 get_class() 获取工具类。
    '''
    tools = []
    project_root = str(CURRENT_DIR.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    for py_file in CURRENT_DIR.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        # 把文件路径转成模块名，如 tools.Bashtool.bashtools
        rel_path = py_file.relative_to(CURRENT_DIR.parent)
        module_name = ".".join(rel_path.with_suffix("").parts)

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        get_class = getattr(module, "get_class", None)
        if get_class is not None:
            # NOTE: get_class() 返回 Tool 子类，再 () 一次得到实例。
            # 这是为了配合 tool_schema_json 改为实例方法：schema 生成需要实例级别的动态 description。
            # 副作用：所有工具必须支持无参实例化（目前均满足）。
            tools.append(get_class()())

    return tools
