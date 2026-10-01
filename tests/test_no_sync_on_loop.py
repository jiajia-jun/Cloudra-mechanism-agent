"""静态护栏：async 函数体内禁止同步阻塞调用。

同步 sqlite3/subprocess/网络调用在事件循环线程上执行会冻结整个 loop，
曾造成跨进程 5 分钟级 "database is locked" 死锁。本测试用 AST 扫描
cloudra/ 下所有 async def 函数体（不下钻嵌套 def/lambda），命中禁止
名单即失败。确知安全的例外集中维护在 _ALLOWLIST，必须附理由。
"""

from __future__ import annotations

import ast
from pathlib import Path

CLOUDRA_ROOT = Path(__file__).resolve().parent.parent / "cloudra"

# {(相对路径, async 函数限定名): 理由}
_ALLOWLIST: dict[tuple[str, str], str] = {}


def _iter_async_functions(tree: ast.AST, prefix: str = ""):
    stack = [(child, prefix) for child in ast.iter_child_nodes(tree)]
    while stack:
        node, prefix = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}{node.name}"
            if isinstance(node, ast.AsyncFunctionDef):
                yield qualname, node
            prefix = f"{qualname}."
        stack.extend((child, prefix) for child in ast.iter_child_nodes(node))


def _calls_in_async_body(func: ast.AsyncFunctionDef):
    """遍历 async 函数体，不下钻嵌套 def / lambda（它们有自己的执行上下文）。"""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _violation(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        if func.id == "retry_on_locked":
            return "retry_on_locked (sync DB write retry)"
        return None
    if not isinstance(func, ast.Attribute):
        return None
    target = func.value
    if func.attr == "sleep" and isinstance(target, ast.Name) and target.id == "time":
        return "time.sleep"
    if func.attr == "run" and isinstance(target, ast.Name) and target.id == "subprocess":
        return "subprocess.run"
    if isinstance(target, ast.Name) and target.id == "requests":
        return f"requests.{func.attr}"
    if func.attr == "connect" and isinstance(target, (ast.Name, ast.Attribute)):
        # aiosqlite.connect 是异步连接器（返回 awaitable），不是同步阻塞
        if isinstance(target, ast.Name) and target.id == "aiosqlite":
            return None
        return f"{ast.unparse(target)}.connect (sync DB connect)"
    if func.attr == "retry_on_locked":
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
        for qualname, func in _iter_async_functions(tree):
            if (rel, qualname) in _ALLOWLIST:
                continue
            for call in _calls_in_async_body(func):
                kind = _violation(call)
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
        for qualname, _ in _iter_async_functions(tree):
            found.add((rel, qualname))
    stale = [key for key in _ALLOWLIST if key not in found]
    assert not stale, f"白名单中的条目已不存在: {stale}"


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
