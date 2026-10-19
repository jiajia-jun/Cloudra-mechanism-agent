"""Invalid arguments must explain the real public schema without side effects."""

import json

import pytest

from cloudra.runtime_v2.adapters import LegacyToolExecutor
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command


async def _invalid_call(name, arguments):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={"name": "invalid input"}))).data
    agent = (await bus.execute(Command(type="agent.spawn", target={"project_id": project.id},
                                      payload={"role_id": "coordinator"}))).data
    result = await LegacyToolExecutor(core).execute(agent, ToolCall("invalid", name, arguments))
    assert not result.is_success
    return result.summary


@pytest.mark.asyncio
async def test_flat_edit_feedback_gives_the_single_actual_nested_shape():
    feedback = await _invalid_call("edit", {"path": "PROCESS.md", "old_string": "old", "new_string": "new"})

    assert "arguments.old_string" in feedback
    assert "arguments.edits: required field is missing" in feedback
    assert "accepted fields at arguments: path, edits" in feedback
    example = json.loads(feedback.split("Example: ", 1)[1])
    assert set(example) == {"path", "edits"}
    assert set(example["edits"][0]) == {"old_string", "new_string"}


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments,path,accepted", [
    ("write", {"path": "x", "content": "x", "Overwrite": True}, "arguments.Overwrite", "path, content"),
    ("query_compute_job", {"job_ids": [1, 2]}, "arguments.job_ids", "job_id, limit"),
    ("log_parser", {"log_file": "x.log"}, "arguments.log_file", "log_path, properties, watch_pairs"),
    ("edit", {"path": "x", "edits": [{"old_string": "a", "new_string": "b", "ReplaceAll": True}]},
     "arguments.edits.0.ReplaceAll", "old_string, new_string, replace_all"),
    ("schedule", {"action": "cancel", "ID": 1}, "arguments.ID", "schedule_id"),
    ("ts_resume", {"run_id": "ts_0001", "reason": "repair profile",
                   "changes": {"calculations": {"B3LYP": {"KeywordsBad": []}}}},
     "arguments.changes.calculations.B3LYP.KeywordsBad", "engine, method, basis_set"),
])
async def test_feedback_retains_unknown_fields_and_lists_accepted_fields(name, arguments, path, accepted):
    feedback = await _invalid_call(name, arguments)

    assert path in feedback
    assert "accepted fields at " in feedback
    assert accepted in feedback
    assert "documented nested shape" not in feedback


@pytest.mark.asyncio
async def test_union_feedback_distinguishes_public_variants_without_implementation_names():
    feedback = await _invalid_call("ts_resume", {
        "run_id": "ts_0001", "reason": "switch profile",
        "changes": {"guess": {"calculation": {"ref": "scan"}}},
    })

    assert "arguments.changes.guess.calculation.ref" in feedback
    assert "arguments.changes.guess.calculation.replace: required field is missing" in feedback
    assert "accepted fields at arguments.changes.guess.calculation: replace" in feedback
    assert "variant" in feedback
    assert "ScanGuessChanges" not in feedback
    assert "QmCalculationChanges" not in feedback
    assert "CalculationReplacement" not in feedback
    assert "ProvidedGuess" not in feedback


def test_discriminated_draft_feedback_preserves_real_paths_and_public_operation_tags():
    from cloudra.dag.drafts import DraftsMixin

    with pytest.raises(RuntimeError) as raised:
        DraftsMixin._validate_draft(
            [{"op": "add_node", "graph": "delivery", "Node": {}}], {}, "invalid shape",
        )

    feedback = str(raised.value)
    assert "operations.0.Node" in feedback
    assert "operations.0.node: required field is missing" in feedback
    assert "accepted fields at operations.0: op, graph, node" in feedback
    assert "variant op='add_node'" in feedback
    assert "AddNode" not in feedback


@pytest.mark.parametrize("operation", [{"graph": "delivery"}, {"op": "WrongOperation", "graph": "delivery"}])
def test_union_tag_feedback_names_the_real_discriminator_and_choices(operation):
    from cloudra.dag.drafts import DraftsMixin

    with pytest.raises(RuntimeError) as raised:
        DraftsMixin._validate_draft([operation], {}, "invalid operation")

    feedback = str(raised.value)
    assert "operation/type tag 'op'" in feedback
    assert "accepted variants:" in feedback
    assert "add_node" in feedback
    assert "AddNode" not in feedback


def test_schema_feedback_does_not_relax_gaussian_memory_admission(tmp_path):
    from cloudra.services.compute_admission import resource_underestimate
    from cloudra.tools.Chemtool.submit_compute_job import SubmitComputeJob_input_schema

    path = tmp_path / "input.gjf"
    path.write_text("%mem=4GB\n# hf/sto-3g\n\ntitle\n\n0 1\nH 0 0 0\n\n")
    args = SubmitComputeJob_input_schema.model_validate({"input_file": str(path), "memory_mb": 4000})

    diagnostic = resource_underestimate("gaussian", str(path), cpus=1, memory_mb=args.memory_mb)

    assert "4096 MB" in diagnostic
    assert "memory_mb=4000" in diagnostic
    assert "Request memory_mb=4096" in diagnostic
