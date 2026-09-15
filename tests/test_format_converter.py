"""format_converter 工具测试。

覆盖审计发现：
- F1：mol/sdf 读写必须走 RDKit 保留键/形式电荷/立体（ASE 中转丢光键与电荷）；
      xyz→sdf→xyz 坐标保持回归。
- F4：多帧/多分子输入不再静默丢帧——取第一帧并在 message 显式披露。
- F5：mol/sdf 输入带电荷时转 gjf/inp 等在 message 显式警告电荷不落坐标格式。
"""

import os

import pytest

pytest.importorskip("rdkit")
pytest.importorskip("ase")

from rdkit import Chem  # noqa: E402

from cloudra.tools.Chemtool.format_converter import FormatConverter, FormatConverter_input_schema  # noqa: E402

# 带电烯醇盐 CC([O-])CC=O：13 原子（含 H 后）多键 + 形式电荷 -1
ENOLATE_SMILES = "CC([O-])CC=O"


def _enolate_molfile() -> str:
    mol = Chem.MolFromSmiles(ENOLATE_SMILES)
    return Chem.MolToMolBlock(mol, kekulize=True)


async def _convert(tmp_path, input_fmt, output_fmt, source_text, name="in", out_name="out"):
    in_path = tmp_path / f"{name}.{input_fmt}"
    in_path.write_text(source_text, encoding="utf-8")
    out_path = tmp_path / f"{out_name}.{output_fmt}"
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(in_path), input_format=input_fmt,
            output_format=output_fmt, output_path=str(out_path),
        ),
        session=None,
    )
    return result, out_path


# ---------------------------------------------------------------------------
# F1：化学信息保留
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mol_to_sdf_keeps_bonds_charge_and_stereo(tmp_path):
    """F1：带电烯醇盐 mol→sdf 必须保留键数/形式电荷（ASE 中转会丢成 0 键 0 电荷）。"""
    result, sdf_path = await _convert(tmp_path, "mol", "sdf", _enolate_molfile())
    assert result.is_success, result.message

    reader = Chem.SDMolSupplier(str(sdf_path), removeHs=False, sanitize=True)
    mols = [m for m in reader if m is not None]
    assert len(mols) == 1

    original = Chem.MolFromSmiles(ENOLATE_SMILES)
    got = mols[0]
    assert got.GetNumBonds() == original.GetNumBonds()
    total_charge = sum(a.GetFormalCharge() for a in got.GetAtoms())
    assert total_charge == -1
    # 化学身份：canonical SMILES 一致
    assert Chem.MolToSmiles(got) == Chem.MolToSmiles(original)


@pytest.mark.asyncio
async def test_sdf_to_mol_roundtrip_keeps_chemistry(tmp_path):
    """F1：sdf→mol 同样保留键/电荷（先 mol→sdf 造中间，再 sdf→mol）。"""
    result1, sdf_path = await _convert(tmp_path, "mol", "sdf", _enolate_molfile())
    assert result1.is_success, result1.message

    result2, mol_path = await _convert(tmp_path, "sdf", "mol", sdf_path.read_text(encoding="utf-8"),
                                       name="mid", out_name="back")
    assert result2.is_success, result2.message

    got = Chem.MolFromMolFile(str(mol_path), removeHs=False)
    assert got is not None
    original = Chem.MolFromSmiles(ENOLATE_SMILES)
    assert got.GetNumBonds() == original.GetNumBonds()
    assert sum(a.GetFormalCharge() for a in got.GetAtoms()) == -1
    assert Chem.MolToSmiles(got) == Chem.MolToSmiles(original)


_WATER_XYZ = """3
water
O   0.000000   0.000000   0.000000
H   0.957000   0.000000   0.000000
H  -0.239000   0.927000   0.000000
"""


@pytest.mark.asyncio
async def test_xyz_to_sdf_to_xyz_preserves_coordinates(tmp_path):
    """F1 回归：纯坐标格式链 xyz→sdf→xyz 坐标保持不变（sdf 侧为原子+坐标）。"""
    result1, sdf_path = await _convert(tmp_path, "xyz", "sdf", _WATER_XYZ)
    assert result1.is_success, result1.message

    result2, xyz_path = await _convert(tmp_path, "sdf", "xyz", sdf_path.read_text(encoding="utf-8"),
                                       name="mid", out_name="back")
    assert result2.is_success, result2.message

    import ase.io

    back = ase.io.read(str(xyz_path), format="xyz")
    import numpy as np

    positions = back.get_positions()
    expected = np.array([
        [0.0, 0.0, 0.0],
        [0.957, 0.0, 0.0],
        [-0.239, 0.927, 0.0],
    ])
    assert positions == pytest.approx(expected, abs=1e-3)


# ---------------------------------------------------------------------------
# F4：多帧/多分子披露
# ---------------------------------------------------------------------------

_MULTIFRAME_XYZ = """3
frame1
C   0.0   0.0   0.0
H   1.0   0.0   0.0
H   0.0   1.0   0.0
3
frame2
C   5.0   5.0   5.0
H   6.0   5.0   5.0
H   5.0   6.0   5.0
"""


@pytest.mark.asyncio
async def test_multiframe_xyz_reports_first_frame_in_message(tmp_path):
    """F4：xyz 输入含多帧时，message 显式声明帧数与"取第一帧"（不静默丢帧）。"""
    result, out_path = await _convert(tmp_path, "xyz", "sdf", _MULTIFRAME_XYZ)
    assert result.is_success, result.message
    assert "2 coordinate frames" in result.message
    assert "first" in result.message

    # 落盘确实是第一帧的坐标
    reader = Chem.SDMolSupplier(str(out_path), removeHs=False, sanitize=True)
    mols = [m for m in reader if m is not None]
    assert mols
    conf = mols[0].GetConformer()
    first_c = conf.GetAtomPosition(0)
    assert abs(first_c.x) < 1e-6 and abs(first_c.y) < 1e-6  # frame1 C at origin


@pytest.mark.asyncio
async def test_multimolecule_sdf_reports_first_in_message(tmp_path):
    """F4：SDF 含多个分子时同样只转第一个并披露。"""
    import io

    m1 = Chem.MolFromSmiles("CCO")
    m2 = Chem.MolFromSmiles("C#N")
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    for m in (m1, m2):
        writer.write(m)
    writer.close()
    sdf_text = buf.getvalue()
    assert sdf_text.count("$$$$") >= 2

    result, out_path = await _convert(tmp_path, "sdf", "xyz", sdf_text)
    assert result.is_success, result.message
    assert "2 frames/molecules" in result.message
    assert "first" in result.message


# ---------------------------------------------------------------------------
# F5：带电输入 → 坐标输出格式的警告
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_charged_input_to_gjf_warns_charge_not_written(tmp_path):
    """F5：带电烯醇盐 mol→gjf 成功，但 message 必须警告电荷不落坐标格式。"""
    result, out_path = await _convert(tmp_path, "mol", "gjf", _enolate_molfile())
    assert result.is_success, result.message
    assert "charge" in result.message.lower()
    assert "coordinate" in result.message.lower() or "coordinates" in result.message.lower()


@pytest.mark.asyncio
async def test_neutral_mol_to_gjf_no_charge_warning(tmp_path):
    """中性分子转 gjf 不出现电荷警告。"""
    mol = Chem.MolFromSmiles("CCO")
    result, _ = await _convert(tmp_path, "mol", "gjf", Chem.MolToMolBlock(mol, kekulize=True))
    assert result.is_success, result.message
    assert "charge" not in result.message.lower()


@pytest.mark.asyncio
async def test_xyz_to_poscar_conversion(tmp_path):
    """验证 xyz 转换到 poscar / vasp 格式。"""
    result, poscar_path = await _convert(tmp_path, "xyz", "poscar", _WATER_XYZ)
    assert result.is_success, result.message
    assert poscar_path.is_file()
    content = poscar_path.read_text(encoding="utf-8")
    assert len(content.splitlines()) >= 5


def test_tool_metadata():
    tool = FormatConverter()
    assert tool.tool_name == "format_converter"
    assert tool.is_write() is True


# ---------------------------------------------------------------------------
# 日志帧解析的裸 IndexError 收口（生产实锤：截断日志炸 "list index out of range"）
# ---------------------------------------------------------------------------


async def _convert_log(tmp_path, monkeypatch=None, extract_frames_result=None):
    """log→csv 转换；extract_frames_result 非 None 时 monkeypatch 帧提取。"""
    log = tmp_path / "job.log"
    log.write_text("not a real computation log\n", encoding="utf-8")
    if monkeypatch is not None:
        from cloudra.tools.core import gaussian_frames

        def _stub(text, **_kwargs):
            if isinstance(extract_frames_result, Exception):
                raise extract_frames_result
            return extract_frames_result

        monkeypatch.setattr(gaussian_frames, "extract_frames_from_text", _stub)
    return await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(log), input_format="log",
            output_format="csv", output_path=str(tmp_path / "out.csv"),
        ),
        session=None,
    )


@pytest.mark.asyncio
async def test_log_parser_index_error_returns_clean_failure(tmp_path, monkeypatch):
    """帧解析链路裸抛 IndexError（截断/畸形日志的空列表索引）时，必须翻成
    有指引的 is_success=False，不把 "list index out of range" 漏给调用方。"""
    result = await _convert_log(
        tmp_path, monkeypatch, extract_frames_result=IndexError("list index out of range"),
    )
    assert result.is_success is False
    assert "list index out of range" not in result.message
    assert "truncated" in result.message or "not a valid" in result.message


@pytest.mark.asyncio
async def test_log_with_no_parseable_frames_fails_cleanly(tmp_path, monkeypatch):
    """空帧（日志里没有任何可提取的关键帧）：干净的 is_success=False + 原因说明。"""
    result = await _convert_log(tmp_path, monkeypatch, extract_frames_result=[])
    assert result.is_success is False
    assert "No key frames" in result.message
    assert "list index out of range" not in result.message


# ---------------------------------------------------------------------------
# T6：log 路径单读一次文本下传——path 版 detect_job_types/extract_frames 不再被调用
# ---------------------------------------------------------------------------

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.mark.asyncio
async def test_gaussian_log_conversion_uses_single_text_read(tmp_path, monkeypatch):
    """boom 掉 gaussian_frames 的 path 版入口后转换仍成功：证明 _convert_log
    只读一次日志文本并下传 *_from_text 原语，不再各自整读大日志。"""
    from cloudra.tools.core import gaussian_frames

    def _boom(log_path, **_kwargs):
        raise AssertionError(f"path-based re-read must not happen: {log_path}")

    monkeypatch.setattr(gaussian_frames, "detect_job_types", _boom)
    monkeypatch.setattr(gaussian_frames, "extract_frames", _boom)

    log = tmp_path / "job.log"
    log.write_text(
        open(os.path.join(_FIXTURES, "gaussian", "water_opt_freq_g16.out"), encoding="utf-8").read(),
        encoding="utf-8",
    )
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(log), input_format="log",
            output_format="csv", output_path=str(tmp_path / "out.csv"),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert (tmp_path / "out.csv").is_file()


@pytest.mark.asyncio
async def test_orca_log_conversion_uses_single_text_read(tmp_path, monkeypatch):
    """ORCA 同样：path 版 detect/extract/reason 全部 boom 后转换仍成功。"""
    from cloudra.tools.core import orca_frames

    def _boom(log_path, **_kwargs):
        raise AssertionError(f"path-based re-read must not happen: {log_path}")

    monkeypatch.setattr(orca_frames, "detect_job_types", _boom)
    monkeypatch.setattr(orca_frames, "extract_frames", _boom)
    monkeypatch.setattr(orca_frames, "frames_unavailable_reason", _boom)

    log = tmp_path / "job.log"
    log.write_text(
        open(os.path.join(_FIXTURES, "orca", "dvb_opt_orca42.out"), encoding="utf-8").read(),
        encoding="utf-8",
    )
    result = await FormatConverter().tool_call(
        FormatConverter_input_schema(
            input_path=str(log), input_format="log",
            output_format="csv", output_path=str(tmp_path / "out.csv"),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert (tmp_path / "out.csv").is_file()
