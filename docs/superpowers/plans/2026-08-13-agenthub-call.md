# AgentHub directory / call Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `agent_hub` `directory` and `call` so any agent can see who is doing what and phone another session or role without treating the consult as a Coordinator delivery.

**Architecture:** Keep the existing `agent_hub` tool. Pure helpers live in `cloudra/tools/Managetool/_hub_call.py` (format, resolve, directory listing, deliver user-line). Spawn reuses `dispatch_subagent` with an `extra_payload` flag `origin=hub_call`. Visit appends `role=user` then `inject_event(user_message)` and resumes a follower the same way TUI append does. Executor skips the “已完成。结论” Coordinator wakeup when `origin` is `hub_call` and instead injects a hang-up user line to the caller.

**Tech Stack:** Python >= 3.11, existing `ConversationDB` / aiosqlite, `ContextManager`, `dispatch_subagent`, pytest-asyncio. No new dependencies.

## Global Constraints

- Do not expose a `query` field on `agent_hub` input. Directory rows use `task`; call speech uses `message`; posts keep `content`.
- Incoming call is exactly one `role=user` line (template below). No `[来电]` pin, no harness `stop` reject.
- Do not interrupt an in-flight LLM/tool turn.
- Followers do not gain `SubAgentLauncher` / `MANAGE`.
- `a-0` / `coordinator` always visits the existing Coordinator session; never spawn a second Coordinator.
- Exact `agent_id` or registry class name always **spawns**; visiting a live specialist requires its `session_id`.
- `origin=hub_call` `stop` must not send Coordinator `子 Agent … 已完成。结论:`.
- Do not rewrite `small_mol.md` / `dft.md` / other role files.
- Do not git commit unless the user explicitly asked in that session (AGENTS.md). Skip every Commit step otherwise.
- Do not run the full suite. Run only the focused pytest commands in each task.
- Incoming template (caller fills `{message}` only):

```
【来电】{caller_agent_id} 打给你（session={caller_session_id}）。请第一时间回应这通来电（正文或 agent_hub call/post），不要先查计算、改提醒或 stop。

{message}
```

## File map

- Create: `cloudra/tools/Managetool/_hub_call.py` — format, resolve, directory SQL, deliver/resume helpers.
- Modify: `cloudra/tools/Managetool/agent_hub.py` — schema, description, `directory` / `call` actions.
- Modify: `cloudra/tools/Managetool/_subagent_dispatch.py` — `extra_payload` merge into request payload.
- Modify: `cloudra/runtime/executor.py` — hang-up vs Coordinator delivery wakeup.
- Modify: `cloudra/runtime/prompt_assembler.py` — `_AGENT_HUB_GUIDANCE`.
- Modify: `cloudra/core/agent.py` — `_REVIVED_AFTER_STOP_NOTICE` one clause.
- Modify: `cloudra/prompts/coordinator.md` — drop “子 Agent 之间不允许直接通信”.
- Test: `tests/test_agent_hub.py` — directory, resolve, visit inject, spawn, validation.
- Test: `tests/test_executor_finalize.py` — `origin=hub_call` does not wake Coordinator as delivery.
- Test: `tests/test_plan_tools.py` — revived notice mentions 来电.
- Test: `tests/test_prompt_assembler.py` — hub guidance mentions `directory` / `call`.

---

### Task 1: Format, resolve, directory

**Files:**
- Create: `cloudra/tools/Managetool/_hub_call.py`
- Modify: `cloudra/tools/Managetool/agent_hub.py`
- Test: `tests/test_agent_hub.py`

**Interfaces:**
- Produces:
  - `INCOMING_CALL_TEMPLATE: str`
  - `format_incoming_call(*, caller_agent_id: str, caller_session_id: str, message: str, post_line: str | None = None) -> str`
  - `resolve_call_target(to: str, *, db: ConversationDB) -> tuple[str, dict]`
    - `("visit", {"session_id": str, "agent_id": str})`
    - `("spawn", {"agent_id": str})`
    - `("error", {"message": str})`
  - `async def list_directory(db: ConversationDB) -> list[dict]` each dict: `session_id`, `agent_id`, `agent_type`, `state`, `task`
- Consumes: `session` table (`query` column internally), `_resolve_agent_id` from `agent_hub.py` (move it into `_hub_call.py` and re-export from `agent_hub.py` so existing tests keep importing from `agent_hub` if they do; currently tests do not import `_resolve_agent_id`).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_agent_hub.py`:

```python
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Managetool._hub_call import (
    format_incoming_call,
    list_directory,
    resolve_call_target,
)


def test_format_incoming_call_is_user_speech_not_a_prompt():
    text = format_incoming_call(
        caller_agent_id="a-0",
        caller_session_id="a-0_run1",
        message="POZ 有虚频，怎么位移？",
    )
    assert text.startswith("【来电】")
    assert "a-0" in text and "a-0_run1" in text
    assert "第一时间" in text
    assert "POZ 有虚频，怎么位移？" in text
    assert "【来电】" in text.split("POZ", 1)[0]


def test_format_incoming_call_optional_post_line():
    text = format_incoming_call(
        caller_agent_id="a-4",
        caller_session_id="a-4_task1",
        message="看这个",
        post_line="对照帖子 #3（主题 虚频）。",
    )
    assert "对照帖子 #3" in text


@pytest.mark.asyncio
async def test_directory_exposes_task_not_query(tmp_path):
    db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-0_run1', 'a-0', 'coordinator', '乙烯臭氧化', 'running')"
        )
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4_task1', 'a-4', 'follower', 'opt POZ', 'waiting')"
        )
        con.commit()
    rows = await list_directory(db)
    by_id = {r["session_id"]: r for r in rows}
    assert by_id["a-0_run1"]["task"] == "乙烯臭氧化"
    assert "query" not in by_id["a-0_run1"]
    assert by_id["a-4_task1"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_resolve_call_target_visit_spawn_coordinator(tmp_path):
    db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-0_run1', 'a-0', 'coordinator', '主任务', 'running')"
        )
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'running')"
        )
        con.commit()
    kind, data = resolve_call_target("a-4_task1", db=db)
    assert kind == "visit" and data["session_id"] == "a-4_task1" and data["agent_id"] == "a-4"
    kind, data = resolve_call_target("a-4", db=db)
    assert kind == "spawn" and data["agent_id"] == "a-4"
    kind, data = resolve_call_target("small_mol", db=db)
    assert kind == "spawn" and data["agent_id"] == "a-4"
    kind, data = resolve_call_target("coordinator", db=db)
    assert kind == "visit" and data["agent_id"] == "a-0" and data["session_id"] == "a-0_run1"
    kind, data = resolve_call_target("a-0", db=db)
    assert kind == "visit" and data["agent_id"] == "a-0"
    kind, data = resolve_call_target("nobody", db=db)
    assert kind == "error"
```

Also extend `TestAgentHub.test_validation` after implementation so `action="directory"` succeeds; in this task add:

```python
    async def test_directory_action_lists_sessions(self, agent, mock_session, tmp_path, monkeypatch):
        from cloudra.infra.config import get_config
        get_config()._ensure_dirs()
        db = ConversationDB(agent.conversation_id).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
                "VALUES ('a-0_x', 'a-0', 'coordinator', '主任务', 'running')"
            )
            con.commit()
        tool = AgentHub(subagent=agent)
        out = await tool.tool_call(AgentHub_input_schema(action="directory"), mock_session)
        assert out.is_success
        assert any(r.get("task") == "主任务" for r in out.sessions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_agent_hub.py::test_format_incoming_call_is_user_speech_not_a_prompt tests/test_agent_hub.py::test_directory_exposes_task_not_query tests/test_agent_hub.py::test_resolve_call_target_visit_spawn_coordinator tests/test_agent_hub.py::TestAgentHub::test_directory_action_lists_sessions`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `_hub_call`, or `AgentHub_output_schema` has no `sessions`.

- [ ] **Step 3: Implement helpers and wire `directory`**

Create `cloudra/tools/Managetool/_hub_call.py`:

```python
"""AgentHub directory / call helpers. No `query` on the tool wire."""

from __future__ import annotations

from cloudra.persistence.database import ConversationDB, aretry_on_locked
from cloudra.subagents.registry import SUBAGENT_REGISTRY

INCOMING_CALL_TEMPLATE = (
    "【来电】{caller_agent_id} 打给你（session={caller_session_id}）。"
    "请第一时间回应这通来电（正文或 agent_hub call/post），"
    "不要先查计算、改提醒或 stop。\n\n{message}"
)


def format_incoming_call(
    *,
    caller_agent_id: str,
    caller_session_id: str,
    message: str,
    post_line: str | None = None,
) -> str:
    text = INCOMING_CALL_TEMPLATE.format(
        caller_agent_id=caller_agent_id,
        caller_session_id=caller_session_id or "unknown",
        message=message.strip(),
    )
    if post_line:
        text = f"{text}\n{post_line}"
    return text


def resolve_agent_id(target: str) -> str | None:
    t = target.strip()
    if not t:
        return None
    if t.lower() in ("coordinator", "a-0"):
        return "a-0"
    if t.startswith("a-") and "_" not in t[2:] and t[2:].replace("-", "").isdigit() is False:
        # a-4 is an id; a-4_task1 is a session_id. Digit check: agent ids are a-<n>.
        rest = t[2:]
        if rest.isdigit():
            return t
    if t.startswith("a-") and t[2:].isdigit():
        return t
    for reg in SUBAGENT_REGISTRY:
        if reg.class_name == t:
            return reg.agent_id
    return None


def resolve_call_target(to: str, *, db: ConversationDB) -> tuple[str, dict]:
    raw = (to or "").strip()
    if not raw:
        return "error", {"message": "call 需要非空的 to。"}
    lowered = raw.lower()
    if lowered in ("coordinator", "a-0"):
        row = _latest_coordinator(db)
        if row is None:
            return "error", {"message": "本对话没有 Coordinator session。"}
        return "visit", {"session_id": row[0], "agent_id": "a-0"}
    session_row = _session_row(db, raw)
    if session_row is not None:
        return "visit", {"session_id": session_row[0], "agent_id": session_row[1] or ""}
    agent_id = resolve_agent_id(raw)
    if agent_id == "a-0":
        row = _latest_coordinator(db)
        if row is None:
            return "error", {"message": "本对话没有 Coordinator session。"}
        return "visit", {"session_id": row[0], "agent_id": "a-0"}
    if agent_id is not None:
        return "spawn", {"agent_id": agent_id}
    return "error", {"message": f"未知的 to: {raw}"}


def _session_row(db: ConversationDB, session_id: str):
    with db.connect() as con:
        return con.execute(
            "SELECT session_id, agent_id, agent_type, state, query FROM session WHERE session_id=?",
            (session_id,),
        ).fetchone()


def _latest_coordinator(db: ConversationDB):
    with db.connect() as con:
        return con.execute(
            "SELECT session_id, agent_id FROM session WHERE agent_id='a-0' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()


async def list_directory(db: ConversationDB) -> list[dict]:
    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT session_id, agent_id, agent_type, state, query FROM session "
                "ORDER BY created_at DESC"
            )
            return await cur.fetchall()

    rows = await aretry_on_locked(query)
    return [
        {
            "session_id": r[0],
            "agent_id": r[1],
            "agent_type": r[2],
            "state": r[3],
            "task": r[4] or "",
        }
        for r in rows
    ]
```

Fix `resolve_agent_id`: do **not** treat `a-4_task1` as an agent id. Implementation:

```python
def resolve_agent_id(target: str) -> str | None:
    t = target.strip()
    if not t:
        return None
    if t.lower() in ("coordinator", "a-0"):
        return "a-0"
    if t.startswith("a-") and t[2:].isdigit():
        return t
    for reg in SUBAGENT_REGISTRY:
        if reg.class_name == t:
            return reg.agent_id
    return None
```

`resolve_call_target` must check the session table **before** `resolve_agent_id` for strings like `a-4_task1` (already does).

In `agent_hub.py`:

- Move `_resolve_agent_id` to call `resolve_agent_id` from `_hub_call` (keep the old name as an alias so notify still works):

```python
from cloudra.tools.Managetool._hub_call import (
    list_directory,
    resolve_agent_id,
    resolve_call_target,
)

def _resolve_agent_id(target: str) -> str | None:
    return resolve_agent_id(target)
```

- Update `description` to mention `directory` and `call` (`to` + `message`, optional `post_id`; no `query`).
- `AgentHub_input_schema.action` description: `post / browse / read / search / directory / call`
- Add fields (no `query`):

```python
    to: str = Field(default="", description="call 目标：session_id、agent_id（如 a-4）、角色名（如 small_mol）或 coordinator")
    message: str = Field(default="", description="call 时你要对对面说的话（不是角色 prompt）")
```

`post_id` already exists.

- `AgentHub_output_schema` add:

```python
    sessions: list = Field(default_factory=list, description="directory 结果")
    session_id: str = Field(default="", description="call 结果：对方 session_id")
```

- In `tool_call`, dispatch:

```python
        if action == "directory":
            rows = await list_directory(db)
            return AgentHub_output_schema(
                is_success=True,
                sessions=rows,
                message=f"共 {len(rows)} 个 session。" if rows else "当前没有 session。",
            )
        if action == "call":
            return await self._call(db, user_input)  # stub raising NotImplemented in this task? 
```

For this task only, `_call` may return `is_success=False, message="call 尚未实现"` — **do not**. Instead leave `call` for Task 2 and let unknown-action still fail. `test_validation` uses `teleport`; `call` without implementation would be a new action that currently hits “未知 action”. Do **not** add `call` to the dispatcher until Task 2. Only add `directory` in this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/test_agent_hub.py`

Expected: PASS (existing notify tests still pass; `_resolve_agent_id` alias must keep `small_mol` → `a-4`).

- [ ] **Step 5: Commit** — skip unless the user asked.

---

### Task 2: `call` visit injects `role=user`

**Files:**
- Modify: `cloudra/tools/Managetool/_hub_call.py`
- Modify: `cloudra/tools/Managetool/agent_hub.py`
- Test: `tests/test_agent_hub.py`

**Interfaces:**
- Consumes: `format_incoming_call`, `resolve_call_target` from Task 1.
- Produces: `async def deliver_incoming_call(*, conversation_id, callee_agent_id, callee_session_id, text, db_path) -> None` which `ContextManager.append({"role":"user","content": text})` then `inject_event(event_type="user_message", content=text, session_id=callee_session_id)`.
- Coordinator context file uses `session_id=None` when `callee_agent_id == "a-0"` (same as `append_session_message_command`).

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_call_visit_appends_user_incoming_not_system_wrapper(
    agent, mock_session, tmp_path, monkeypatch
):
    import os
    from pathlib import Path
    from cloudra.persistence.context_manager import ContextManager

    runtime_dir = Path(f"/tmp/cr{os.getpid()}hub")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    db = ConversationDB(agent.conversation_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'running')"
        )
        con.commit()
    agent.session_id = "a-hub_s"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(AgentHub_input_schema(
        action="call", to="a-4_task1", message="POZ 有虚频，怎么位移？",
    ), mock_session)
    assert out.is_success
    assert out.session_id == "a-4_task1"

    cm = ContextManager(
        agent_id="a-4",
        conversation_id=agent.conversation_id,
        prompt=None,
        query="",
        session_id="a-4_task1",
    )
    stored = await cm.load()
    user_hits = [
        m for m in stored
        if m.get("role") == "user" and "【来电】" in str(m.get("content", ""))
    ]
    system_hits = [
        m for m in stored
        if m.get("role") == "system" and (
            "【来电】" in str(m.get("content", ""))
            or "【hub_message】" in str(m.get("content", ""))
            or "【user_message】" in str(m.get("content", ""))
        )
    ]
    assert len(user_hits) == 1
    assert "POZ 有虚频" in user_hits[0]["content"]
    assert system_hits == []


@pytest.mark.asyncio
async def test_call_empty_message_fails(agent, mock_session):
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(AgentHub_input_schema(
        action="call", to="a-4", message="",
    ), mock_session)
    assert not out.is_success


@pytest.mark.asyncio
async def test_call_missing_post_id_still_visits(agent, mock_session, monkeypatch):
    import os
    from pathlib import Path
    runtime_dir = Path(f"/tmp/cr{os.getpid()}hub2")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    db = ConversationDB(agent.conversation_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'running')"
        )
        con.commit()
    agent.session_id = "a-hub_s"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(AgentHub_input_schema(
        action="call", to="a-4_task1", message="看一下", post_id=999,
    ), mock_session)
    assert out.is_success
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_agent_hub.py::test_call_visit_appends_user_incoming_not_system_wrapper tests/test_agent_hub.py::test_call_empty_message_fails tests/test_agent_hub.py::test_call_missing_post_id_still_visits`

Expected: FAIL (`未知 action: call` or no user line).

- [ ] **Step 3: Implement visit `call`**

In `_hub_call.py`:

```python
async def deliver_incoming_call(
    *,
    conversation_id: str,
    callee_agent_id: str,
    callee_session_id: str,
    text: str,
    db_path: str,
) -> None:
    from cloudra.persistence.context_manager import ContextManager

    context_session_id = None if callee_agent_id == "a-0" else callee_session_id
    cm = ContextManager(
        agent_id=callee_agent_id,
        conversation_id=conversation_id,
        prompt=None,
        query="",
        session_id=context_session_id,
        db_path=db_path,
    )
    await cm.append({"role": "user", "content": text})
    await ContextManager.inject_event(
        conversation_id=conversation_id,
        agent_id=callee_agent_id,
        event_type="user_message",
        content=text,
        db_path=db_path,
        session_id=callee_session_id,
    )
```

Optional post line helper:

```python
async def optional_post_line(db: ConversationDB, post_id: int | None) -> str | None:
    if not post_id:
        return None
    row = await AgentHub._get_post(db, post_id)  # avoid cycle — duplicate the SELECT here
```

Do **not** import `AgentHub` from `_hub_call`. Copy the small SELECT from `_get_post` into `_hub_call.lookup_post(db, post_id) -> dict | None`. If None, return `None` (call still happens, no pointer).

In `agent_hub.py` `_call`:

```python
    async def _call(self, db, user_input):
        spoken = user_input.message.strip()
        if not spoken:
            return AgentHub_output_schema(is_success=False, message="call 需要非空的 message。")
        kind, data = resolve_call_target(user_input.to, db=db)
        if kind == "error":
            return AgentHub_output_schema(is_success=False, message=data["message"])
        if kind == "spawn":
            return AgentHub_output_schema(is_success=False, message="spawn 尚未实现")  # Task 3
        # visit
        caller_agent = getattr(self.subagent, "id", None) or getattr(self.subagent, "name", "unknown")
        caller_session = getattr(self.subagent, "session_id", None) or ""
        post_line = None
        if user_input.post_id:
            post = await lookup_post(db, user_input.post_id)
            if post is not None:
                post_line = f"对照帖子 #{post['id']}（主题 {post['topic']}）。"
        text = format_incoming_call(
            caller_agent_id=str(caller_agent),
            caller_session_id=str(caller_session),
            message=spoken,
            post_line=post_line,
        )
        await deliver_incoming_call(
            conversation_id=getattr(self.subagent, "conversation_id", "default"),
            callee_agent_id=data["agent_id"],
            callee_session_id=data["session_id"],
            text=text,
            db_path=_tool_db_path(self.subagent),
        )
        return AgentHub_output_schema(
            is_success=True,
            session_id=data["session_id"],
            message=f"已呼叫 {data['session_id']}（不阻塞）。",
        )
```

Do **not** leave a “spawn 尚未实现” in the merged tree after Task 3; in this task the spawn tests are not added yet. If `kind == "spawn"` in this task, return a clear error `"spawn 将在后续实现"` **only if** you have not started Task 3. Prefer implementing spawn in Task 3 immediately after; if a test calls `to=a-4` here (`test_call_empty_message` uses `to=a-4` with empty message — that fails before resolve). Good.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/test_agent_hub.py`

Expected: PASS.

- [ ] **Step 5: Commit** — skip unless the user asked.

---

### Task 3: `call` spawn (non-blocking, `origin=hub_call`)

**Files:**
- Modify: `cloudra/tools/Managetool/_subagent_dispatch.py`
- Modify: `cloudra/tools/Managetool/_hub_call.py`
- Modify: `cloudra/tools/Managetool/agent_hub.py`
- Test: `tests/test_agent_hub.py`

**Interfaces:**
- Consumes: `dispatch_subagent(...)` existing kwargs.
- Produces: `dispatch_subagent(..., extra_payload: dict | None = None)` merged into `base_payload` before `acreate_subagent_request`. Keys used: `origin="hub_call"`, `caller_agent_id`, `caller_session_id`.
- Spawn `query` argument to `dispatch_subagent` is the caller's `message` (this becomes session `query` / directory `task`). The first user line in context is still `format_incoming_call(...)`.
- `is_wait=False`. Inherit `working_directory` and `orchestration_mode` from `self.subagent`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_call_to_agent_id_spawns_new_session_even_if_one_exists(
    agent, mock_session, monkeypatch
):
    from cloudra.tools.Managetool import _hub_call as hub_call

    db = ConversationDB(agent.conversation_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'running')"
        )
        con.commit()
    captured = {}

    async def fake_dispatch(agent_cls, **kwargs):
        captured.update(kwargs)
        from cloudra.tools.Managetool._subagent_dispatch import SubagentDispatchResult
        return SubagentDispatchResult(
            task_id=9, session_id="a-4_task9", act_agent="small_mol", result="async"
        )

    monkeypatch.setattr(hub_call, "dispatch_subagent", fake_dispatch)
    monkeypatch.setattr(
        "cloudra.tools.Managetool.agent_hub.dispatch_subagent", fake_dispatch
    )
    agent.session_id = "a-0_run1"
    agent.id = "a-0"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(AgentHub_input_schema(
        action="call", to="a-4", message="帮我看虚频",
    ), mock_session)
    assert out.is_success
    assert out.session_id == "a-4_task9"
    assert captured["is_wait"] is False
    assert captured["query"] == "帮我看虚频"
    extra = captured.get("extra_payload") or {}
    assert extra.get("origin") == "hub_call"
    assert extra.get("caller_session_id") == "a-0_run1"


@pytest.mark.asyncio
async def test_call_to_a0_does_not_spawn(agent, mock_session, monkeypatch):
    spawned = []

    async def boom(*_a, **_k):
        spawned.append(1)
        raise AssertionError("must not spawn coordinator")

    monkeypatch.setattr(
        "cloudra.tools.Managetool._hub_call.dispatch_subagent", boom
    )
    db = ConversationDB(agent.conversation_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-0_run1', 'a-0', 'coordinator', '主任务', 'running')"
        )
        con.commit()
    agent.session_id = "a-4_task1"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(AgentHub_input_schema(
        action="call", to="a-0", message="虚频怎么处理",
    ), mock_session)
    assert out.is_success
    assert out.session_id == "a-0_run1"
    assert spawned == []
```

Patch the symbol actually used by `_call` (if spawn is in `_hub_call.spawn_from_call`, patch that).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_agent_hub.py::test_call_to_agent_id_spawns_new_session_even_if_one_exists tests/test_agent_hub.py::test_call_to_a0_does_not_spawn`

Expected: FAIL (spawn error or Coordinator cloned).

- [ ] **Step 3: Implement spawn**

`dispatch_subagent` signature add `extra_payload: Optional[dict] = None`. After `base_payload = { ... 'yolo': ... }`:

```python
    if extra_payload:
        base_payload.update(extra_payload)
```

In `_hub_call.py`:

```python
async def spawn_from_call(
    *,
    agent_id: str,
    message: str,
    incoming_text: str,
    conversation_id: str,
    working_directory,
    parent_session_id,
    parent_orchestration_mode,
    caller_agent_id: str,
    caller_session_id: str,
) -> str:
    from cloudra.subagents import Subagent_hash
    from cloudra.tools.Managetool._subagent_dispatch import dispatch_subagent

    agent_cls = Subagent_hash().get(agent_id)
    if agent_cls is None:
        raise ValueError(f"未知 agent_id: {agent_id}")
    result = await dispatch_subagent(
        agent_cls,
        agent_id=agent_id,
        query=message,
        context=[{"role": "user", "content": incoming_text}],
        is_wait=False,
        conversation_id=conversation_id,
        working_directory=working_directory,
        parent_session_id=parent_session_id,
        parent_orchestration_mode=parent_orchestration_mode,
        extra_payload={
            "origin": "hub_call",
            "caller_agent_id": caller_agent_id,
            "caller_session_id": caller_session_id,
        },
    )
    return result.session_id
```

Passing `incoming_text` as `context` makes the first extra user line the 【来电】 template; `query=message` fills directory `task`. `dispatch_subagent` already appends `context` blocks onto the new agent.

Wire `kind == "spawn"` in `_call` to `spawn_from_call` and return `session_id`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/test_agent_hub.py tests/test_subagent_execution_mode.py tests/test_subagent_swarm.py`

Expected: PASS (`extra_payload` default None must not break launcher/swarm).

- [ ] **Step 5: Commit** — skip unless the user asked.

---

### Task 4: Hang-up vs delivery + follower resume

**Files:**
- Modify: `cloudra/runtime/executor.py`
- Modify: `cloudra/tools/Managetool/_hub_call.py`
- Test: `tests/test_executor_finalize.py`
- Test: `tests/test_agent_hub.py` (resume path can be a unit test on a helper)

**Interfaces:**
- Produces: `async def _wake_parent(database_path, input_data, content)` — if `input_data.get("origin") == "hub_call"`, inject `role=user` hang-up to `caller_agent_id` / `caller_session_id`; else existing `_wake_coordinator`.
- Hang-up text: `【来电结束】{agent_name} (session={session_id}) 已挂断。`
- Visit resume: if follower target has no `subagent_requests` row in `ready`/`running` for that `session_id`, `acreate_subagent_request` with `session_id_fn=lambda _tid: session_id` and `create_task(run_subagent_in_process(...))` (copy `_resume_follower_session` without TUI `user_message` session_event). Coordinator visit: inject only; if you can see no live wait loop, do not invent a second Coordinator. Sleeping Coordinator wakeup via `submit_async` is **out of this task** unless a one-line hook is already easy; spec requires it — implement a helper `async def resume_visit_if_needed(...)` that for `agent_id=="a-0"` only injects (wait loop already listens to `external_event`), and for followers resumes when no running request.

- [ ] **Step 1: Write failing tests**

In `tests/test_executor_finalize.py`, add a helper path that puts `origin` in `input_data`:

```python
@pytest.mark.asyncio
class TestHubCallHangup:
    async def test_hub_call_origin_does_not_wake_coordinator_as_delivery(
        self, tmp_path, monkeypatch
    ):
        from cloudra.runtime.executor import run_executor

        db_path = _setup_executor_env(tmp_path, monkeypatch, run_result="闲聊结论")
        db = ConversationDB.from_path(db_path)
        with db.connect() as con:
            row = con.execute("SELECT input_data FROM subagent_requests WHERE id=1").fetchone()
            payload = json.loads(row[0])
            payload["origin"] = "hub_call"
            payload["caller_agent_id"] = "a-0"
            payload["caller_session_id"] = "a-0_run1"
            con.execute(
                "UPDATE subagent_requests SET input_data=? WHERE id=1",
                (json.dumps(payload),),
            )
            con.commit()
        await run_executor(1, db_path, "s-1")
        _, _, events = _read_states(db_path)
        contents = [e[3] for e in events]
        assert not any("已完成。结论" in (c or "") for c in contents)
```

Also assert a user-line hang-up was appended for the caller if easy (caller CM under conv-1 / a-0). `_wake_coordinator` today inserts `context_events` for a-0. New path should `deliver_incoming_call` or append+inject user_message to caller, **not** `event_type=subagent`.

Extend `_read_states` or query `context_events.event_type` is `user_message` and content contains `【来电结束】`.

Keep existing `TestMarkDone.test_db_state_and_wakeup_event` unchanged (launcher origin still `subagent` + 已完成).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_executor_finalize.py::TestHubCallHangup`

Expected: FAIL (`已完成。结论` still present).

- [ ] **Step 3: Implement hang-up branch**

Replace the three `_wake_coordinator(...)` calls with `_wake_after_executor(...)`:

```python
async def _wake_after_executor(database_path: str, input_data: dict, content: str) -> None:
    if input_data.get("origin") == "hub_call":
        caller_id = input_data.get("caller_agent_id") or "a-0"
        caller_session = input_data.get("caller_session_id") or None
        hangup = (
            f"【来电结束】{input_data.get('agent_id', 'subagent')} "
            f"(session={input_data.get('session_id')}) 已挂断。"
        )
        from cloudra.tools.Managetool._hub_call import deliver_incoming_call
        await deliver_incoming_call(
            conversation_id=input_data.get("conversation_id", "default"),
            callee_agent_id=caller_id,
            callee_session_id=caller_session or "",
            text=hangup,
            db_path=database_path,
        )
        return
    await _wake_coordinator(database_path, input_data, content)
```

Use `sub_agent.name` / `session_id` / `task_id` already in the existing f-strings for hang-up; pass them in `content` or format inside `_wake_after_executor` from `input_data` + the current `session_id` argument. Keep launcher strings identical.

Visit resume helper (followers only):

```python
async def resume_follower_if_idle(*, db, conversation_id, session_id, agent_id, working_directory, orchestration_mode, parent_session_id) -> None:
    async def count_live():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM subagent_requests "
                "WHERE session_id=? AND state IN ('ready', 'running')",
                (session_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0
    if await aretry_on_locked(count_live) > 0:
        return
    # same acreate_subagent_request + create_task(run_subagent_in_process) as service._resume_follower_session
```

Call this at the end of visit `call` after `deliver_incoming_call`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/test_executor_finalize.py tests/test_agent_hub.py`

Expected: PASS. Launcher done test still has `event_type == "subagent"` and 已完成.

- [ ] **Step 5: Commit** — skip unless the user asked.

---

### Task 5: Prompts

**Files:**
- Modify: `cloudra/runtime/prompt_assembler.py` (`_AGENT_HUB_GUIDANCE`)
- Modify: `cloudra/core/agent.py` (`_REVIVED_AFTER_STOP_NOTICE`)
- Modify: `cloudra/prompts/coordinator.md`
- Test: `tests/test_prompt_assembler.py`
- Test: `tests/test_plan_tools.py`

**Interfaces:**
- Consumes: none from previous tasks besides the 【来电】 user-line convention.
- Produces: updated guidance strings only.

- [ ] **Step 1: Write failing tests**

In `test_prompt_assembler.py::test_agent_hub_guidance_injected_when_tool_present` add:

```python
    assert "directory" in with_hub.identity_messages[0]["content"]
    assert "call" in with_hub.identity_messages[0]["content"]
    assert "【来电】" in with_hub.identity_messages[0]["content"]
```

In `test_plan_tools.py::test_revived_after_stop_notice_injected` add:

```python
        assert "来电" in text
```

Add a small test that coordinator prompt no longer forbids peer talk:

```python
def test_coordinator_prompt_allows_peer_call():
    from pathlib import Path
    text = Path("cloudra/prompts/coordinator.md").read_text(encoding="utf-8")
    assert "不允许直接通信" not in text
    assert "agent_hub" in text
```

Put that in `tests/test_agent_hub.py` or `tests/test_prompt_assembler.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_prompt_assembler.py::test_agent_hub_guidance_injected_when_tool_present tests/test_plan_tools.py::TestGoalConfirm::test_revived_after_stop_notice_injected`

Expected: FAIL on missing `directory` / `来电`.

- [ ] **Step 3: Edit the three prompt sources**

`_AGENT_HUB_GUIDANCE` — add bullets: `directory` lists `task` (what they are doing); `call` uses `to` + `message` (optional `post_id`); a `【来电】` line is a user message and must be answered first; `call` is not a delivery.

`_REVIVED_AFTER_STOP_NOTICE` — add that a `【来电】` user line counts as a user ask (answer before silent `stop`).

`coordinator.md` — delete “子 Agent 之间不允许直接通信，信息同步由你负责.” Replace with: 派工仍用 `SubAgentLauncher`；平行说话用 `agent_hub` 的 `call`/`post`，那不是一次交付。

Do not edit `small_mol.md` / `dft.md`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/test_prompt_assembler.py tests/test_plan_tools.py tests/test_agent_hub.py tests/test_executor_finalize.py`

Expected: PASS.

- [ ] **Step 5: Commit** — skip unless the user asked.

---

## Spec coverage

| Spec item | Task |
| :--- | :--- |
| `directory` + `task` naming | 1 |
| `call` `to`/`message`/`post_id`, no `query` | 1–3 |
| `to` resolution visit vs spawn vs a-0 | 1, 3 |
| Incoming `role=user` 【来电】 template | 2 |
| Missing `post_id` still calls | 2 |
| Spawn `origin=hub_call`, `is_wait=False`, directory task = message | 3 |
| Hang-up not Coordinator delivery | 4 |
| Follower resume when idle | 4 |
| Prompts / coordinator line | 5 |
| No pin / no stop reject / no role-file rewrite | Global + 5 |

## Placeholder scan

None. Spawn is Task 3, not a “later” comment in the shipped dispatcher after Task 3 completes.
