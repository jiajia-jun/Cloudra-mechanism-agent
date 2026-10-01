"""MCP 工具面投影测试。

覆盖的核心不变量：MCP 可见面永远是 wire 层允许面的子集，且每一条声明式门禁
（role_allowlist / supervisor_access / orchestration_mode / visual / config_gate）
在 MCP 面上都被如实复现。
"""

from __future__ import annotations

from cloudra.tools.capabilities import supervisor_tool_names
from cloudra.tools.mcp_surface import EXCLUDED_FROM_MCP, mcp_tools, visible_tool_names
from cloudra.tools.registry import TOOL_REGISTRY

NAMED = frozenset(reg.tool_name for reg in TOOL_REGISTRY if reg.tool_name)
DAG_TOOLS = frozenset(
    reg.tool_name
    for reg in TOOL_REGISTRY
    if reg.module.startswith("cloudra.tools.Plantool.dag_tools.")
)

# 会遍历的角色：含受 role_allowlist 排除的（explorer/writer）与受 supervisor_access
# 收窄的（supervisor）。
ALL_ROLES = (None, "coordinator", "small_mol", "md", "dft", "experiment",
             "explorer", "writer", "researcher", "env", "supervisor")


def _visible(role_id: str | None, *, mode: str = "dag_guided", visual: bool = True,
             disabled: frozenset[str] = frozenset()) -> frozenset[str]:
    return visible_tool_names(
        role_id=role_id,
        orchestration_mode=mode,
        visual_mode=visual,
        disabled_by_config=disabled,
    )


def test_visible_names_are_always_registered():
    """MCP 可见面不得凭空造出注册表里没有的工具名。"""
    for role in ALL_ROLES:
        for mode in ("standard", "dag_record", "dag_guided"):
            assert _visible(role, mode=mode) <= NAMED


def test_excluded_tools_are_never_visible():
    """宿主自带 / 决定不暴露的工具在任何角色与模式下都不得出现。"""
    for role in ALL_ROLES:
        for mode in ("standard", "dag_record", "dag_guided"):
            assert not (_visible(role, mode=mode) & set(EXCLUDED_FROM_MCP)), (role, mode)


def test_literature_tools_are_excluded_but_email_is_not():
    """search/browser 不暴露；email 保留（由 config_gate 决定，而非静态排除）。"""
    assert {"search", "browser"} <= set(EXCLUDED_FROM_MCP)
    assert not ({"email_reader", "email_sender"} & set(EXCLUDED_FROM_MCP))
    assert "email_sender" in _visible("experiment")


def test_dag_tools_are_hidden_outside_dag_modes():
    """dag_* 只在非 standard 编排模式下有意义。"""
    assert not (_visible("coordinator", mode="standard") & DAG_TOOLS)
    assert DAG_TOOLS <= _visible("coordinator", mode="dag_record")
    assert DAG_TOOLS <= _visible("coordinator", mode="dag_guided")


def test_role_allowlist_is_mirrored():
    """_SCIENCE_ROLES 之外的角色拿不到化学工具；coordinator 必须保留化学工具链。"""
    explorer = _visible("explorer")
    assert "ts_prepare" not in explorer
    assert "submit_compute_job" not in explorer
    assert "internal_coordinates" not in explorer

    coordinator = _visible("coordinator")
    assert "ts_prepare" in coordinator
    assert "submit_compute_job" in coordinator
    assert "internal_coordinates" in coordinator


def test_experiment_only_spectra_are_not_leaked():
    """ir/nmr 谱图工具是 experiment 专属。"""
    for role in ("coordinator", "small_mol", "md", "dft"):
        visible = _visible(role)
        assert "ir_processor" not in visible, role
        assert "nmr_processor" not in visible, role

    experiment = _visible("experiment")
    assert "ir_processor" in experiment
    assert "nmr_processor" in experiment


def test_supervisor_surface_is_exactly_the_access_projection():
    """督导面 = supervisor_access 投影 − MCP 排除项；role_allowlist 只减不增。"""
    expected = frozenset(supervisor_tool_names()) - set(EXCLUDED_FROM_MCP)
    assert _visible("supervisor") == expected


def test_supervisor_cannot_reach_compute_entry_tools():
    """督导是只读裁决者，绝不能拿到计算入口工具。"""
    supervisor = _visible("supervisor")
    for tool in ("submit_compute_job", "ts_prepare", "ts_resume", "qm_input_writer", "ts_guess"):
        assert tool not in supervisor, tool


def test_visual_gate():
    assert "pymol_render" in _visible("coordinator", visual=True)
    assert "pymol_render" not in _visible("coordinator", visual=False)


def test_config_gate_removes_tools():
    disabled = frozenset({"email_sender"})
    assert "email_sender" in _visible("experiment")
    assert "email_sender" not in _visible("experiment", disabled=disabled)


def test_mcp_tools_descriptors_are_well_formed():
    names = _visible("coordinator")
    surface = mcp_tools(names)
    assert surface.tools
    for tool in surface.tools:
        assert tool.name in names
        assert tool.description, f"{tool.name} has no description"
        wire = tool.as_mcp_tool()
        assert set(wire) == {"name", "description", "inputSchema"}
        assert wire["inputSchema"]["type"] == "object"
        # 与 wire 层同一份 schema 生成：必须继续禁止未声明字段。
        assert wire["inputSchema"]["additionalProperties"] is False


def test_dag_tools_resolve_without_optional_chemistry_extras():
    """DAG 工具是纯 Python + Pydantic，任何环境下都必须可用。"""
    surface = mcp_tools(DAG_TOOLS)
    assert surface.unavailable == {}
    assert {tool.name for tool in surface.tools} == DAG_TOOLS


def test_failed_tool_load_is_reported_not_swallowed(monkeypatch):
    """单工具加载失败必须进入 unavailable，而不是静默从工具表消失。"""
    from cloudra.tools import mcp_surface

    target = sorted(DAG_TOOLS)[0]
    real = mcp_surface._describe

    def flaky(reg):
        if reg.tool_name == target:
            raise ImportError("synthetic failure")
        return real(reg)

    monkeypatch.setattr(mcp_surface, "_describe", flaky)
    surface = mcp_surface.mcp_tools(DAG_TOOLS)
    assert target in surface.unavailable
    assert target not in {tool.name for tool in surface.tools}
    assert len(surface.tools) == len(DAG_TOOLS) - 1
