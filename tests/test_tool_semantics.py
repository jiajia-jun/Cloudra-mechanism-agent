"""Registry semantic projections: no downstream per-tool name sets anymore."""

from __future__ import annotations

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
        "web_fetch",
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
    "web_fetcher", "headless_browser", "SubAgentLauncher", "SubAgentSwarm",
}
REQUIRED = {
    "read", "search", "bash", "write", "edit", "get_skill",
    "web_fetch", "browser", "subagent_launcher", "subagent_swarm",
}


def test_registry_wire_names():
    names = {e.tool_name for e in get_tools_lst()}
    assert GONE.isdisjoint(names)
    assert REQUIRED <= names


def test_edit_schema_uses_path_and_old_string():
    edit = next(e for e in get_tools_lst() if e.tool_name == "edit")
    params = edit.instantiate().tool_schema_json()["function"]["parameters"]
    props = params["properties"]
    assert "path" in props and "filepath" not in props
    edit_item = props["edits"]["items"]
    keys = edit_item.get("properties") or edit_item
    if "$ref" in edit_item:
        ref = edit_item["$ref"].rsplit("/", 1)[-1]
        keys = params.get("$defs", {}).get(ref, {}).get("properties", keys)
    # $ref unwrap if needed
    assert "old_string" in keys or "old_string" in str(params)


def test_get_skill_schema_has_reference_not_other():
    skill = next(e for e in get_tools_lst() if e.tool_name == "get_skill")
    props = skill.instantiate().tool_schema_json()["function"]["parameters"]["properties"]
    assert "reference" in props and "other" not in props
