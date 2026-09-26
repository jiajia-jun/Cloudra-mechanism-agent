"""Tests for skill discovery, role-tailored skill recommendations, and AgentHub skill integration."""

from types import SimpleNamespace

import pytest

from cloudra.runtime.prompt_assembler import PromptAssembler
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command
from cloudra.tools.Skilltool.get_skill import GetSkill, GetSkill_input_schema


@pytest.mark.asyncio
async def test_get_skill_empty_or_list_shows_catalog():
    """Empty name or 'list' returns available skill catalog."""
    tool = GetSkill()
    res_empty = await tool.tool_call(GetSkill_input_schema(skill_name=""), None)
    assert res_empty.is_success is True
    assert "Available Skills Catalog" in res_empty.content
    assert "reaction-mechanisms" in res_empty.content
    assert "dft-calculation" in res_empty.content

    res_list = await tool.tool_call(GetSkill_input_schema(skill_name="list"), None)
    assert res_list.is_success is True
    assert "reaction-mechanisms" in res_list.content


@pytest.mark.asyncio
async def test_get_skill_fuzzy_matching():
    """Misspelled skill name suggests close matches."""
    tool = GetSkill()
    res = await tool.tool_call(GetSkill_input_schema(skill_name="reaction-mech"), None)
    assert res.is_success is False
    assert "Did you mean 'reaction-mechanisms'?" in res.result
    assert "Available skills:" in res.result


@pytest.mark.asyncio
async def test_get_skill_includes_references():
    """get_skill automatically appends available reference files if present."""
    tool = GetSkill()
    res = await tool.tool_call(GetSkill_input_schema(skill_name="reaction-mechanisms"), None)
    assert res.is_success is True
    assert "Organic Reaction Mechanisms & Competing Pathways Playbook" in res.content
    assert "Available Reference Guides in 'reaction-mechanisms'" in res.content
    assert "carbonyl.md" in res.content
    assert "pericyclic.md" in res.content
    assert "radical.md" in res.content


@pytest.mark.asyncio
async def test_hub_search_finds_skills():
    """agent_hub(action='search', keyword=...) searches skills dynamically."""
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "test_proj"}))
    project = next(iter(core.projects.values()))
    spawn_res = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "investigate mechanism"},
        )
    )
    agent = spawn_res.data

    call = ToolCall(
        id="t1",
        name="agent_hub",
        arguments={"action": "search", "keyword": "reaction"},
    )
    res = await handle_hub_tool(core, agent, call)
    assert res.is_success is True
    assert "Matched Domain Skills:" in res.summary
    assert "reaction-mechanisms" in res.summary
    assert any(s["name"] == "reaction-mechanisms" for s in res.data["skills"])


def test_prompt_assembler_tailored_role_skills(tmp_path, monkeypatch):
    """Known roles receive tailored skill recommendations; unmapped roles receive full manifest."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "small_mol.md").write_text("# Small Mol", encoding="utf-8")
    (prompts_dir / "explorer.md").write_text("# Explorer", encoding="utf-8")
    (prompts_dir / "custom_role.md").write_text("# Custom", encoding="utf-8")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    config = SimpleNamespace(config_file=config_dir / "config.toml")

    monkeypatch.setattr("cloudra.runtime.prompt_assembler.PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr("cloudra.runtime.prompt_assembler.get_config", lambda: config)

    # 1. small_mol should get recommended skills: dft-calculation, reaction-mechanisms
    asm_sm = PromptAssembler(
        prompt_name="small_mol",
        custom_prompt=None,
        conversation_id="c1",
        working_directory=str(workspace),
        include_memory=False,
    )
    content_sm = asm_sm.assemble([]).identity_messages[0]["content"]
    assert "## Recommended Domain Skills" in content_sm
    assert "- dft-calculation:" in content_sm
    assert "- reaction-mechanisms:" in content_sm
    assert "agent_hub(action=\"search\", keyword=\"skill <domain>\")" in content_sm
    assert "- literature-search:" not in content_sm

    # 2. explorer has empty recommendation tuple -> Domain Skills On-Demand
    asm_exp = PromptAssembler(
        prompt_name="explorer",
        custom_prompt=None,
        conversation_id="c2",
        working_directory=str(workspace),
        include_memory=False,
    )
    content_exp = asm_exp.assemble([]).identity_messages[0]["content"]
    assert "## Domain Skills On-Demand" in content_exp
    assert "agent_hub(action=\"search\", keyword=\"skill <domain>\")" in content_exp
    assert "## Recommended Domain Skills" not in content_exp

    # 3. custom_role is not in _ROLE_RECOMMENDED_SKILLS -> Full manifest fallback
    asm_cust = PromptAssembler(
        prompt_name="custom_role",
        custom_prompt=None,
        conversation_id="c3",
        working_directory=str(workspace),
        include_memory=False,
    )
    content_cust = asm_cust.assemble([]).identity_messages[0]["content"]
    assert "## Current skill manifest" in content_cust
    assert "- reaction-mechanisms:" in content_cust
    assert "- dft-calculation:" in content_cust
