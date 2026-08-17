"""Registry semantic projections: no downstream per-tool name sets anymore."""

from __future__ import annotations

from cloudra.tools import get_tools_lst
from cloudra.tools.capabilities import (
    android_tools,
    evidence_deriver_for,
    is_dag_observable,
    is_substantive_tool,
    substantive_tools,
    supervisor_evidence_tools,
)
from cloudra.tools.registry import TOOL_REGISTRY

# 迁移前 substantive gate 与 Android runtime profile 的硬编码集合。
# 这里钉住它们，防止把语义搬进 registry 的过程中改变行为。
_EXPECTED_SUBSTANTIVE = frozenset(
    {
        "SubAgentLauncher",
        "SubAgentSwarm",
        "text_writer",
        "edit_file",
        "gaussian_log_parser",
        "submit_compute_job",
        "gjf_writer",
        "conformer_search",
        "ts_guess",
        "thermo_analysis",
        "electronic_analysis",
        "ir_processor",
        "nmr_processor",
    }
)
_EXPECTED_ANDROID = frozenset(
    {
        "SubAgentLauncher",
        "agent_hub",
        "edit_file",
        "get_subagent_report",
        "getskill",
        "image_reader",
        "openalex_searcher",
        "paper_searcher",
        "schedule",
        "stop",
        "text_reader",
        "text_writer",
        "update_memory",
        "web_fetcher",
        "web_search",
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


def test_substantive_projection_keeps_prior_behavior():
    assert substantive_tools() == _EXPECTED_SUBSTANTIVE


def test_android_projection_keeps_prior_behavior():
    assert android_tools() == _EXPECTED_ANDROID


def test_substantive_defaults_to_false_for_plain_tools():
    assert not is_substantive_tool("web_search")
    assert not is_substantive_tool("not_a_tool")


def test_bashtools_predicate():
    assert not is_substantive_tool("bashtools", {"command": "ls -la"})
    assert is_substantive_tool("bashtools", {"command": "echo hi > out.txt"})
    assert is_substantive_tool("bashtools", {"command": "g16 job.gjf"})


def test_dag_observe_projection():
    loaded = {entry.tool_name for entry in get_tools_lst()}
    assert "dag_graph" not in loaded
    assert "dag_view" in loaded
    assert not is_dag_observable("dag_view")
    assert not is_dag_observable("dag_add_species")
    assert not is_dag_observable("getskill")
    assert is_dag_observable("gaussian_log_parser")
    assert is_dag_observable("unknown_plugin_tool")


def test_supervisor_evidence_projection():
    assert "gaussian_log_parser" in supervisor_evidence_tools()


def test_evidence_derivers_are_loadable():
    for tool_name in ("ts_guess", "gaussian_log_parser", "reaction_mapping", "thermo_analysis"):
        assert evidence_deriver_for(tool_name) is not None, tool_name


def test_no_ghost_tool_names_in_semantics():
    """语义投影只允许引用已加载工具；历史上的 scan_parse 幽灵分支不应复活。"""
    loaded = {entry.tool_name for entry in get_tools_lst()}
    assert substantive_tools() <= loaded
    assert android_tools() <= loaded
    assert supervisor_evidence_tools() <= loaded
