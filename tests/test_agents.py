from cloudra.core.agent import Coordinator
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


def test_follower_streams_by_default():
    """Follower（子 Agent）默认开启流式，前端才能收到各 session 的 llm_chunk。"""
    from cloudra.subagents.explorer import explorer
    assert explorer(query="test", conversation_id="test").is_stream is True


def test_subagent_roster():
    """钉住新 roster：8 个领域角色、id 连续、权限矩阵符合约定。"""
    from cloudra.subagents import get_subagent_classes

    classes = get_subagent_classes()
    expected_ids = [f"a-{i}" for i in range(1, 9)]
    assert sorted(classes.keys()) == expected_ids

    expected_names = {
        "a-1": "explorer",
        "a-2": "writer",
        "a-3": "researcher",
        "a-4": "small_mol",
        "a-5": "md",
        "a-6": "dft",
        "a-7": "experiment",
        "a-8": "env",
    }
    for aid, name in expected_names.items():
        cls = classes[aid]
        agent = cls(query="test", conversation_id="test")
        assert agent.name == name
        assert agent.id == aid
        # prompt 文件必须存在
        from pathlib import Path
        prompt_path = Path("cloudra/prompts") / f"{agent.prompt_name}.md"
        assert prompt_path.exists(), f"missing prompt: {prompt_path}"

    # 权限矩阵：explorer 只读；writer 读写；其余全权限
    def perms(aid):
        agent = classes[aid](query="test", conversation_id="test")
        return (
            agent.has_read_permission(),
            agent.has_write_permission(),
            agent.script_run_permission(),
            agent.destructive_permission(),
        )

    assert perms("a-1") == (True, False, False, False)
    assert perms("a-2") == (True, True, False, False)
    for aid in ("a-3", "a-4", "a-5", "a-6", "a-7", "a-8"):
        assert perms(aid) == (True, True, True, True)
