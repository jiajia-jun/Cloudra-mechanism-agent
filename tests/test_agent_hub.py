"""AgentHub（agent 论坛）钉板测试：

- 注册与可见性：只读的 explorer 也能看到 agent_hub（论坛是通信渠道，不占写权限）
- post/read/browse/search 回环；parent_id 问答串；参数校验
"""

import pytest

from cloudra.agent import Follower
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
