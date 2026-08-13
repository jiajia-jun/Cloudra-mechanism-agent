"""AgentHub（agent 论坛）钉板测试：

- 注册与可见性：只读的 explorer 也能看到 agent_hub（论坛是通信渠道，不占写权限）
- post/read/browse/search 回环；parent_id 问答串；参数校验
"""

import asyncio
import json

import pytest

from cloudra.core.agent import Follower
from cloudra.persistence.database import ConversationDB
from cloudra.subagents.explorer import explorer
from cloudra.tools.Managetool._hub_call import (
    format_incoming_call,
    list_directory,
    resolve_call_target,
)
from cloudra.tools.Managetool.agent_hub import (
    AgentHub,
    AgentHub_input_schema,
)


@pytest.fixture
def agent():
    return Follower(
        id="a-hub",
        name="hubber",
        prompt="测试",
        query="测试问题",
        conversation_id="test-hub",
    )


class TestRegistry:
    def test_hub_visible_to_readonly_explorer(self):
        agent = explorer(query="test", conversation_id="test-hub")
        names = {t.tool_name for t in agent.get_available_tools()}
        assert "agent_hub" in names


@pytest.mark.asyncio
class TestAgentHub:
    async def test_post_and_read_roundtrip(self, agent, mock_session):
        tool = AgentHub(subagent=agent)
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="CO2加氢-文献", kind="finding",
            content="发现：Cu/ZnO 界面是关键活性位，DOI:10.xxxx",
        ), mock_session)
        assert out.is_success and out.post_id > 0

        read = await tool.tool_call(AgentHub_input_schema(
            action="read", topic="CO2加氢-文献",
        ), mock_session)
        assert read.is_success and len(read.posts) == 1
        post = read.posts[0]
        assert post["content"].startswith("发现：Cu/ZnO")
        assert post["author_agent"] == "hubber"
        assert post["kind"] == "finding"
        assert post["parent_id"] is None

    async def test_thread_with_parent_id(self, agent, mock_session):
        tool = AgentHub(subagent=agent)
        q = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="MD-力场", kind="question", content="有人问：OPLS 还是 AMBER？",
        ), mock_session)
        a = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="MD-力场", kind="answer", content="回答：看体系，蛋白质用 AMBER。",
            parent_id=q.post_id,
        ), mock_session)
        assert a.is_success

        read = await tool.tool_call(AgentHub_input_schema(
            action="read", topic="MD-力场",
        ), mock_session)
        answers = [p for p in read.posts if p["kind"] == "answer"]
        assert answers and answers[0]["parent_id"] == q.post_id

    async def test_browse_and_search(self, agent, mock_session):
        tool = AgentHub(subagent=agent)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="CO2加氢-文献", content="Cu/ZnO 界面是活性位",
        ), mock_session)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="MD-力场", kind="answer", content="蛋白质用 AMBER 力场",
        ), mock_session)

        browse = await tool.tool_call(AgentHub_input_schema(action="browse"), mock_session)
        assert browse.is_success
        topics = {t["topic"] for t in browse.posts}
        assert {"CO2加氢-文献", "MD-力场"} <= topics

        hit = await tool.tool_call(AgentHub_input_schema(
            action="search", keyword="AMBER",
        ), mock_session)
        assert hit.is_success and len(hit.posts) == 1
        assert "AMBER" in hit.posts[0]["content"]

        miss = await tool.tool_call(AgentHub_input_schema(
            action="search", keyword="不存在的关键词xyz",
        ), mock_session)
        assert miss.is_success and miss.posts == []

    async def test_validation(self, agent, mock_session):
        tool = AgentHub(subagent=agent)
        out = await tool.tool_call(AgentHub_input_schema(action="post", topic="", content="x"), mock_session)
        assert not out.is_success
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="t", content="x", kind="rant",
        ), mock_session)
        assert not out.is_success
        out = await tool.tool_call(AgentHub_input_schema(action="teleport"), mock_session)
        assert not out.is_success
        out = await tool.tool_call(AgentHub_input_schema(action="read"), mock_session)
        assert not out.is_success

    async def test_directory_action_lists_sessions(self, agent, mock_session, tmp_path):
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

    async def test_cross_agent_visibility(self, agent, mock_session):
        """另一个 Agent（不同 session）也能读到帖子——论坛是跨进程的共享媒介。"""
        await AgentHub(subagent=agent).tool_call(AgentHub_input_schema(
            action="post", topic="CO2加氢-文献", content="共享的发现",
        ), mock_session)
        other = Follower(
            id="a-hub2", name="reader", prompt="测试", query="q",
            conversation_id="test-hub",
        )
        read = await AgentHub(subagent=other).tool_call(AgentHub_input_schema(
            action="read", topic="CO2加氢-文献",
        ), mock_session)
        assert read.is_success and len(read.posts) == 1
        assert read.posts[0]["author_agent"] == "hubber"


@pytest.fixture
def captured_events(monkeypatch):
    """拦截 ContextManager.inject_event，捕获论坛发出的事件通知。"""
    from cloudra.persistence.context_manager import ContextManager

    calls = []

    async def fake_inject_event(*, conversation_id, agent_id, event_type, content, db_path=None, **_kwargs):
        calls.append({
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "content": content,
        })

    monkeypatch.setattr(ContextManager, "inject_event", fake_inject_event)
    return calls


@pytest.mark.asyncio
class TestHubNotify:
    async def test_to_agent_triggers_hub_message_event(self, agent, mock_session, captured_events):
        """to_agent 点名（角色名解析为 agent_id）→ 被点名者收到 hub_message 事件。"""
        tool = AgentHub(subagent=agent)
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="乙烯臭氧化-TS1", kind="message", to_agent="small_mol",
            content="TS1 虚频 -275 cm-1，请复核 IRC 端点匹配。",
        ), mock_session)
        assert out.is_success and "Notified" in out.message

        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt["conversation_id"] == "test-hub"
        assert evt["agent_id"] == "a-4"  # small_mol 解析为注册表里的 a-4
        assert evt["event_type"] == "hub_message"
        assert "mentioned you" in evt["content"] and "TS1 虚频" in evt["content"]

        read = await tool.tool_call(AgentHub_input_schema(
            action="read", topic="乙烯臭氧化-TS1",
        ), mock_session)
        assert read.posts[0]["to_agent"] == "small_mol"

    async def test_hub_message_truncates_notification_body(self, agent, mock_session, captured_events):
        """点名通知正文截断至 500 字符。"""
        body = "发现：" + ("关键活性位细节。" * 80)
        tool = AgentHub(subagent=agent)
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="长帖", kind="message", to_agent="small_mol",
            content=body,
        ), mock_session)
        assert out.is_success
        assert captured_events[0]["content"].endswith(body[:500])
        assert len(captured_events[0]["content"]) < len(body) + 80

    async def test_reply_notifies_original_author(self, mock_session, captured_events):
        """回复别人的帖子 → 原作者收到 hub_reply 事件；自己回复自己不通知。"""
        small_mol = Follower(
            id="a-4", name="small_mol", prompt="测试", query="q",
            conversation_id="test-hub",
        )
        q = await AgentHub(subagent=small_mol).tool_call(AgentHub_input_schema(
            action="post", topic="乙烯臭氧化-TS1", kind="question",
            content="TS1 虚频只有一个，但幅值偏小，算数吗？",
        ), mock_session)
        assert q.is_success and captured_events == []

        replier = Follower(
            id="a-6", name="dft", prompt="测试", query="q",
            conversation_id="test-hub",
        )
        a = await AgentHub(subagent=replier).tool_call(AgentHub_input_schema(
            action="post", topic="乙烯臭氧化-TS1", kind="answer",
            content="算数，虚频幅值看反应坐标，不看过渡态紧不紧。",
            parent_id=q.post_id,
        ), mock_session)
        assert a.is_success
        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt["agent_id"] == "a-4"
        assert evt["event_type"] == "hub_reply"
        assert "replied to your" in evt["content"]

        # 自己回复自己的帖子：不再产生任何通知
        captured_events.clear()
        self_reply = await AgentHub(subagent=small_mol).tool_call(AgentHub_input_schema(
            action="post", topic="乙烯臭氧化-TS1", kind="answer",
            content="补充：已用 IRC 确认端点。",
            parent_id=q.post_id,
        ), mock_session)
        assert self_reply.is_success and captured_events == []

    async def test_to_agent_validation(self, agent, mock_session, captured_events):
        tool = AgentHub(subagent=agent)
        # 未知角色名拒绝
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="t", content="x", to_agent="nobody",
        ), mock_session)
        assert not out.is_success and captured_events == []
        # message 类必须配 to_agent
        out = await tool.tool_call(AgentHub_input_schema(
            action="post", topic="t", content="x", kind="message",
        ), mock_session)
        assert not out.is_success and captured_events == []


@pytest.mark.asyncio
class TestHubFuzzySearch:
    async def test_synonym_keyword_hits(self, agent, mock_session):
        """近义/不精确措辞也能命中（中文 bigram 覆盖率），结果带 score。"""
        tool = AgentHub(subagent=agent)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="SCF-疑难",
            content="SCF 不收敛时用 stable=opt 重算并检查波函数，确认波函数稳定性。",
        ), mock_session)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="MD-力场", content="蛋白质用 AMBER 力场",
        ), mock_session)

        hit = await tool.tool_call(AgentHub_input_schema(
            action="search", keyword="检查波函数是否稳定",
        ), mock_session)
        assert hit.is_success and len(hit.posts) == 1
        assert hit.posts[0]["topic"] == "SCF-疑难"
        assert 0.34 <= hit.posts[0]["score"] < 1.0

    async def test_exact_substring_ranks_first(self, agent, mock_session):
        """子串精确命中得分高于模糊命中，排在最前。"""
        tool = AgentHub(subagent=agent)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="几何优化",
            content="几何优化收敛判据：力的均方根与最大位移同时达标。",
        ), mock_session)
        await tool.tool_call(AgentHub_input_schema(
            action="post", topic="SCF-疑难",
            content="SCF 不收敛时用 stable=opt 检查几何结构是否合理。",
        ), mock_session)

        hit = await tool.tool_call(AgentHub_input_schema(
            action="search", keyword="几何优化收敛",
        ), mock_session)
        assert hit.is_success and len(hit.posts) == 2
        # 第一帖正文精确包含关键词，应排在只有部分 bigram 重合的第二帖之前
        assert hit.posts[0]["topic"] == "几何优化"
        assert hit.posts[0]["score"] > hit.posts[1]["score"]


def test_format_incoming_call_is_user_speech_not_a_prompt():
    text = format_incoming_call(
        caller_agent_id="a-0",
        caller_session_id="a-0_run1",
        message="POZ 有虚频，怎么位移？",
    )
    assert text.startswith("[Incoming call]")
    assert "a-0" in text and "a-0_run1" in text
    assert "Answer this call first" in text
    assert "POZ 有虚频，怎么位移？" in text
    assert "[Incoming call]" in text.split("POZ", 1)[0]


def test_format_incoming_call_optional_post_line():
    text = format_incoming_call(
        caller_agent_id="a-4",
        caller_session_id="a-4_task1",
        message="看这个",
        post_line="Related post #3 (topic 虚频).",
    )
    assert "Related post #3" in text


def test_format_incoming_call_preserves_braces_in_message():
    spoken = '{"freq": -1}'
    text = format_incoming_call(
        caller_agent_id="a-0",
        caller_session_id="a-0_run1",
        message=spoken,
    )
    assert spoken in text
    assert text.endswith(spoken)


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
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-4', 'a-4', 'follower', 'legacy id', 'finished')"
        )
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('small_mol', 'a-4', 'follower', 'class name id', 'finished')"
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

    monkeypatch.setattr(hub_call, "dispatch_subagent", fake_dispatch, raising=False)
    agent.session_id = "a-0_run1"
    agent.id = "a-0"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(action="call", to="a-4", message="帮我看虚频"),
        mock_session,
    )
    assert out.is_success
    assert out.session_id == "a-4_task9"
    assert captured["is_wait"] is False
    assert captured["query"] == "帮我看虚频"
    expected_call = format_incoming_call(
        caller_agent_id="a-0",
        caller_session_id="a-0_run1",
        message="帮我看虚频",
    )
    assert captured["context"] == [{"role": "user", "content": expected_call}]
    extra = captured.get("extra_payload") or {}
    assert extra.get("origin") == "hub_call"
    assert extra.get("caller_session_id") == "a-0_run1"
    assert extra.get("caller_agent_id") == "a-0"


@pytest.mark.asyncio
async def test_call_to_a0_does_not_spawn(agent, mock_session, monkeypatch, tmp_path):
    spawned = []

    async def boom(*_a, **_k):
        spawned.append(1)
        raise AssertionError("must not spawn coordinator")

    monkeypatch.setattr(
        "cloudra.tools.Managetool._hub_call.dispatch_subagent",
        boom,
        raising=False,
    )
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    db = ConversationDB(agent.conversation_id).init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
            "VALUES ('a-0_run1', 'a-0', 'coordinator', '主任务', 'running')"
        )
        con.commit()
    agent.session_id = "a-4_task1"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(action="call", to="a-0", message="虚频怎么处理"),
        mock_session,
    )
    assert out.is_success
    assert out.session_id == "a-0_run1"
    assert spawned == []


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
        con.execute(
            "INSERT INTO subagent_requests (state, input_data, conversation_id, session_id) "
            "VALUES ('running', '{}', ?, 'a-4_task1')",
            (agent.conversation_id,),
        )
        con.commit()
    agent.session_id = "a-hub_s"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(
            action="call",
            to="a-4_task1",
            message="POZ 有虚频，怎么位移？",
        ),
        mock_session,
    )
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
        m
        for m in stored
        if m.get("role") == "user" and "[Incoming call]" in str(m.get("content", ""))
    ]
    system_hits = [
        m
        for m in stored
        if m.get("role") == "system"
        and (
            "[Incoming call]" in str(m.get("content", ""))
            or "【hub_message】" in str(m.get("content", ""))
            or "【user_message】" in str(m.get("content", ""))
        )
    ]
    assert len(user_hits) == 1
    assert "POZ 有虚频" in user_hits[0]["content"]
    assert system_hits == []


@pytest.mark.asyncio
async def test_call_unknown_agent_id_fails_closed(agent, mock_session):
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(action="call", to="a-99", message="hello"),
        mock_session,
    )
    assert not out.is_success
    assert "a-99" in out.message or "Unknown" in out.message


@pytest.mark.asyncio
async def test_call_empty_message_fails(agent, mock_session):
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(action="call", to="a-4", message=""),
        mock_session,
    )
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
        con.execute(
            "INSERT INTO subagent_requests (state, input_data, conversation_id, session_id) "
            "VALUES ('running', '{}', ?, 'a-4_task1')",
            (agent.conversation_id,),
        )
        con.commit()
    agent.session_id = "a-hub_s"
    tool = AgentHub(subagent=agent)
    out = await tool.tool_call(
        AgentHub_input_schema(
            action="call",
            to="a-4_task1",
            message="看一下",
            post_id=999,
        ),
        mock_session,
    )
    assert out.is_success


@pytest.mark.asyncio
class TestResumeFollowerIfIdle:
    async def test_idle_follower_creates_hub_call_request(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        monkeypatch.setattr(
            "cloudra.infra.runtime_profile.subagent_execution_mode",
            lambda: "inprocess",
        )
        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state, "
                "orchestration_mode) "
                "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'completed', 'dag_record')"
            )
            con.commit()

        scheduled = []

        async def fake_run(task_id, db_path, sid):
            scheduled.append((task_id, sid, db_path))

        monkeypatch.setattr(
            "cloudra.tools.Managetool._subagent_dispatch.run_subagent_in_process",
            fake_run,
        )

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-4_task1",
            agent_id="a-4",
            working_directory="/work",
            orchestration_mode="dag_record",
            parent_session_id="a-0_run1",
            caller_agent_id="a-0",
            caller_session_id="a-0_run1",
        )
        await asyncio.sleep(0.05)

        with db.connect() as con:
            rows = con.execute(
                "SELECT input_data, state, session_id FROM subagent_requests WHERE session_id=?",
                ("a-4_task1",),
            ).fetchall()
        assert len(rows) == 1
        payload = json.loads(rows[0][0])
        assert rows[0][1] == "running"
        assert rows[0][2] == "a-4_task1"
        assert payload["origin"] == "hub_call"
        assert payload["caller_agent_id"] == "a-0"
        assert payload["caller_session_id"] == "a-0_run1"
        assert payload["agent_id"] == "a-4"
        assert payload["working_directory"] == "/work"
        assert payload["orchestration_mode"] == "dag_record"
        assert payload.get("context") in (None, [])
        assert scheduled and scheduled[0][1] == "a-4_task1"

    async def test_guided_parent_resume_stores_dag_record(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        monkeypatch.setattr(
            "cloudra.infra.runtime_profile.subagent_execution_mode",
            lambda: "inprocess",
        )
        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state, "
                "working_directory, orchestration_mode) "
                "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'completed', "
                "'/session-work', 'dag_guided')"
            )
            con.commit()

        scheduled = []

        def fake_create_mobile_task(coro):
            scheduled.append(coro)
            coro.close()
            return None

        monkeypatch.setattr(
            "cloudra.runtime.mobile_tasks.create_mobile_task",
            fake_create_mobile_task,
        )

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-4_task1",
            agent_id="a-4",
            working_directory="/caller-work",
            orchestration_mode="dag_guided",
            parent_session_id="a-0_run1",
            caller_agent_id="a-0",
            caller_session_id="a-0_run1",
        )

        with db.connect() as con:
            row = con.execute(
                "SELECT input_data, state FROM subagent_requests WHERE session_id=?",
                ("a-4_task1",),
            ).fetchone()
        payload = json.loads(row[0])
        assert row[1] == "running"
        assert payload["orchestration_mode"] == "dag_record"
        assert payload["working_directory"] == "/session-work"
        assert payload["origin"] == "hub_call"
        assert len(scheduled) == 1

    async def test_idle_resume_subprocess_marks_ready(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        monkeypatch.setattr(
            "cloudra.infra.runtime_profile.subagent_execution_mode",
            lambda: "subprocess",
        )
        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
                "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'completed')"
            )
            con.commit()

        scheduled = []
        emitted = []

        async def fake_run(*_a, **_k):
            scheduled.append(1)

        async def fake_aemit(conversation_id, kind, **kwargs):
            emitted.append((conversation_id, kind, kwargs))

        monkeypatch.setattr(
            "cloudra.tools.Managetool._subagent_dispatch.run_subagent_in_process",
            fake_run,
        )
        monkeypatch.setattr("cloudra.infra.events.aemit", fake_aemit)

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-4_task1",
            agent_id="a-4",
            working_directory="/work",
            orchestration_mode="standard",
            parent_session_id="a-0_run1",
            caller_agent_id="a-0",
            caller_session_id="a-0_run1",
        )

        with db.connect() as con:
            row = con.execute(
                "SELECT input_data, state FROM subagent_requests WHERE session_id=?",
                ("a-4_task1",),
            ).fetchone()
        payload = json.loads(row[0])
        assert row[1] == "ready"
        assert payload["orchestration_mode"] == "standard"
        assert scheduled == []
        assert any(kind == "subagent_request_ready" for _, kind, _ in emitted)
        assert emitted[0][2]["session_id"] == "a-4_task1"

    async def test_guided_caller_fallback_stores_dag_record(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        monkeypatch.setattr(
            "cloudra.infra.runtime_profile.subagent_execution_mode",
            lambda: "inprocess",
        )

        async def no_stored(_db, _session_id):
            return None, None

        monkeypatch.setattr(
            "cloudra.tools.Managetool._hub_call._session_resume_fields",
            no_stored,
        )
        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
                "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'completed')"
            )
            con.commit()

        scheduled = []

        def fake_create_mobile_task(coro):
            scheduled.append(coro)
            coro.close()
            return None

        monkeypatch.setattr(
            "cloudra.runtime.mobile_tasks.create_mobile_task",
            fake_create_mobile_task,
        )

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-4_task1",
            agent_id="a-4",
            working_directory="/caller-work",
            orchestration_mode="dag_guided",
            parent_session_id="a-0_run1",
            caller_agent_id="a-0",
            caller_session_id="a-0_run1",
        )

        with db.connect() as con:
            row = con.execute(
                "SELECT input_data FROM subagent_requests WHERE session_id=?",
                ("a-4_task1",),
            ).fetchone()
        payload = json.loads(row[0])
        assert payload["orchestration_mode"] == "dag_record"
        assert payload["working_directory"] == "/caller-work"
        assert payload["origin"] == "hub_call"
        assert len(scheduled) == 1

    async def test_live_ready_or_running_does_not_resume(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
                "VALUES ('a-4_task1', 'a-4', 'follower', 'opt', 'running')"
            )
            con.execute(
                "INSERT INTO subagent_requests (state, input_data, conversation_id, session_id) "
                "VALUES ('running', '{}', 'conv-1', 'a-4_task1')"
            )
            con.commit()

        scheduled = []

        async def fake_run(*_a, **_k):
            scheduled.append(1)

        monkeypatch.setattr(
            "cloudra.tools.Managetool._subagent_dispatch.run_subagent_in_process",
            fake_run,
        )

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-4_task1",
            agent_id="a-4",
            working_directory="/work",
            orchestration_mode="standard",
            parent_session_id="a-0_run1",
            caller_agent_id="a-0",
            caller_session_id="a-0_run1",
        )

        with db.connect() as con:
            n = con.execute(
                "SELECT COUNT(*) FROM subagent_requests WHERE session_id=?",
                ("a-4_task1",),
            ).fetchone()[0]
        assert n == 1
        assert scheduled == []

    async def test_a0_does_not_spawn(self, tmp_path, monkeypatch):
        from cloudra.tools.Managetool._hub_call import resume_follower_if_idle

        db = ConversationDB.from_path(str(tmp_path / "hub.db")).init()
        with db.connect() as con:
            con.execute(
                "INSERT INTO session (session_id, agent_id, agent_type, query, state) "
                "VALUES ('a-0_run1', 'a-0', 'coordinator', '主任务', 'sleeping')"
            )
            con.commit()

        scheduled = []

        async def fake_run(*_a, **_k):
            scheduled.append(1)

        monkeypatch.setattr(
            "cloudra.tools.Managetool._subagent_dispatch.run_subagent_in_process",
            fake_run,
        )

        await resume_follower_if_idle(
            db=db,
            conversation_id="conv-1",
            session_id="a-0_run1",
            agent_id="a-0",
            working_directory="/work",
            orchestration_mode="standard",
            parent_session_id=None,
            caller_agent_id="a-4",
            caller_session_id="a-4_task1",
        )

        with db.connect() as con:
            n = con.execute("SELECT COUNT(*) FROM subagent_requests").fetchone()[0]
        assert n == 0
        assert scheduled == []
