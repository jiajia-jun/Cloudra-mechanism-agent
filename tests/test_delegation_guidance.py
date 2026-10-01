"""Regression checks for model-facing delegation contracts, not model behavior."""

import pytest

from cloudra.runtime.prompt_assembler import PromptAssembler
from cloudra.runtime_v2.schemas import AgentSession, InvocationProtocol
from cloudra.runtime_v2.tool_catalog import tool_declarations, wire_tool_schemas


def test_coordinator_assembly_requires_proactive_delegation(tmp_path):
    assembly = PromptAssembler(
        prompt_name="coordinator",
        custom_prompt=None,
        conversation_id="delegation-guidance",
        working_directory=str(tmp_path),
        include_memory=False,
        include_agents_md=False,
    ).assemble(["subagent_launcher", "subagent_swarm", "agent_hub"])
    prompt = assembly.identity_messages[0]["content"]

    assert "must proactively delegate" in prompt
    assert "Run independent assignments in parallel" in prompt
    assert "brief requests directly" in prompt
    assert "not a fixed list of delegable task types" in prompt
    assert "Do not prescribe tool whitelists or step-by-step tool sequences" in prompt
    assert "Specialists may talk directly to one another" in prompt


@pytest.mark.parametrize(
    ("tool_name", "task_field"),
    [("subagent_launcher", "query"), ("subagent_swarm", "prompt_template")],
)
def test_dispatch_guidance_uses_goal_contracts_on_both_protocols(tool_name, task_field):
    agent = AgentSession(
        id="coordinator", project_id="delegation-guidance", role_id="coordinator",
        display_name="Coordinator",
    )
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    function = wire_tool_schemas(agent, [tool_name])[0]["function"]
    task_description = function["parameters"]["properties"][task_field]["description"]
    declarations = tool_declarations([tool_name], role_id="coordinator")

    for surface in (function["description"], task_description, declarations):
        assert "Do not prescribe tool whitelists or step-by-step tool sequences" in surface
        assert "allowed tools" not in surface
        assert "forbidden tools" not in surface
    assert "evidence" in task_description
    assert "done criteria" in task_description
    assert "agent_hub" in function["description"]
