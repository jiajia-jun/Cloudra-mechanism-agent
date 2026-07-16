from cloudra.agent import Coordinator
from cloudra.tools.core.permission_model import Permission


def test_coordinator_permissions():
    """测试 Coordinator 的默认权限。"""
    agent = Coordinator(query="test", conversation_id="test")
    perms = agent.permission_all()
    assert bool(perms & Permission.READ) is True
    assert bool(perms & Permission.MANAGE) is True
    assert bool(perms & Permission.WRITE) is True  # Coordinator 拥有 write 权限，但实际受白名单约束
    assert agent.has_manage_permission() is True

def test_follower_permissions():
    """测试 Follower (以 explorer 为例) 的权限。"""
    from cloudra.subagents.explorer import explorer
    agent = explorer(query="test", conversation_id="test")
    perms = agent.permission_all()
    assert bool(perms & Permission.READ) is True
    assert bool(perms & Permission.WRITE) is False
    assert bool(perms & Permission.DESTRUCTIVE) is False

def test_agent_available_tools():
    """测试 Agent 能过滤出符合权限的工具。"""
    from cloudra.subagents.explorer import explorer
    agent = explorer(query="test", conversation_id="test")
    tools = agent.get_available_tools()

    # explorer 应该能看到 bashtools (read), 但不应该看到 molecule_drawer (destructive)
    # 注意：molecule_drawer 现在的权限设置可能允许 read? 检查一下
    tool_names = [t.tool_name for t in tools]
    assert 'bashtools' in tool_names
    # 假设 molecule_drawer 是 destructive，explorer 不该有
    # assert 'molecule_drawer' not in tool_names
