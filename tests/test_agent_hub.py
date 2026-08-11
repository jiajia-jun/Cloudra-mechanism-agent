"""AgentHub（agent 论坛）钉板测试：

- 注册与可见性：只读的 explorer 也能看到 agent_hub（论坛是通信渠道，不占写权限）
- post/read/browse/search 回环；parent_id 问答串；参数校验
"""

import pytest

from cloudra.core.agent import Follower
from cloudra.subagents.explorer import explorer
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
        assert out.is_success and "已通知" in out.message

        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt["conversation_id"] == "test-hub"
        assert evt["agent_id"] == "a-4"  # small_mol 解析为注册表里的 a-4
        assert evt["event_type"] == "hub_message"
        assert "点名你" in evt["content"] and "TS1 虚频" in evt["content"]

        read = await tool.tool_call(AgentHub_input_schema(
            action="read", topic="乙烯臭氧化-TS1",
        ), mock_session)
        assert read.posts[0]["to_agent"] == "small_mol"

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
        assert "回复了你" in evt["content"]

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
