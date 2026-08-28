"""qm_input_writer: generate valid Gaussian input files."""

import pytest

pytest.importorskip("rdkit", reason="qm_input_writer requires RDKit (chem extra)")

from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

_WATER_XYZ = (
    "3\nwater\n"
    "O  0.000000  0.000000  0.117300\n"
    "H  0.000000  0.757200 -0.469200\n"
    "H  0.000000 -0.757200 -0.469200\n"
)


@pytest.mark.asyncio
async def test_qm_input_writer_from_xyz_file_produces_valid_gjf(tmp_path):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "jobs" / "water_opt.gjf"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            source_type="xyz_file",
            source_value=str(xyz),
            method="b3lyp",
            basis_set="6-31g(d)",
            task_type=[{"opt": None}, {"freq": None}],
            charge=0,
            multiplicity=1,
            mem="8GB",
            nproc=8,
            chk_name="water.chk",
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    assert result.input_path == str(out)
    content = out.read_text(encoding="utf-8")
    assert "%chk=water.chk" in content
    assert "%nproc=8" in content
    assert "%mem=8GB" in content
    assert "#p opt freq b3lyp/6-31g(d)" in content
    assert "\n0 1\n" in content
    assert "O" in content and "H" in content
    # Gaussian 输入以坐标块后的空行结束
    assert content.endswith("\n\n")


@pytest.mark.asyncio
async def test_qm_input_writer_missing_source_file_fails(tmp_path):
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            source_type="xyz_file",
            source_value=str(tmp_path / "nope.xyz"),
            output_dir=str(tmp_path / "x.gjf"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "not found" in result.message


@pytest.mark.asyncio
async def test_qm_input_writer_invalid_smiles_fails(tmp_path):
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            source_type="smiles",
            source_value="not_a_smiles((",
            output_dir=str(tmp_path / "x.gjf"),
        ),
        session=None,
    )
    assert result.is_success is False


@pytest.mark.asyncio
async def test_qm_input_writer_orca_engine_produces_valid_inp(tmp_path):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "jobs" / "water_ts.inp"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            method="wB97X-V",
            basis_set="def2-TZVP",
            task_type=[{"opt": "ts,calcfc,noeigen"}, {"freq": None}],
            charge=-1,
            multiplicity=1,
            mem="8GB",
            nproc=8,
            extra_keywords="D3BJ",
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    assert result.input_path == str(out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("! OptTS Freq wB97X-V def2-TZVP D3BJ")
    assert "%pal nprocs 8 end" in content
    assert "%maxcore 1024" in content
    assert "\n* xyz -1 1\n" in content
    assert "O" in content and "H" in content
    assert content.rstrip().endswith("*")


@pytest.mark.asyncio
async def test_qm_input_writer_orca_plain_opt_maps_keywords(tmp_path):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "water_opt.inp"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            method="b3lyp",
            basis_set="def2-svp",
            task_type=[{"opt": None}],
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    content = out.read_text(encoding="utf-8")
    assert content.startswith("! Opt b3lyp def2-svp")
    assert "\n* xyz 0 1\n" in content
