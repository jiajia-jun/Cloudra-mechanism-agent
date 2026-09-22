from cloudra.core.agent import Coordinator
from cloudra.tools.core.permission_model import Permission


def test_agent_working_directory_defaults_to_cwd(tmp_path, monkeypatch):
    """未显式传入时，Agent 工作目录必须收成当前进程的绝对路径，不能保持 None。"""
    monkeypatch.chdir(tmp_path)
    agent = Coordinator(query="test", conversation_id="test")
    assert agent.working_directory == str(tmp_path.resolve())


def test_coordinator_permissions():
    """测试 Coordinator 的默认权限。"""
    agent = Coordinator(query="test", conversation_id="test")
    perms = agent.permission_all()
    assert bool(perms & Permission.READ) is True
    assert bool(perms & Permission.MANAGE) is True
    assert bool(perms & Permission.WRITE) is True  # Coordinator 拥有 write 权限，但实际受白名单约束
    assert agent.has_manage_permission() is True

def test_builtin_roles_own_their_prompt_files():
    """每个内置角色都要有对应的角色 prompt（身份只此一处声明）。"""
    from pathlib import Path

    from cloudra.runtime_v2.roles import BUILTIN_ROLES

    prompts = Path("cloudra/prompts")
    for role in BUILTIN_ROLES:
        assert (prompts / f"{role.role_id}.md").exists(), f"missing prompt: {role.role_id}"


def test_legacy_subagent_class_stack_is_gone():
    """legacy 子 Agent 类栈（a-N 类 + 注册表加载器）已删除，不得复活。

    身份/权限的唯一事实源是 ``RoleProfile``（runtime_v2/roles.py）；
    历史 a-N 词表只经 ``cloudra.base.role_identity`` 映射。
    """
    from pathlib import Path

    pkg = Path(__file__).resolve().parents[1] / "cloudra" / "subagents"
    leftovers = sorted(p.name for p in pkg.glob("*.py")) if pkg.exists() else []
    assert leftovers == [], f"legacy subagent modules still present: {leftovers}"
