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
            task_type=[{"opt": "ts"}, {"freq": None}],
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


@pytest.mark.asyncio
async def test_qm_input_writer_orca_extopt_external_mlip(tmp_path):
    """外部 MLIP 路由（GH #16）：! ExtOpt + %method ProgExt/Ext_Params 块；
    method/basis_set 不进入输入（外部势没有基组概念）。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "ts_opt.inp"

    # TS 初始 Hessian 控制走原生 orca_blocks；Gaussian 子选项 calcfc/noeigen
    # 对 ORCA 是配置错误（见 test_orca_rejects_gaussian_opt_suboptions）。
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program="/opt/conda/envs/chemai/bin/mace",
            external_params="--model /opt/MACE-omol-0.model --device cpu --dtype float64",
            task_type=[{"opt": "ts"}, {"freq": None}],
            nproc=1,
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    content = out.read_text(encoding="utf-8")
    assert content.startswith("! ExtOpt OptTS Freq")
    assert 'ProgExt "/opt/conda/envs/chemai/bin/mace"' in content
    assert 'Ext_Params "--model /opt/MACE-omol-0.model --device cpu --dtype float64"' in content
    assert "b3lyp" not in content and "6-31g" not in content
    assert "\n* xyz 0 1\n" in content


@pytest.mark.asyncio
async def test_qm_input_writer_gaussian_external_route(tmp_path):
    """Gaussian 外部 MLIP 路由：external="..." 进 route 卡，method/basis 不进入。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "water_opt.gjf"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="gaussian",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program="mace",
            task_type=[{"opt": None}],
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    content = out.read_text(encoding="utf-8")
    route = next(line for line in content.splitlines() if line.startswith("#"))
    assert 'external="mace"' in route
    assert "b3lyp" not in route and "6-31g" not in route


@pytest.mark.asyncio
async def test_qm_input_writer_external_params_requires_external_program(tmp_path):
    """external_params 单独出现（无 external_program）是配置错误，fail-loud。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_params="--model /opt/x.model",
            task_type=[{"opt": None}],
            output_dir=str(tmp_path / "bad.inp"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "external_program" in result.message
