import importlib.util
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).parent

_TOOLS_CACHE = None

def get_tools_lst():
    '''
    从 tools 目录下递归加载工具类，返回一个工具类列表。
    遍历所有子目录中的 .py 文件，查找并调用 get_class() 获取工具类。
    使用全局缓存确保每个进程只加载一次模块。
    '''
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    tools = []
    project_root = str(CURRENT_DIR.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    for py_file in CURRENT_DIR.rglob("*.py"):
        # 排除 __init__.py、__pycache__ 以及核心依赖目录 core
        if py_file.name == "__init__.py" or "__pycache__" in str(py_file) or "core" in py_file.parts:
            continue

        # 把文件路径转成模块名，如 tools.Bashtool.bashtools
        try:
            rel_path = py_file.relative_to(CURRENT_DIR.parent)
            module_name = ".".join(rel_path.with_suffix("").parts)

            # 使用标准的 import_module 或 spec 加载
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            # 在执行前放入 sys.modules 是标准的，但我们要防止重复执行
            if module_name not in sys.modules:
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            else:
                module = sys.modules[module_name]

            get_class_func = getattr(module, "get_class", None)
            if get_class_func is not None:
                tools.append(get_class_func()())
        except Exception as e:
            # 记录错误但不中断整体加载
            print(f"警告: 加载工具 {py_file} 失败: {e}")

    _TOOLS_CACHE = tools
    return tools
