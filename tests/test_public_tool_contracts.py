"""Model-visible contracts must suffice without application source access."""

import json
from pathlib import Path

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor, legacy_tool_schemas
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command, InvocationProtocol, RuntimeSettings
from cloudra.runtime_v2.tool_catalog import tool_declarations


def test_proposal_wire_schema_describes_declarative_species_and_steps():
    schema = legacy_tool_schemas(["dag_propose_mechanism"])[0]["function"]["parameters"]
    assert "species" in schema["properties"]
    assert "steps" in schema["properties"]
    assert "operations" not in schema["properties"]
    assert "stage_contracts" not in schema["properties"]
    declarations = tool_declarations(
        ["dag_propose_mechanism"], orchestration_mode="dag_guided"
    )
    for field in ('"species"', '"steps"', '"from"', '"to"'):
        assert field in declarations
    for internal in ("operations", "stage_contracts", "claim_spec", "contract_version", "evidence_vetoed", "saddle_supported"):
        assert internal not in declarations


@pytest.mark.asyncio
async def test_invalid_proposal_returns_public_field_help_without_internal_exception():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "contract test"}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator", "query": "test"},
    ))
    await bus.execute(Command(
        type="agent.settings_update", target={"session_id": spawned.data.id},
        payload={"orchestration_mode": "dag_guided"},
    ))
    result = await LegacyToolExecutor(core).execute(spawned.data, ToolCall(
        id="bad-proposal", name="dag_propose_mechanism",
        arguments={"species": [{"invalid": "node"}], "rationale": "hypothesis"},
    ))
    assert not result.is_success
    assert "species" in result.summary
    for internal in ("pydantic", "input_value", "tagged-union", "DagPropose", "Traceback"):
        assert internal not in result.summary


def test_new_settings_default_to_javascript_but_explicit_traditional_is_preserved():
    assert RuntimeSettings().invocation_protocol is InvocationProtocol.JAVASCRIPT
    assert RuntimeSettings(invocation_protocol="traditional").invocation_protocol is InvocationProtocol.TRADITIONAL


def test_research_prompt_excludes_application_checkout_context(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloudra.runtime.prompt_assembler import PromptAssembler

    root = tmp_path / "application"
    (root / "cloudra" / "runtime").mkdir(parents=True)
    (root / "cloudra" / "runtime" / "prompt_assembler.py").write_text("# application source")
    (root / "pyproject.toml").write_text('[project]\nname = "cloudra"\n')
    (root / "AGENTS.md").write_text("DEVELOPER_ONLY_INTERNAL_MAP")
    (root / "old_answer.json").write_text("{}")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "AGENTS.md").write_text("USER_RESEARCH_RULE")
    monkeypatch.setattr("cloudra.runtime.prompt_assembler.get_config", lambda: SimpleNamespace(
        config_file=config_dir / "config.yaml",
    ))
    assembler = PromptAssembler(
        prompt_name=None, custom_prompt="Research the chemistry.", conversation_id="p",
        working_directory=str(root), include_memory=False,
    )
    sections = assembler._agents_md_sections()
    assert "DEVELOPER_ONLY_INTERNAL_MAP" not in str(sections)
    assert "USER_RESEARCH_RULE" in str(sections)
    observation, _ = assembler._workspace_observation([])
    assert "old_answer.json" not in observation["content"]
    assert "working_directory=" in observation["content"]


def test_documented_proposal_can_be_validated_by_the_real_controller():
    from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanismInput

    skill = Path("cloudra/skills/dag-operations/SKILL.md").read_text()
    assert "```json" in skill
    example = json.loads(skill.split("```json\n", 1)[1].split("```", 1)[0])
    parsed = DagProposeMechanismInput.model_validate(example)
    assert len(parsed.species) == 2
    assert len(parsed.steps) == 1
    assert parsed.species[0].name == "Reactant Complex"
    assert parsed.steps[0].name == "Diels-Alder Cycloaddition"


@pytest.mark.asyncio
async def test_unexpected_tool_failure_logs_details_but_does_not_send_them_to_model(monkeypatch, caplog):
    from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism

    async def broken(*args):
        raise OSError("private implementation /private/app/runtime.py failed")

    monkeypatch.setattr(DagProposeMechanism, "tool_call", broken)
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(Command(
        type="agent.spawn", target={"project_id": project.id}, payload={"role_id": "coordinator"},
    ))
    result = await LegacyToolExecutor(core).execute(spawned.data, ToolCall(
        id="failure", name="dag_propose_mechanism", arguments={
            "species": [{"name": "R"}], "steps": [], "rationale": "test",
        },
    ))
    assert not result.is_success and result.error.effect_state == "unknown"
    assert "/private/app" not in result.summary
    assert "/private/app" not in result.error.message
    assert "/private/app" in caplog.text
