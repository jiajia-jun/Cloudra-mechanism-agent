"""实例字段隔离回归：reAct / Session 的类级可变默认值会导致实例间共享状态。"""

from cloudra.persistence.database import ConversationDB


def _make_react(tmp_path, monkeypatch, agent_id, conv_id):
    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct

    db_path = str(tmp_path / f"{conv_id}.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _cid, _db=db_path: _db)

    agent = Follower(
        id=agent_id,
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    return reAct(agent)


def test_react_instances_do_not_share_state(tmp_path, monkeypatch):
    react_a = _make_react(tmp_path, monkeypatch, "a-1", "conv-a")
    react_b = _make_react(tmp_path, monkeypatch, "a-2", "conv-b")

    react_a.undos.append({"role": "assistant"})
    react_a._continue = False
    # 网络重试计数 _reset_count 已随重试层迁移到 LLMClient；
    # 这里改用截断重试计数固定实例隔离语义
    react_a._truncation_retries = 3

    assert react_a.undos is not react_b.undos
    assert react_b.undos == []
    assert react_b._continue is True
    assert react_b._truncation_retries == 0


def test_sessions_do_not_share_tool_calling(tmp_path):
    """terminal 追踪已从 Session 移到 Bash 工具实例：实例间不共享运行态。

    Session 现在是纯内存镜像（数据库是唯一事实来源），不再携带 tool_calling。
    """
    from cloudra.base.session_class import Session
    from cloudra.tools.Bashtool.bashtools import Bashtools

    session_a = Session(id="s-1", path=str(tmp_path / "s1.json"))
    assert not hasattr(session_a, "tool_calling")

    tool_a = Bashtools()
    tool_b = Bashtools()
    tool_a._terminal_commands["t-1"] = "ls"
    assert tool_a._terminal_commands is not tool_b._terminal_commands
    assert tool_b._terminal_commands == {}
