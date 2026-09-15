"""mechanism_predict（FlowER 外部环境封装）的测试。

纯逻辑测试不依赖 conda/torch；真实冒烟仅在 flower env 与检查点都已就位时跑
（环境探测 skipif，与 tests/test_benchmark_sandbox_fp.py 的 _REQUIRES_* 先例一致）。
"""

from __future__ import annotations

import os
import shutil

import pytest

from cloudra.infra.config import DEFAULT_DATA_DIR, get_config
from cloudra.runtime_v2.schemas import AgentSession, InvocationProtocol
from cloudra.runtime_v2.tool_catalog import guest_tool_names, wire_tool_schemas
from cloudra.tools.capabilities import config_disabled_tools
from cloudra.tools.Chemtool.mechanism_predict import (
    MechanismPredict,
    MechanismPredict_input_schema,
    enumerate_pathways,
)

try:
    import rdkit  # noqa: F401
    _RDKIT_AVAILABLE = True
except Exception:
    _RDKIT_AVAILABLE = False

_REQUIRES_RDKIT = pytest.mark.skipif(not _RDKIT_AVAILABLE, reason="rdkit not installed")

# 真实冒烟的环境探测：conda env `flower` 的 python + 默认安装位的仓库与检查点。
# conftest 把 config 文件隔离到临时路径，测试读不到真实 config 里的 flower.*，
# 因此这里直接探测 setup 脚本的默认安装位置（只读，不写真实数据目录）。
_SMOKE_PYTHON = ""
_conda_base = shutil.which("conda")
if _conda_base:
    _cand = os.path.join(
        os.path.dirname(os.path.dirname(_conda_base)), "envs", "flower", "bin", "python"
    )
    if os.path.isfile(_cand):
        _SMOKE_PYTHON = _cand
_SMOKE_REPO = os.path.join(
    # 与 setup 脚本默认安装位一致：platformdirs 的 user_data_dir（macOS 是
    # ~/Library/Application Support/cloudra，不是 ~/.local/share）
    str(DEFAULT_DATA_DIR), "external", "FlowER"
)
_SMOKE_CHECKPOINT = ""
if os.path.isdir(os.path.join(_SMOKE_REPO, "checkpoints")):
    for _root, _dirs, _files in os.walk(os.path.join(_SMOKE_REPO, "checkpoints")):
        for _name in sorted(_files):
            if _name.startswith("model.") and _name.endswith(".pt"):
                _SMOKE_CHECKPOINT = os.path.join(_root, _name)
                break
        if _SMOKE_CHECKPOINT:
            break
_SMOKE_READY = bool(_SMOKE_PYTHON and _SMOKE_CHECKPOINT)
_REQUIRES_FLOWER_ENV = pytest.mark.skipif(
    not _SMOKE_READY,
    reason="flower conda env/checkpoint not installed (run scripts/setup_flower.sh)",
)


def _agent() -> AgentSession:
    agent = AgentSession(id="a", project_id="p", role_id="explorer", display_name="explorer")
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return agent


def _wire_names(agent: AgentSession, tool_names: list[str]) -> list[str]:
    return [
        (s.get("function") or {}).get("name")
        for s in wire_tool_schemas(agent, tool_names)
    ]


def _enable_flower(monkeypatch, tmp_path=None, *, configured: bool = True):
    """打开开关；configured=True 时把三个路径指到 tmp_path 下的占位文件。"""
    flower = get_config().flower
    monkeypatch.setattr(flower, "enabled", True)
    if configured:
        assert tmp_path is not None
        repo = tmp_path / "repo"
        repo.mkdir(exist_ok=True)
        env_python = tmp_path / "python"
        env_python.touch()
        checkpoint = tmp_path / "model.1_0.pt"
        checkpoint.touch()
        monkeypatch.setattr(flower, "repo_dir", str(repo))
        monkeypatch.setattr(flower, "env_python", str(env_python))
        monkeypatch.setattr(flower, "checkpoint", str(checkpoint))
    return flower


# ----------------------------------------------------------------- 开关与投影

def test_config_gate_disabled_by_default():
    assert "mechanism_predict" in config_disabled_tools()
    assert "mechanism_predict" not in _wire_names(_agent(), ["mechanism_predict"])
    assert "mechanism_predict" not in guest_tool_names(["mechanism_predict"])


def test_config_gate_enabled_makes_tool_visible(monkeypatch):
    _enable_flower(monkeypatch, configured=False)
    assert "mechanism_predict" not in config_disabled_tools()
    assert "mechanism_predict" in _wire_names(_agent(), ["mechanism_predict"])
    assert "mechanism_predict" in guest_tool_names(["mechanism_predict"])


def test_config_gate_unknown_path_fails_closed(monkeypatch):
    import cloudra.tools.registry as registry_mod
    from cloudra.tools import capabilities
    from cloudra.tools.registry import TOOL_REGISTRY, ToolRegistration

    bogus = ToolRegistration(
        module="cloudra.tools.Chemtool.mechanism_predict",
        class_name="MechanismPredict",
        tool_name="bogus_gated_tool",
        config_gate="flower.no_such_field",
    )
    patched = tuple(TOOL_REGISTRY) + (bogus,)
    # capabilities 与 registry 各自持有 TOOL_REGISTRY 名字，需同步替换
    monkeypatch.setattr(registry_mod, "TOOL_REGISTRY", patched)
    monkeypatch.setattr(capabilities, "TOOL_REGISTRY", patched)
    assert "bogus_gated_tool" in config_disabled_tools()


# ----------------------------------------------------------------- tool_call 前置校验

@pytest.mark.asyncio
async def test_tool_call_refused_when_disabled(mock_session):
    tool = MechanismPredict()
    result = await tool.tool_call(
        MechanismPredict_input_schema(reactants="CC(=O)O"), mock_session
    )
    assert result.is_success is False
    assert "disabled" in result.message


@_REQUIRES_RDKIT
@pytest.mark.asyncio
async def test_tool_call_unconfigured_points_to_setup(monkeypatch, mock_session):
    _enable_flower(monkeypatch, configured=False)
    tool = MechanismPredict()
    result = await tool.tool_call(
        MechanismPredict_input_schema(reactants="CC(=O)O"), mock_session
    )
    assert result.is_success is False
    assert "setup_flower.sh" in result.message


@_REQUIRES_RDKIT
@pytest.mark.asyncio
async def test_tool_call_rejects_invalid_smiles(monkeypatch, tmp_path, mock_session):
    _enable_flower(monkeypatch, tmp_path)
    tool = MechanismPredict()
    result = await tool.tool_call(
        MechanismPredict_input_schema(reactants="not_a_smiles"), mock_session
    )
    assert result.is_success is False
    assert "Invalid reactant SMILES" in result.message


@_REQUIRES_RDKIT
@pytest.mark.asyncio
async def test_tool_call_rejects_malformed_reaction_string(monkeypatch, tmp_path, mock_session):
    _enable_flower(monkeypatch, tmp_path)
    tool = MechanismPredict()
    result = await tool.tool_call(
        MechanismPredict_input_schema(reactants="CC(=O)O>>CC(=O)Cl"), mock_session
    )
    assert result.is_success is False
    assert "plain dot-separated" in result.message


# ----------------------------------------------------------------- 路径枚举（纯函数）

def _network_fixture() -> dict:
    """root A 分两路：A->B->D(终点) 与 A->C->D；外加一条 B->B 自环类回访边不进栈。"""
    return {
        "reactant_input": "A",
        "root": "A",
        "sample_size": 10,
        "skipped_edges": 0,
        "nodes": ["A", "B", "C", "D"],
        "edges": [
            {"reactant": "A", "product": "B", "rank": 0, "count": 8, "probability": 0.8},
            {"reactant": "A", "product": "C", "rank": 1, "count": 2, "probability": 0.2},
            {"reactant": "B", "product": "D", "rank": 0, "count": 5, "probability": 0.5},
            {"reactant": "C", "product": "D", "rank": 0, "count": 5, "probability": 0.5},
            {"reactant": "D", "product": "B", "rank": 1, "count": 1, "probability": 0.1},
        ],
    }


def test_enumerate_pathways_orders_by_cumulative_probability():
    pathways = enumerate_pathways(_network_fixture())
    # A->B->D (cum 0.4)：D->B 的回访边因 B 已在路径上而终结；
    # A->C->D->B (cum 0.01)：该路径里 B 未访问过，D->B 边成立，随后 B->D 回访终结
    assert len(pathways) == 2
    assert pathways[0]["cumulative_probability"] == pytest.approx(0.4)
    assert pathways[1]["cumulative_probability"] == pytest.approx(0.01)
    assert [s["product"] for s in pathways[0]["steps"]] == ["B", "D"]
    assert [s["product"] for s in pathways[1]["steps"]] == ["C", "D", "B"]
    assert all(p["reaches_target"] is None for p in pathways)


def test_enumerate_pathways_empty_network_yields_nothing():
    network = {"root": "A", "nodes": ["A"], "edges": []}
    assert enumerate_pathways(network) == []


@_REQUIRES_RDKIT
def test_target_flags_exact_component_match():
    from cloudra.tools.Chemtool.mechanism_predict import (
        _attach_target_flags,
        _normalise_target_smiles,
    )

    pathways = [
        {
            "steps": [{"reactant": "A", "product": "CC(=O)O.Cl", "probability": 0.5}],
            "cumulative_probability": 0.5,
            "reaches_target": None,
        }
    ]
    _attach_target_flags(pathways, [_normalise_target_smiles("OC(=O)C")])
    assert pathways[0]["reaches_target"] is True

    pathways[0]["reaches_target"] = None
    _attach_target_flags(pathways, [_normalise_target_smiles("CC(=O)Cl")])
    assert pathways[0]["reaches_target"] is False


# ----------------------------------------------------------------- 真实冒烟（可选）

@_REQUIRES_FLOWER_ENV
@_REQUIRES_RDKIT
@pytest.mark.asyncio
async def test_smoke_real_flower_run(monkeypatch, tmp_path, mock_session):
    flower = get_config().flower
    monkeypatch.setattr(flower, "enabled", True)
    monkeypatch.setattr(flower, "repo_dir", _SMOKE_REPO)
    monkeypatch.setattr(flower, "env_python", _SMOKE_PYTHON)
    monkeypatch.setattr(flower, "checkpoint", _SMOKE_CHECKPOINT)
    tool = MechanismPredict()
    result = await tool.tool_call(
        MechanismPredict_input_schema(
            reactants="CC(=O)CC(=O)C(F)(F)F.NNc1cccc(Br)c1",
            beam_size=3,
            nbest=2,
            max_depth=6,
            sample_size=4,
            timeout_s=3600,
            output_dir=str(tmp_path),
        ),
        mock_session,
    )
    assert result.is_success, result.message
    assert result.num_steps > 0
    assert os.path.isfile(result.network_json)


def test_enumerate_pathways_best_first_keeps_highest_probability_prefix():
    """Best-first：explore_cap 打满时保留的是当前概率最高的前缀，而不是
    LIFO DFS 的任意子集（旧实现会先沿 edges 顺序里靠后的支路深入，最高概率
    路径可能根本没展开到，结果随 driver 输出顺序漂移）。"""
    network = {
        "root": "A",
        "edges": [
            # 高概率边写在前面：LIFO 会后弹它、先沿 C 支路消耗 cap
            {"reactant": "A", "product": "B", "rank": 0, "count": 6, "probability": 0.6},
            {"reactant": "A", "product": "C", "rank": 1, "count": 4, "probability": 0.4},
            {"reactant": "C", "product": "D", "rank": 0, "count": 9, "probability": 0.9},
            {"reactant": "D", "product": "E", "rank": 0, "count": 9, "probability": 0.9},
        ],
    }
    # cap=2：best-first 弹出 A(1.0) 与 B(0.6)——B 是终点，最高概率路径直接保留
    pathways = enumerate_pathways(network, explore_cap=2)
    assert len(pathways) == 1
    assert pathways[0]["cumulative_probability"] == pytest.approx(0.6)
    assert [s["product"] for s in pathways[0]["steps"]] == ["B"]


def test_enumerate_pathways_independent_of_edge_input_order():
    """同层子边按 (-概率, 产物) 排序入堆：枚举例序与 driver 的 edges 输出顺序无关。"""
    fixture = _network_fixture()
    reversed_edges = {**fixture, "edges": list(reversed(fixture["edges"]))}
    assert enumerate_pathways(fixture) == enumerate_pathways(reversed_edges)
