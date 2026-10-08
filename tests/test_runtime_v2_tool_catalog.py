"""Tool catalog: JS declarations, wire projection, route validation."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from cloudra.runtime_v2.schemas import (
    AgentSession,
    CurrentRun,
    InvocationProtocol,
    OrchestrationMode,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.tool_catalog import (
    JS_EXEC_NAME,
    guest_tool_names,
    js_exec_schema,
    tool_declarations,
    validate_wire_route,
    wire_tool_schemas,
)
from cloudra.tools import ToolEntry
from cloudra.tools.capabilities import is_direct_only


def _agent(
    *,
    protocol=InvocationProtocol.TRADITIONAL,
    running=False,
    read_only=False,
    role_id="explorer",
) -> AgentSession:
    agent = AgentSession(
        id="a",
        project_id="p",
        role_id=role_id,
        display_name=role_id,
    )
    agent.settings.invocation_protocol = protocol
    if read_only:
        agent.capabilities.permissions = PermissionSet(read=True)
    if running:
        agent.current_run = CurrentRun(
            run_id="r1",
            started_at=agent.created_at,
            invocation_protocol=InvocationProtocol.JAVASCRIPT,
        )
    return agent


def _names(schemas: list[dict]) -> list[str]:
    return [(s.get("function") or {}).get("name") for s in schemas]


# ------------------------------------------------------------------ wire projection


def test_traditional_projection_returns_business_schemas():
    # coordinator 在化学工具 role_allowlist 内；非科学角色看不到 log_parser
    # （见下方 role allowlist 测试）。
    schemas = wire_tool_schemas(_agent(role_id="coordinator"), ["log_parser"])
    assert _names(schemas) == ["log_parser"]
    assert JS_EXEC_NAME not in _names(schemas)


def test_js_projection_returns_js_exec_and_direct_controls_only():
    schemas = wire_tool_schemas(_agent(protocol=InvocationProtocol.JAVASCRIPT), ["*"])
    names = _names(schemas)
    assert names[0] == JS_EXEC_NAME
    assert set(names) == {JS_EXEC_NAME, "stop", "ask_user", "schedule"}


def test_unattended_agent_wire_hides_ask_user():
    """GH #31：无人值守评测下 ask_user 不得出现在线缆投影；其他 direct
    controls（stop/schedule）不受影响。"""
    agent = _agent(protocol=InvocationProtocol.JAVASCRIPT)
    agent.settings.unattended = True
    names = _names(wire_tool_schemas(agent, ["*"]))
    assert "ask_user" not in names
    assert {"stop", "schedule"} <= set(names)


def test_attended_agent_wire_keeps_ask_user():
    names = _names(wire_tool_schemas(_agent(protocol=InvocationProtocol.JAVASCRIPT), ["*"]))
    assert "ask_user" in names


def test_js_projection_with_empty_capabilities_exposes_no_business_tools():
    schemas = wire_tool_schemas(_agent(protocol=InvocationProtocol.JAVASCRIPT), [])
    assert _names(schemas) == [JS_EXEC_NAME]
    declarations = tool_declarations([], visual_mode=True)
    assert "declare const tools: Record<string, never>;" in declarations


def test_read_only_agent_may_select_javascript():
    # permission.script governs script-capable backend tools, not the protocol.
    agent = _agent(protocol=InvocationProtocol.JAVASCRIPT, read_only=True)
    assert JS_EXEC_NAME in _names(wire_tool_schemas(agent, ["*"]))


def test_js_exec_schema_shape_is_stable():
    schema = js_exec_schema()
    function = schema["function"]
    assert function["name"] == "js_exec"
    assert function["parameters"]["required"] == ["code"]
    assert function["parameters"]["additionalProperties"] is False


def test_js_declarations_preserve_tool_workflow_description():
    """JS guests need the same workflow/permission guidance as chat callers."""
    from dataclasses import dataclass

    @dataclass
    class Entry:
        tool_name: str = "demo_tool"
        tool_description: str = "Use this after validation; do not use for raw guesses."
        input_schema: object = None
        output_schema: object = None

    rendered = tool_declarations(["demo_tool"], entries=[Entry()])
    assert "Use this after validation; do not use for raw guesses." in rendered


def test_js_declarations_project_constraints_and_escape_comments():
    class Schema(BaseModel):
        value: int = Field(3, ge=1, le=9, description="value */ safely")

    class Entry:
        tool_name = "bounded"
        tool_description = ""
        input_schema = Schema
        output_schema = None

    rendered = tool_declarations(["bounded"], entries=[Entry()])
    assert "default=3" in rendered
    assert "min 1" in rendered and "max 9" in rendered
    assert "value */ safely" not in rendered


# ------------------------------------------------------- orchestration mode gate


def _mode_agent(mode: OrchestrationMode) -> AgentSession:
    # coordinator 携带全量业务工具（role_allowlist 内），隔离模式门本身的行为。
    agent = _agent(role_id="coordinator")
    agent.settings.orchestration_mode = mode
    return agent


def test_dag_tools_hidden_in_standard_mode():
    from cloudra.tools.capabilities import dag_tools

    assert {"dag_view", "dag_submit_step_evidence", "dag_propose_mechanism"} <= dag_tools()
    names = set(_names(wire_tool_schemas(_mode_agent(OrchestrationMode.STANDARD), ["*"])))
    assert "log_parser" in names
    assert not (names & dag_tools())
    guest = guest_tool_names(
        ["dag_view", "log_parser"], orchestration_mode=OrchestrationMode.STANDARD
    )
    assert guest == ["log_parser"]


def test_supervisor_review_decision_tools_hidden_in_dag_record():
    from cloudra.tools.capabilities import dag_review_decision_tools

    assert {
        "dag_accept_mechanism",
        "dag_review_step",
        "dag_review_species",
    } <= dag_review_decision_tools()
    names = set(_names(wire_tool_schemas(_mode_agent(OrchestrationMode.DAG_RECORD), ["*"])))
    assert {"dag_view", "dag_submit_step_evidence", "dag_propose_mechanism"} <= names
    assert not (names & dag_review_decision_tools())


def test_all_dag_tools_visible_in_dag_guided():
    names = set(_names(wire_tool_schemas(_mode_agent(OrchestrationMode.DAG_GUIDED), ["*"])))
    assert {
        "dag_view",
        "dag_submit_step_evidence",
        "dag_submit_species_evidence",
        "dag_review_step",
        "dag_review_species",
        "dag_accept_mechanism",
        "dag_propose_mechanism",
        # Task 1/3：删除与送审/裁决/证据工具同样在 guided 全量可见。
        "dag_remove_node",
        "dag_remove_edge",
        "dag_bind_evidence",
        "dag_review_call",
        "dag_review_evidence",
        "dag_view_evidence",
        "dag_set_coverage_contract",
        "dag_message_supervisor",
    } <= names


def test_research_agent_guest_declarations_include_removal_tools():
    """dag_guided 下研究 agent 的 JS guest 声明里实际出现删节点/删边函数。"""
    text = tool_declarations(
        ["*"], orchestration_mode=OrchestrationMode.DAG_GUIDED
    )
    assert "dag_remove_node(" in text
    assert "dag_remove_edge(" in text
    assert "dag_review_call(" in text
    assert "dag_bind_evidence(" in text


def test_supervisor_cannot_discover_removal_tools():
    """删图工具不授予 supervisor_access：督导的能力投影里没有删除工具。"""
    from cloudra.tools.capabilities import supervisor_allowed_tools

    allowed = supervisor_allowed_tools()
    assert "dag_remove_node" not in allowed
    assert "dag_remove_edge" not in allowed
    assert "dag_view_evidence" in allowed  # evidence_read
    assert allowed["dag_view_evidence"] == "evidence_read"


def test_guest_declarations_follow_orchestration_mode():
    text = tool_declarations(
        ["dag_view", "log_parser"], orchestration_mode=OrchestrationMode.STANDARD
    )
    assert "dag_view(" not in text and "log_parser(" in text
    text = tool_declarations(
        ["dag_view", "dag_review_step"], orchestration_mode=OrchestrationMode.DAG_RECORD
    )
    assert "dag_view(" in text and "dag_review_step(" not in text


# ------------------------------------------------------------------ role allowlist


def test_hierarchical_dispatch_tools_are_coordinator_only_on_wire_and_guest():
    for role in ("explorer", "researcher", "small_mol", "supervisor"):
        names = set(_names(wire_tool_schemas(_agent(role_id=role), ["*"])))
        assert "agent_hub" in names
        assert "subagent_launcher" not in names
        assert "subagent_swarm" not in names
        guest = guest_tool_names(["*"], role_id=role)
        assert "subagent_launcher" not in guest
        assert "subagent_swarm" not in guest
    coordinator_names = set(_names(wire_tool_schemas(_agent(role_id="coordinator"), ["*"])))
    assert {"agent_hub", "subagent_launcher", "subagent_swarm"} <= coordinator_names


def test_role_allowlist_hides_chem_tools_from_non_science_roles():
    for role in ("explorer", "writer", "researcher", "env"):
        names = set(_names(wire_tool_schemas(_agent(role_id=role), ["*"])))
        assert "log_parser" not in names, role
        assert "submit_compute_job" not in names, role
        assert "smiles_to_mol" not in names, role
        # 通用工具不设 allowlist，不受角色门影响。
        assert {"read", "bash", "search"} <= names, role


def test_role_allowlist_keeps_chem_tools_for_science_roles():
    """coordinator 保留完整化学工具链是 benchmark 回归红线（题面 agent 以
    coordinator 角色运行）；supervisor 在列只为保住其 evidence_read 面。"""
    for role in ("coordinator", "small_mol", "md", "dft", "experiment", "supervisor"):
        names = set(_names(wire_tool_schemas(_agent(role_id=role), ["*"])))
        assert "log_parser" in names, role
        assert "submit_compute_job" in names, role


def test_role_allowlist_filters_guest_names_and_declarations():
    guest = guest_tool_names(["*"], role_id="researcher")
    assert "log_parser" not in guest
    assert "mechanism_predict" in guest
    assert "bash" in guest
    text = tool_declarations(["*"], role_id="researcher")
    assert "log_parser(" not in text
    text = tool_declarations(["*"], role_id="small_mol")
    assert "log_parser(" in text
    # 不传 role_id 的调用方（如静态检查）不做角色过滤。
    assert "log_parser" in guest_tool_names(["*"])


def test_permission_stage_blocks_role_restricted_tool():
    import asyncio

    from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
    from cloudra.runtime_v2.policies.permission import PermissionStage
    from cloudra.runtime_v2.schemas import AgentCapabilities, PermissionSet

    def ctx(role_id: str) -> PipelineContext:
        return PipelineContext(
            agent=_agent(role_id=role_id),
            run_id="r",
            settings_snapshot=RuntimeSettings(),
            capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
            inbox_messages=[],
            emit=lambda *_args, **_kwargs: None,
        )

    stage = PermissionStage()
    blocked = asyncio.run(stage.before_tool(ctx("researcher"), ToolCall(id="t1", name="log_parser")))
    assert blocked.outcome == "block"
    assert "researcher" in blocked.message
    allowed = asyncio.run(stage.before_tool(ctx("small_mol"), ToolCall(id="t2", name="log_parser")))
    assert allowed.outcome == "allow"
    unrestricted = asyncio.run(stage.before_tool(ctx("researcher"), ToolCall(id="t3", name="bash")))
    assert unrestricted.outcome == "allow"
    hypothesis = asyncio.run(stage.before_tool(ctx("researcher"), ToolCall(id="t4", name="mechanism_predict")))
    assert hypothesis.outcome == "allow"


# ----------------------------------------------------------------------- routing


def test_validate_wire_route_traditional_rejects_js_exec():
    error = validate_wire_route("traditional", JS_EXEC_NAME)
    assert error is not None and "js_exec_in_traditional" in error
    assert validate_wire_route("traditional", "log_parser") is None


def test_validate_wire_route_javascript_rejects_toplevel_business_calls():
    error = validate_wire_route("javascript", "log_parser")
    assert error is not None and "business_call_outside_program" in error
    assert validate_wire_route("javascript", JS_EXEC_NAME) is None
    assert validate_wire_route("javascript", "stop") is None
    assert validate_wire_route("javascript", "ask_user") is None


def test_validate_wire_route_guest_rejects_direct_controls():
    error = validate_wire_route("javascript", "stop", origin="guest")
    assert error is not None and "direct_only_in_guest" in error
    assert validate_wire_route("javascript", "log_parser", origin="guest") is None
    assert validate_wire_route("javascript", JS_EXEC_NAME, origin="guest") is not None


def test_direct_only_projection_marks_stop_ask_user_schedule():
    assert is_direct_only("stop")
    assert is_direct_only("ask_user")
    assert is_direct_only("schedule")
    assert not is_direct_only("log_parser")
    assert not is_direct_only("unregistered_test_tool")


# ------------------------------------------------------------------- declarations


def test_guest_names_resolve_wildcard_and_exclude_direct_controls():
    names = guest_tool_names(["*"], visual_mode=True)
    assert "log_parser" in names
    assert "bash" in names
    assert "stop" not in names
    assert "ask_user" not in names
    assert "schedule" not in names
    assert names == sorted(names)


def test_guest_names_expand_wildcard_from_single_pass_iterable():
    names = guest_tool_names(iter(["*", "echo"]), role_id="researcher")
    assert {"bash", "read", "echo"} <= set(names)
    assert "log_parser" not in names
    assert "stop" not in names


def test_guest_names_respect_visual_gate():
    assert "pymol_render" in guest_tool_names(["pymol_render"], visual_mode=True)
    assert "pymol_render" not in guest_tool_names(["pymol_render"], visual_mode=False)
    assert "pymol_render" not in guest_tool_names(["*"], visual_mode=False)


class SubModel(BaseModel):
    smiles: str = Field(description="A SMILES string")


class SampleArgs(BaseModel):
    log_path: str = Field(description="Absolute path to the log file")
    engine: str = "orca"
    mode: Optional[str] = None
    level: Literal["low", "high"] = "low"
    targets: list[SubModel] = Field(default_factory=list)
    attempts: int = 3


class SampleData(BaseModel):
    value: float
    note: Optional[str] = None


class WeirdArgs(BaseModel):
    class Config:
        extra = "allow"

    payload: Any = None


def _entry(name: str, args, data) -> ToolEntry:
    return ToolEntry(
        cls=type("FakeTool", (), {}),
        tool_name=name,
        tool_id=f"t-{name}",
        input_schema=args,
        output_schema=data,
    )


def _sample_declarations() -> str:
    entries = [_entry("sample_tool", SampleArgs, SampleData)]
    return tool_declarations(["sample_tool"], visual_mode=True, entries=entries)


def test_declarations_render_required_and_optional_args():
    text = _sample_declarations()
    assert '"log_path": string;' in text
    assert '"engine"?: string;' in text
    assert '"attempts"?: number;' in text
    assert "/** Absolute path to the log file */" in text


def test_declarations_render_output_data_fields():
    text = _sample_declarations()
    assert "type SampleToolData = {" in text
    assert '"value": number;' in text
    assert '"note"?: string | null;' in text
    assert "sample_tool(args: SampleToolArgs): Promise<ToolResponse<SampleToolData>>;" in text


def test_declarations_render_enum_array_nullable_and_refs():
    text = _sample_declarations()
    assert '"level"?: "low" | "high";' in text
    assert '"targets"?: Array<SampleToolArgs_SubModel>;' in text
    assert '"mode"?: string | null;' in text
    assert "type SampleToolArgs_SubModel = {" in text
    assert '"smiles": string;' in text


def test_declarations_preserve_fixed_tuple_atom_references():
    from cloudra.tools.core.ts_inputs import RotatedConformer, TsReaction

    text = tool_declarations(
        ["rotate", "reaction"],
        entries=[
            _entry("rotate", RotatedConformer, SampleData),
            _entry("reaction", TsReaction, SampleData),
        ],
    )
    assert '"atoms": [number, number];' in text
    assert '"reaction_center"?: Array<[number, number]>;' in text


def test_declarations_preserve_heterogeneous_tuple_members():
    class TaggedCoordinate(BaseModel):
        coordinate: tuple[Literal["bond"], int, int]
        labeled: tuple[SubModel, str | None]

    text = tool_declarations(
        ["coordinate"], entries=[_entry("coordinate", TaggedCoordinate, SampleData)],
    )
    assert '"coordinate": ["bond", number, number];' in text
    assert '"labeled": [CoordinateArgs_SubModel, string | null];' in text


def test_declarations_preserve_shared_fields_with_mode_conditions():
    class ModeArgs(BaseModel):
        model_config = ConfigDict(json_schema_extra={"oneOf": [
            {
                "properties": {"mode": {"const": "scan"}}, "required": ["mode"],
                "anyOf": [
                    {"properties": {"input_path": {"type": "string"}}, "required": ["input_path"]},
                    {"properties": {"input_text": {"type": "string"}}, "required": ["input_text"]},
                ],
            },
            {
                "properties": {"mode": {"const": "verify"}, "log_path": {"type": "string"}},
                "required": ["mode", "log_path"],
            },
        ]})
        mode: Literal["scan", "verify"]
        engine: str
        input_path: str | None = None
        input_text: str | None = None
        log_path: str | None = None

    text = tool_declarations(["mode_tool"], entries=[_entry("mode_tool", ModeArgs, SampleData)])
    assert '"engine": string;' in text
    assert '"mode": "scan";' in text
    assert '"input_path": string;' in text
    assert '"input_text": string;' in text
    assert '"mode": "verify";' in text
    assert '"log_path": string;' in text
    assert " & " in text


def test_declarations_are_deterministic_and_escape_comments():
    class Nasty(BaseModel):
        weird_name: str = Field(description="ends a comment */ and opens /* one")

    entries = [
        _entry("zeta_tool", SampleArgs, SampleData),
        _entry("alpha_tool", Nasty, SampleData),
    ]
    first = tool_declarations(["zeta_tool", "alpha_tool"], visual_mode=True, entries=entries)
    second = tool_declarations(["alpha_tool", "zeta_tool"], visual_mode=True, entries=list(reversed(entries)))
    assert first == second
    assert first.index("alpha_tool(") < first.index("zeta_tool(")
    assert "*\\/" in first


def test_unknown_schema_constructs_become_unknown_never_any():
    text = tool_declarations(["weird_tool"], visual_mode=True,
                             entries=[_entry("weird_tool", WeirdArgs, None)])
    assert '"payload"?: unknown;' in text
    assert ": any" not in text
    # Missing output schema degrades to an unknown record, not an invention.
    assert "WeirdToolData = unknown;" in text


def test_undeclared_test_tools_use_record_types():
    text = tool_declarations(["echo"], visual_mode=True, entries=[])
    assert "echo(args: Record<string, unknown>): Promise<ToolResponse<Record<string, unknown>>>;" in text


def test_real_registry_declarations_smoke():
    text = tool_declarations(["log_parser"], visual_mode=True)
    assert "log_parser(args: LogParserArgs)" in text
    assert "ToolResponse<LogParserData>" in text
