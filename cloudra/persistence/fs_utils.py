"""原子文件写入工具。

非原子写（``open(path, 'w')`` 先截断再写）会在写入中途留下"半截文件"：
并发读者（TUI 状态栏、其它进程读 JSONL 历史等）会读到残缺内容，
导致 JSON 解析失败，甚至被误当作"文件损坏"而触发破坏性回退。

原子写把内容先写入同目录的临时文件，写完再 ``os.replace`` 一步切换，
对读者而言文件永远要么是旧的完整版本、要么是新的完整版本。
"""

import json
import os
import tempfile
from typing import Any, Iterable


def atomic_write_bytes(path: str, data: bytes, *, mode: int | None = None) -> None:
    """原子写入二进制内容到 ``path``。

    临时文件用 ``tempfile.mkstemp`` 生成唯一名称，避免多个写者撞用同一
    临时文件相互截断；写入成功后 ``os.replace`` 原子替换，失败时清理残留。
    目标文件已存在时沿用其权限位，避免 mkstemp 默认 0600 改变文件属性；
    ``mode`` 显式指定时覆盖该默认。
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if mode is None:
            try:
                mode = os.stat(path).st_mode & 0o777
            except OSError:
                mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: str, content: str, encoding: str = "utf-8", *, mode: int | None = None
) -> None:
    """原子写入文本内容到 ``path``。"""
    atomic_write_bytes(path, content.encode(encoding), mode=mode)


def atomic_write_json(
    path: str,
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 2,
) -> None:
    """原子写入 JSON 数据到 ``path``。"""
    text = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, text)


def atomic_write_jsonl(path: str, items: Iterable[Any]) -> None:
    """原子写入 JSONL（每行一个 JSON 值，不带缩进）到 ``path``。"""
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    atomic_write_text(path, text)
