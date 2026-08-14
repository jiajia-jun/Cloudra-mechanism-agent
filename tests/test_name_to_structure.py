import os

import pytest

import cloudra.tools.Chemtool.name_to_structure as mod
from cloudra.tools.Chemtool.name_to_structure import NameToStructure, NameToStructure_input_schema

ASPIRIN = {
    "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "iupac_name": "2-acetoxybenzoic acid",
    "molecular_formula": "C9H8O4",
    "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    "cid": "2244",
}


@pytest.fixture
def tool():
    return NameToStructure()


def _patch_resolvers(monkeypatch, pubchem=None, cir=None, opsin=None):
    """把三个网络解析函数替换为返回固定值/抛错的假实现（测试不触网）。"""
    async def fake_pubchem(name):
        return pubchem
    async def fake_cir(name):
        return cir
    async def fake_opsin(name):
        return opsin
    monkeypatch.setattr(mod, "_resolve_pubchem", fake_pubchem)
    monkeypatch.setattr(mod, "_resolve_cir", fake_cir)
    monkeypatch.setattr(mod, "_resolve_opsin", fake_opsin)


@pytest.mark.asyncio
async def test_pubchem_hit(tool, mock_session, monkeypatch):
    """PubChem 直接命中：返回完整属性，resolver_used=pubchem。"""
    _patch_resolvers(monkeypatch, pubchem=dict(ASPIRIN))
    result = await tool.safe_call(
        NameToStructure_input_schema(name="aspirin"), mock_session,
    )
    assert result.is_success is True
    assert result.smiles == ASPIRIN["smiles"]
    assert result.resolver_used == "pubchem"
    assert result.cid == "2244"
    assert result.molecular_formula == "C9H8O4"
    assert "Verify" in result.message  # 必带人工核对提示


@pytest.mark.asyncio
async def test_fallback_to_cir(tool, mock_session, monkeypatch):
    """PubChem 未命中时回退 CIR。"""
    _patch_resolvers(monkeypatch, pubchem=None, cir={"smiles": "CCO", "iupac_name": "ethanol"})
    result = await tool.safe_call(
        NameToStructure_input_schema(name="ethanol"), mock_session,
    )
    assert result.is_success is True
    assert result.smiles == "CCO"
    assert result.resolver_used == "cir"


@pytest.mark.asyncio
async def test_resolver_opsin_only(tool, mock_session, monkeypatch):
    """指定 resolver=opsin 时不尝试其他服务。"""
    called = []

    async def fake_pubchem(name):
        called.append("pubchem")
        return dict(ASPIRIN)

    async def fake_opsin(name):
        called.append("opsin")
        return {"smiles": "CC(=O)O"}

    monkeypatch.setattr(mod, "_resolve_pubchem", fake_pubchem)
    monkeypatch.setattr(mod, "_resolve_cir", fake_pubchem)
    monkeypatch.setattr(mod, "_resolve_opsin", fake_opsin)

    result = await tool.safe_call(
        NameToStructure_input_schema(name="acetic acid", resolver="opsin"), mock_session,
    )
    assert result.is_success is True
    assert result.resolver_used == "opsin"
    assert called == ["opsin"]


@pytest.mark.asyncio
async def test_all_resolvers_miss(tool, mock_session, monkeypatch):
    """全部未命中：is_success=False 且给出改名建议。"""
    _patch_resolvers(monkeypatch)
    result = await tool.safe_call(
        NameToStructure_input_schema(name="一个不存在的化合物名xyz"), mock_session,
    )
    assert result.is_success is False
    assert "no hit" in result.message
    assert "IUPAC" in result.message or "CAS" in result.message


@pytest.mark.asyncio
async def test_resolver_exception_continues(tool, mock_session, monkeypatch):
    """某个服务抛网络异常时继续回退而不是失败。"""
    async def boom(name):
        raise ConnectionError("network down")

    async def fake_cir(name):
        return {"smiles": "C"}

    monkeypatch.setattr(mod, "_resolve_pubchem", boom)
    monkeypatch.setattr(mod, "_resolve_cir", fake_cir)
    monkeypatch.setattr(mod, "_resolve_opsin", boom)

    result = await tool.safe_call(
        NameToStructure_input_schema(name="methane"), mock_session,
    )
    assert result.is_success is True
    assert result.resolver_used == "cir"


@pytest.mark.asyncio
async def test_generate_3d_writes_xyz(tool, mock_session, monkeypatch, tmp_path):
    """generate_3d=True：写出 xyz 文件且原子数正确（乙醇 9 原子）。"""
    pytest.importorskip("rdkit", reason="未安装 chem 额外依赖（rdkit）")
    _patch_resolvers(monkeypatch, pubchem={"smiles": "CCO"})
    out = str(tmp_path / "ethanol.xyz")
    result = await tool.safe_call(
        NameToStructure_input_schema(name="ethanol", generate_3d=True, output_path=out),
        mock_session,
    )
    assert result.is_success is True
    assert result.xyz_path == out and os.path.isfile(out)
    lines = open(out).read().splitlines()
    assert int(lines[0]) == 9  # CCO 加氢后 9 原子
    assert len(lines) == 11


def test_tool_metadata():
    tool = NameToStructure()
    assert tool.tool_id == "t-46"
    assert tool.tool_name == "name_to_structure"
    assert tool.is_write() is True
