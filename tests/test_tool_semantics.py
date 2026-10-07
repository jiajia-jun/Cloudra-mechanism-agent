"""Registry semantic projections: no downstream per-tool name sets anymore."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloudra.tools import get_tools_lst
from cloudra.tools.capabilities import (
    android_tools,
    evidence_deriver_for,
    is_dag_compute_entry,
    is_dag_observable,
)
from cloudra.tools.registry import TOOL_REGISTRY

# 迁移前 Android runtime profile 的硬编码集合。
# 这里钉住它，防止把语义搬进 registry 的过程中改变行为。
_EXPECTED_ANDROID = frozenset(
    {
        "subagent_launcher",
        "agent_hub",
        "edit",
        "get_subagent_report",
        "get_skill",
        "read",
        "schedule",
        "search",
        "stop",
        "write",
        "update_memory",
    }
)


def test_declared_tool_names_match_loaded_classes():
    loaded = {entry.tool_name for entry in get_tools_lst()}
    for reg in TOOL_REGISTRY:
        if reg.tool_name:
            assert reg.tool_name in loaded, (
                f"registry declares tool_name={reg.tool_name!r} for "
                f"{reg.class_name}, but no loaded tool has that name"
            )


def test_android_projection_keeps_prior_behavior():
    assert android_tools() == _EXPECTED_ANDROID


def test_compute_entry_defaults_to_false_for_plain_tools():
    assert not is_dag_compute_entry("search")
    assert not is_dag_compute_entry("not_a_tool")


def test_bash_compute_entry_predicate():
    assert not is_dag_compute_entry("bash", {"command": "ls -la"})
    assert is_dag_compute_entry("bash", {"command": "echo hi > out.txt"})
    assert is_dag_compute_entry("bash", {"command": "g16 job.gjf"})


def test_dag_observe_projection():
    loaded = {entry.tool_name for entry in get_tools_lst()}
    assert "dag_graph" not in loaded
    assert "dag_view" in loaded
    assert not is_dag_observable("dag_view")
    assert not is_dag_observable("dag_add_species")
    assert not is_dag_observable("get_skill")
    assert is_dag_observable("log_parser")
    assert is_dag_observable("unknown_plugin_tool")


def test_role_allowlist_projection():
    from cloudra.tools.capabilities import role_hidden_tools

    hidden = role_hidden_tools("researcher")
    # 化学/QM 工具对非科学角色隐藏；层级派工只给 Coordinator。
    assert {"log_parser", "submit_compute_job", "ts_guess", "smiles_to_mol"} <= hidden
    assert {"subagent_launcher", "subagent_swarm"} <= hidden
    assert "agent_hub" not in hidden
    assert "bash" not in hidden
    assert "read" not in hidden
    # 谱图处理（ir/nmr）是 experiment 角色专属；其余化学工具科学角色共享。
    assert role_hidden_tools("coordinator") == {"ir_processor", "nmr_processor"}
    assert role_hidden_tools("experiment") == {"subagent_launcher", "subagent_swarm"}
    for role in ("small_mol", "md", "dft"):
        assert role_hidden_tools(role) == {
            "ir_processor", "nmr_processor", "subagent_launcher", "subagent_swarm"
        }, role
    # supervisor 的 evidence_read 面（log_parser/reaction_mapping）不被角色门拿走。
    assert "log_parser" not in role_hidden_tools("supervisor")
    assert "reaction_mapping" not in role_hidden_tools("supervisor")


def test_role_allowlists_reference_known_roles():
    """allowlist 只允许引用内置角色，防止拼写漂移造成静默全员隐藏。"""
    from cloudra.runtime_v2.roles import BUILTIN_ROLES

    known = {role.role_id for role in BUILTIN_ROLES}
    for reg in TOOL_REGISTRY:
        assert set(reg.role_allowlist) <= known, (
            f"{reg.class_name} declares unknown roles: "
            f"{sorted(set(reg.role_allowlist) - known)}"
        )


def test_role_allowlisted_tools_declare_wire_name():
    """capabilities 投影只认显式 tool_name 的条目：带 role_allowlist 的工具
    必须声明 wire 名，否则名单是死字母。"""
    for reg in TOOL_REGISTRY:
        if reg.role_allowlist:
            assert reg.tool_name, f"{reg.class_name} sets role_allowlist without tool_name"


def test_evidence_derivers_are_loadable():
    for tool_name in ("ts_guess", "log_parser", "reaction_mapping", "thermo_analysis"):
        assert evidence_deriver_for(tool_name) is not None, tool_name


def test_no_ghost_tool_names_in_semantics():
    """语义投影只允许引用已加载工具；历史上的 scan_parse 幽灵分支不应复活。"""
    loaded = {entry.tool_name for entry in get_tools_lst()}
    assert android_tools() <= loaded


GONE = {
    "text_reader", "image_reader", "pdf2md", "pdf2image",
    "web_search", "paper_searcher", "openalex_searcher",
    "bashtools", "text_writer", "edit_file", "getskill",
    "web_fetcher", "web_fetch", "headless_browser", "SubAgentLauncher", "SubAgentSwarm",
    "todo_read",
}
REQUIRED = {
    "read", "search", "bash", "write", "edit", "get_skill",
    "browser", "subagent_launcher", "subagent_swarm",
}


def test_registry_wire_names():
    names = {e.tool_name for e in get_tools_lst()}
    assert GONE.isdisjoint(names)
    assert REQUIRED <= names


def test_edit_schema_uses_path_and_old_string():
    edit = next(e for e in get_tools_lst() if e.tool_name == "edit")
    params = edit.instantiate().tool_schema_json()["function"]["parameters"]
    props = params["properties"]
    assert {"path", "expected_sha256", "edits"} <= props.keys()
    assert "filepath" not in props
    assert {"path", "expected_sha256", "edits"} <= set(params["required"])
    edit_item = props["edits"]["items"]
    if "$ref" in edit_item:
        prefix, ref = edit_item["$ref"].rsplit("/", 1)
        assert prefix == "#/$defs"
        edit_item = params["$defs"][ref]
    assert {"old_string", "new_string", "replace_all"} <= edit_item["properties"].keys()
    assert {"old_string", "new_string"} <= set(edit_item["required"])


@pytest.mark.parametrize("missing", ["old_string", "new_string"])
def test_edit_operation_requires_both_published_text_fields(missing):
    edit = next(e for e in get_tools_lst() if e.tool_name == "edit")
    replacement = {"old_string": "before", "new_string": "after"}
    del replacement[missing]
    with pytest.raises(ValidationError) as error:
        edit.input_schema.model_validate({
            "path": "notes.txt", "expected_sha256": "0" * 64, "edits": [replacement],
        })
    assert any(
        item["loc"] == ("edits", 0, missing) and item["type"] == "missing"
        for item in error.value.errors()
    )


def test_get_skill_schema_has_reference_not_other():
    skill = next(e for e in get_tools_lst() if e.tool_name == "get_skill")
    props = skill.instantiate().tool_schema_json()["function"]["parameters"]["properties"]
    assert "reference" in props and "other" not in props


def test_researcher_can_generate_ml_hypotheses_without_qm_tools():
    from cloudra.tools.capabilities import role_hidden_tools
    hidden = role_hidden_tools("researcher")
    assert "mechanism_predict" not in hidden
    assert "submit_compute_job" in hidden
