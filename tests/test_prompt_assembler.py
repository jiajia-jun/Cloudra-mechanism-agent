import json
from types import SimpleNamespace

import pytest

from cloudra.agent import Follower
from cloudra.context_manager import SUPERVISOR_ADVICE_MARKER, ContextManager


def _context_manager(tmp_path, *, agent_id="a-prompt", query="继续任务"):
    manager = ContextManager(
        agent_id=agent_id,
        conversation_id="prompt-conv",
        prompt=None,
        query=query,
        db_path=str(tmp_path / "conversation.db"),
    )
    manager.context_file = str(tmp_path / f"{agent_id}-context.json")
    return manager


def _agent(tmp_path, workspace, *, prompt_name=None, prompt=None):
    agent = Follower(
        id="a-prompt",
        name=prompt_name or "prompt-test",
        prompt_name=prompt_name,
        prompt=prompt,
        query="继续任务",
        conversation_id="prompt-conv",
        working_directory=str(workspace),
    )
    agent._tools_schema_cache = []
    agent.context_manager = _context_manager(tmp_path)
    return agent


@pytest.fixture
def isolated_prompt_sources(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = SimpleNamespace(config_file=config_dir / "config.toml")

    monkeypatch.setattr(
        "cloudra.runtime.prompt_assembler.PROMPTS_DIR",
        prompts_dir,
    )
    monkeypatch.setattr(
        "cloudra.runtime.prompt_assembler.get_config",
        lambda: config,
    )
    return prompts_dir, workspace


@pytest.mark.asyncio
async def test_role_prompt_change_applies_to_next_request(
    tmp_path,
    isolated_prompt_sources,
):
    prompts_dir, workspace = isolated_prompt_sources
    role_file = prompts_dir / "dynamic.md"
    role_file.write_text("第一版身份", encoding="utf-8")
    agent = _agent(tmp_path, workspace, prompt_name="dynamic")

    first = await agent._build_request_kwargs()
    first_diagnostics = agent.get_runtime_diagnostics()
    first_revision = first_diagnostics["prompt_revision"]
    assert "第一版身份" in first["messages"][0]["content"]

    role_file.write_text("第二版身份", encoding="utf-8")
    second = await agent._build_request_kwargs()
    second_diagnostics = agent.get_runtime_diagnostics()
    second_revision = second_diagnostics["prompt_revision"]

    assert second_revision != first_revision
    assert second_diagnostics["trace_id"] != first_diagnostics["trace_id"]
    assert "第二版身份" in second["messages"][0]["content"]
    assert "第一版身份" not in second["messages"][0]["content"]
    persisted = await agent.get_context()
    assert persisted == [{"role": "user", "content": "继续任务"}]


@pytest.mark.asyncio
async def test_dag_projection_provider_is_fresh_and_standard_has_no_marker(
    tmp_path,
    isolated_prompt_sources,
):
    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    standard = _agent(tmp_path, workspace, prompt_name="probe")

    ordinary = await standard._build_request_kwargs()
    assert not any(
        "DAG projection" in str(message.get("content", ""))
        for message in ordinary["messages"]
    )

    calls = 0

    async def projection():
        nonlocal calls
        calls += 1
        return f"DAG projection revision={calls}; no evidence bodies"

    guided = _agent(tmp_path, workspace, prompt_name="probe")
    guided.set_dag_projection_provider(projection)
    first = await guided._build_request_kwargs()
    second = await guided._build_request_kwargs()

    assert calls == 2
    assert first["messages"][-1]["content"].endswith("revision=1; no evidence bodies")
    assert second["messages"][-1]["content"].endswith("revision=2; no evidence bodies")


def test_web_search_guidance_gated_by_availability(isolated_prompt_sources):
    """联网搜索引导仅在声明有搜索能力时注入。"""
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )

    with_guidance = assembler.assemble(
        ["web_search"], web_search_available=True
    )
    assert "联网搜索" in with_guidance.identity_messages[0]["content"]

    without = assembler.assemble(
        ["web_search"], web_search_available=False
    )
    assert "联网搜索" not in without.identity_messages[0]["content"]


def test_agent_hub_guidance_injected_when_tool_present(isolated_prompt_sources):
    """有 agent_hub 工具时注入并行共享引导，否则不注入。"""
    from cloudra.runtime.prompt_assembler import PromptAssembler

    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    assembler = PromptAssembler(
        prompt_name="probe",
        custom_prompt=None,
        conversation_id="c",
        working_directory=str(workspace),
        include_memory=False,
    )

    with_hub = assembler.assemble(["bashtools", "agent_hub"])
    assert "AgentHub" in with_hub.identity_messages[0]["content"]
    assert "agent_hub" in with_hub.identity_messages[0]["content"]

    without_hub = assembler.assemble(["bashtools"])
    assert "AgentHub" not in without_hub.identity_messages[0]["content"]


@pytest.mark.asyncio
async def test_agent_injects_web_search_guidance_when_search_available(
    tmp_path, isolated_prompt_sources, monkeypatch
):
    """原生搜索启用（默认 deepseek+auto）时，请求的 system prompt 带联网搜索引导。"""
    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "probe.md").write_text("# 角色", encoding="utf-8")
    agent = _agent(tmp_path, workspace, prompt_name="probe")

    kwargs = await agent._build_request_kwargs()
    assert "联网搜索" in kwargs["messages"][0]["content"]

    # 关闭原生搜索且无 web_search 工具时，不注入引导
    from cloudra.config import get_config

    monkeypatch.setattr(get_config().follower, "native_search", "off")
    agent2 = _agent(tmp_path, workspace, prompt_name="probe")
    kwargs2 = await agent2._build_request_kwargs()
    assert "联网搜索" not in kwargs2["messages"][0]["content"]


@pytest.mark.asyncio
async def test_agents_md_change_applies_to_existing_conversation(
    tmp_path,
    isolated_prompt_sources,
):
    _, workspace = isolated_prompt_sources
    agents_file = workspace / "AGENTS.md"
    agents_file.write_text("策略第一版", encoding="utf-8")
    agent = _agent(tmp_path, workspace, prompt="固定角色")

    first = await agent._build_request_kwargs()
    first_revision = agent.get_runtime_diagnostics()["prompt_revision"]
    assert "策略第一版" in first["messages"][0]["content"]

    agents_file.write_text("策略第二版", encoding="utf-8")
    second = await agent._build_request_kwargs()
    second_revision = agent.get_runtime_diagnostics()["prompt_revision"]

    assert second_revision != first_revision
    assert "策略第二版" in second["messages"][0]["content"]
    assert "策略第一版" not in second["messages"][0]["content"]


@pytest.mark.asyncio
async def test_legacy_identity_is_removed_without_losing_history(tmp_path):
    manager = _context_manager(tmp_path)
    legacy = [
        {"role": "system", "content": "已经过期的身份"},
        {"role": "user", "content": "原始任务"},
        {"role": "assistant", "content": "已完成一部分"},
        {
            "role": "system",
            "content": f"{SUPERVISOR_ADVICE_MARKER} 保留这条建议",
        },
        {
            "role": "system",
            "content": "[上下文压缩提示] 保留这条梗概",
        },
    ]
    with open(manager.context_file, "w", encoding="utf-8") as stream:
        json.dump(legacy, stream, ensure_ascii=False)

    migrated = await manager.load()
    assert migrated == legacy[1:]
    # 磁盘已迁移为 JSONL；用双格式读取器验证内容完整
    from cloudra.context_manager import read_context_file
    assert read_context_file(manager.context_file) == legacy[1:]

    messages = await manager.build_messages(
        identity_messages=[{"role": "system", "content": "当前身份"}]
    )
    assert messages[0] == {"role": "system", "content": "当前身份"}
    assert not any("已经过期的身份" in str(msg.get("content")) for msg in messages)
    assert any("已完成一部分" in str(msg.get("content")) for msg in messages)
    assert any(SUPERVISOR_ADVICE_MARKER in str(msg.get("content")) for msg in messages)
    assert any("[上下文压缩提示]" in str(msg.get("content")) for msg in messages)


@pytest.mark.asyncio
async def test_agent_replays_legacy_history_with_current_identity(
    tmp_path,
    isolated_prompt_sources,
):
    _, workspace = isolated_prompt_sources
    agent = _agent(tmp_path, workspace, prompt="当前策略")
    legacy_history = [
        {"role": "system", "content": "旧版本身份与策略"},
        {"role": "user", "content": "分析旧样品"},
        {"role": "assistant", "content": "旧会话已经完成第一步"},
        {"role": "user", "content": "继续第二步"},
    ]
    with open(agent.context_manager.context_file, "w", encoding="utf-8") as stream:
        json.dump(legacy_history, stream, ensure_ascii=False)

    request = await agent._build_request_kwargs()
    contents = [str(message.get("content", "")) for message in request["messages"]]

    assert "当前策略" in contents[0]
    assert not any("旧版本身份与策略" in content for content in contents)
    assert any("分析旧样品" in content for content in contents)
    assert any("旧会话已经完成第一步" in content for content in contents)
    assert any("继续第二步" in content for content in contents)
    from cloudra.context_manager import read_context_file
    assert read_context_file(agent.context_manager.context_file) == legacy_history[1:]


@pytest.mark.asyncio
async def test_ordinary_workspace_change_is_observation_only(
    tmp_path,
    isolated_prompt_sources,
):
    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "dynamic.md").write_text("稳定身份", encoding="utf-8")
    agent = _agent(tmp_path, workspace, prompt_name="dynamic")

    first = await agent._build_request_kwargs()
    first_diagnostics = agent.get_runtime_diagnostics()
    first_observation = first["messages"][-1]["content"]

    (workspace / "new-result.txt").write_text("结果", encoding="utf-8")
    second = await agent._build_request_kwargs()
    second_diagnostics = agent.get_runtime_diagnostics()
    second_observation = second["messages"][-1]["content"]

    assert second_diagnostics["prompt_revision"] == first_diagnostics["prompt_revision"]
    assert second_observation != first_observation
    assert "new-result.txt" in second_observation


@pytest.mark.asyncio
async def test_capability_change_updates_prompt_and_diagnostics(
    tmp_path,
    isolated_prompt_sources,
):
    _, workspace = isolated_prompt_sources
    agent = _agent(tmp_path, workspace, prompt="固定角色")

    without_tools = await agent._build_request_kwargs()
    first_diagnostics = agent.get_runtime_diagnostics()
    assert "tools" not in without_tools

    agent._tools_schema_cache = [
        {
            "type": "function",
            "function": {
                "name": "device.fs.read",
                "description": "读取设备文件",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    with_tools = await agent._build_request_kwargs()
    second_diagnostics = agent.get_runtime_diagnostics()

    assert second_diagnostics["tool_names"] == ["device.fs.read"]
    assert second_diagnostics["capability_revision"] != first_diagnostics[
        "capability_revision"
    ]
    assert second_diagnostics["prompt_revision"] != first_diagnostics[
        "prompt_revision"
    ]
    assert with_tools["tools"] == agent._tools_schema_cache
    assert "- device.fs.read" in with_tools["messages"][0]["content"]


@pytest.mark.asyncio
async def test_existing_workspace_file_modification_is_observation_only(
    tmp_path,
    isolated_prompt_sources,
):
    prompts_dir, workspace = isolated_prompt_sources
    (prompts_dir / "dynamic.md").write_text("稳定身份", encoding="utf-8")
    source = workspace / "same-name.txt"
    source.write_text("first", encoding="utf-8")
    agent = _agent(tmp_path, workspace, prompt_name="dynamic")

    await agent._build_request_kwargs()
    first = agent.get_runtime_diagnostics()
    source.write_text("second-and-longer", encoding="utf-8")
    request = await agent._build_request_kwargs()
    second = agent.get_runtime_diagnostics()

    assert second["prompt_revision"] == first["prompt_revision"]
    assert second["environment_revisions"]["workspace"] != (
        first["environment_revisions"]["workspace"]
    )
    assert "modified: same-name.txt" in request["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_tool_schema_change_updates_capability_revision(
    tmp_path,
    isolated_prompt_sources,
):
    _, workspace = isolated_prompt_sources
    agent = _agent(tmp_path, workspace, prompt="固定角色")
    agent._tools_schema_cache = [
        {
            "type": "function",
            "function": {
                "name": "stable_name",
                "description": "schema v1",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    await agent._build_request_kwargs()
    first = agent.get_runtime_diagnostics()
    agent._tools_schema_cache[0]["function"]["description"] = "schema v2"
    await agent._build_request_kwargs()
    second = agent.get_runtime_diagnostics()

    assert second["tool_names"] == ["stable_name"]
    assert second["capability_revision"] != first["capability_revision"]
    assert second["prompt_revision"] != first["prompt_revision"]


@pytest.mark.asyncio
async def test_skill_manifest_and_supervisor_advice_have_revision_semantics(
    tmp_path,
    isolated_prompt_sources,
    monkeypatch,
):
    _, workspace = isolated_prompt_sources
    skills = tmp_path / "skills"
    skill = skills / "review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: review\ndescription: 第一版\n---\n正文 v1",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cloudra.runtime.prompt_assembler.SKILLS_DIR",
        skills,
    )
    agent = _agent(tmp_path, workspace, prompt="固定角色")

    first_request = await agent._build_request_kwargs()
    first = agent.get_runtime_diagnostics()
    await agent.context_manager.set_supervisor_advice("先检查输入。")
    skill.write_text(
        "---\nname: review\ndescription: 第二版\n---\n正文 v2",
        encoding="utf-8",
    )
    second_request = await agent._build_request_kwargs()
    second = agent.get_runtime_diagnostics()

    first_skill = next(
        source
        for source in first["prompt_sources"]
        if source["kind"] == "skills"
    )
    second_skill = next(
        source
        for source in second["prompt_sources"]
        if source["kind"] == "skills"
    )
    assert first_skill["revision"] != second_skill["revision"]
    assert "第一版" in first_request["messages"][0]["content"]
    assert "第二版" in second_request["messages"][0]["content"]
    assert second["supervisor_advice_revision"] != (
        first["supervisor_advice_revision"]
    )
