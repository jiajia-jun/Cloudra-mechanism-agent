"""静态护栏：async 函数体内禁止同步阻塞调用。

同步 sqlite3/subprocess/网络调用在事件循环线程上执行会冻结整个 loop，
曾造成跨进程 5 分钟级 "database is locked" 死锁。本测试用 AST 扫描
cloudra/ 下所有 async def 函数体（只下钻立即调用的 lambda），命中禁止
名单即失败。确知安全的例外集中维护在 _ALLOWLIST，必须附理由。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CLOUDRA_ROOT = Path(__file__).resolve().parent.parent / "cloudra"

# {(相对路径, async 函数限定名): 理由}
_ALLOWLIST: dict[tuple[str, str], str] = {}


def _iter_async_functions(tree: ast.AST, prefix: str = ""):
    aliases = _import_aliases(tree)
    stack = [(child, prefix, aliases) for child in ast.iter_child_nodes(tree)]
    while stack:
        node, prefix, aliases = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}{node.name}"
            aliases = {**aliases, **_import_aliases(node)}
            if isinstance(node, ast.AsyncFunctionDef):
                yield qualname, node, aliases
            prefix = f"{qualname}."
        stack.extend((child, prefix, aliases) for child in ast.iter_child_nodes(node))


def _calls_in_async_body(func: ast.AsyncFunctionDef):
    """跳过函数定义和延迟 lambda；立即调用的 lambda 在当前 loop 上运行。"""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
            # 立即执行的 lambda 在 loop 上运行；传给 to_thread 的 lambda
            # 仍只被当作定义，不能下钻误报。
            if isinstance(node.func, ast.Lambda):
                stack.append(node.func.body)
        stack.extend(ast.iter_child_nodes(node))


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """当前词法作用域的 import；不让兄弟函数局部名称污染模块。"""
    aliases = {}
    stack = list(ast.iter_child_nodes(tree))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                aliases[bound] = alias.name if alias.asname else bound
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        stack.extend(ast.iter_child_nodes(node))
    return aliases


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        target = _qualified_name(node.value, aliases)
        if target:
            return f"{target}.{node.attr}"
    return None


def _violation(call: ast.Call, aliases: dict[str, str]) -> str | None:
    name = _qualified_name(call.func, aliases)
    if name in {"time.sleep", "subprocess.run"}:
        return name
    if name and name.startswith("requests."):
        return name
    if name in {"sqlite3.connect", "sqlite3.dbapi2.connect"}:
        return f"{name} (sync DB connect)"
    if name == "retry_on_locked" or (name and name.endswith(".retry_on_locked")):
        return "retry_on_locked (sync DB write retry)"
    return None


def _collect_violations():
    violations = []
    for path in sorted(CLOUDRA_ROOT.rglob("*.py")):
        rel = path.relative_to(CLOUDRA_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for qualname, func, aliases in _iter_async_functions(tree):
            if (rel, qualname) in _ALLOWLIST:
                continue
            for call in _calls_in_async_body(func):
                kind = _violation(call, aliases)
                if kind:
                    violations.append(f"{rel}:{call.lineno} {qualname} -> {kind}")
    return violations


def test_no_sync_blocking_calls_in_async_code():
    violations = _collect_violations()
    assert not violations, (
        "async 函数体内发现同步阻塞调用（一律改用 asyncio.to_thread 或异步变体；"
        "确知安全的例外在 tests/test_no_sync_on_loop.py 的 _ALLOWLIST 登记并附理由）：\n"
        + "\n".join(violations)
    )


def test_allowlist_entries_exist():
    """白名单条目必须真实存在，防止改名后白名单变成死条目。"""
    found = set()
    for path in sorted(CLOUDRA_ROOT.rglob("*.py")):
        rel = path.relative_to(CLOUDRA_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for qualname, _, _ in _iter_async_functions(tree):
            found.add((rel, qualname))
    stale = [key for key in _ALLOWLIST if key not in found]
    assert not stale, f"白名单中的条目已不存在: {stale}"


@pytest.mark.parametrize("source,kind", [
    ("import time\nasync def bad():\n    time.sleep(1)", "time.sleep"),
    ("import time as clock\nasync def bad():\n    clock.sleep(1)", "time.sleep"),
    ("from time import sleep as pause\nasync def bad():\n    pause(1)", "time.sleep"),
    ("import subprocess as proc\nasync def bad():\n    proc.run(['true'])", "subprocess.run"),
    ("from subprocess import run\nasync def bad():\n    run(['true'])", "subprocess.run"),
    ("import sqlite3 as db\nasync def bad():\n    db.connect(':memory:')", "sqlite3.connect (sync DB connect)"),
    ("from sqlite3 import connect as open_db\nasync def bad():\n    open_db(':memory:')", "sqlite3.connect (sync DB connect)"),
    ("import requests as web\nasync def bad():\n    web.get('http://example.invalid')", "requests.get"),
    ("from requests import post\nasync def bad():\n    post('http://example.invalid')", "requests.post"),
    ("import time\nasync def bad():\n    (lambda: time.sleep(1))()", "time.sleep"),
    (
        "import asyncio, time\nasync def bad():\n    await asyncio.to_thread(time.sleep(1))",
        "time.sleep",
    ),
])
def test_guard_detects_known_sync_calls_with_import_aliases_and_direct_lambda(
    tmp_path, monkeypatch, source, kind,
):
    (tmp_path / "probe.py").write_text(source, encoding="utf-8")
    monkeypatch.setitem(globals(), "CLOUDRA_ROOT", tmp_path)
    violations = _collect_violations()
    assert len(violations) == 1
    assert violations[0].endswith(f" bad -> {kind}")


@pytest.mark.parametrize("source", [
    "async def good(client):\n    await client.connect()",
    "import aiosqlite as db\nasync def good():\n    await db.connect(':memory:')",
    "from aiosqlite import connect\nasync def good():\n    await connect(':memory:')",
    "import asyncio, time\nasync def good():\n    await asyncio.to_thread(lambda: time.sleep(1))",
    "import asyncio, time\nasync def good():\n    await asyncio.to_thread(time.sleep, 1)",
    "import time\nasync def good():\n    def worker():\n        time.sleep(1)",
])
def test_guard_does_not_report_async_connections_or_deferred_sync_work(
    tmp_path, monkeypatch, source,
):
    (tmp_path / "probe.py").write_text(source, encoding="utf-8")
    monkeypatch.setitem(globals(), "CLOUDRA_ROOT", tmp_path)
    assert _collect_violations() == []


def test_local_import_in_sibling_function_cannot_hide_a_sync_call(tmp_path, monkeypatch):
    (tmp_path / "probe.py").write_text(
        "import time\n"
        "async def blocking():\n    time.sleep(1)\n"
        "async def cooperative():\n    import asyncio as time\n    await time.sleep(1)\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "CLOUDRA_ROOT", tmp_path)
    assert _collect_violations() == ["probe.py:3 blocking -> time.sleep"]


def test_yolo_guard_tolerates_missing_message_history():
    """v2 的 LegacyToolExecutor 传入壳 bridge（无 message_history 等属性），
    YOLO 守卫必须容错而不是 AttributeError。"""
    import asyncio
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    from cloudra.infra.yolo_guard import YoloGuard

    class Shell:
        pass

    guard = YoloGuard.__new__(YoloGuard)
    guard.model = "test-model"
    mock_response = MagicMock()
    tool_call = MagicMock()
    tool_call.function.name = "submit_approval_decision"
    tool_call.function.arguments = json.dumps({"approved": True, "reason": "ok"})
    mock_response.choices[0].message.tool_calls = [tool_call]

    with patch.object(guard, "_client") as mock_client:
        mock_client.return_value.create = AsyncMock(return_value=mock_response)
        approved, _ = asyncio.run(guard.judge("bash", {"command": "ls"}, Shell(), None))

    assert approved is True
