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
async def test_qm_input_writer_orca_single_point_key(tmp_path):
    """task_type=[{"single_point": None}] 被接受并归一化：ORCA 单点的 ! 行
    只留方法/基组（无任务关键字），回读意图为 single_point。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "water_sp.inp"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            method="b3lyp",
            basis_set="def2-svp",
            task_type=[{"single_point": None}],
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    content = out.read_text(encoding="utf-8")
    assert content.startswith("! b3lyp def2-svp")
    assert result.interpreted_intent["tasks"] == ["single_point"]


@pytest.mark.asyncio
async def test_qm_input_writer_gaussian_single_point_key(tmp_path):
    """同一 {'single_point': None} 键在 Gaussian 路由上映射为原生 sp 关键字。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "water_sp.gjf"

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="gaussian",
            source_type="xyz_file",
            source_value=str(xyz),
            method="b3lyp",
            basis_set="6-31g(d)",
            task_type=[{"single_point": None}],
            output_dir=str(out),
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    content = out.read_text(encoding="utf-8")
    assert "#p sp b3lyp/6-31g(d)" in content
    assert result.interpreted_intent["tasks"] == ["single_point"]


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
    method/basis_set 不进入输入（外部势没有基组概念）。
    ProgExt 可执行文件必须真实存在、可执行、且在 agent 可写范围之外。"""
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    out = tmp_path / "ts_opt.inp"
    fake_mace = tmp_path / "sysbin" / "mace"
    fake_mace.parent.mkdir()
    fake_mace.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_mace.chmod(0o755)

    # TS 初始 Hessian 控制走原生 orca_blocks；Gaussian 子选项 calcfc/noeigen
    # 对 ORCA 是配置错误（见 test_orca_rejects_gaussian_opt_suboptions）。
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program=str(fake_mace),
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
    assert f'ProgExt "{fake_mace}"' in content
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
async def test_qm_input_writer_relative_paths_use_agent_workspace(tmp_path, monkeypatch):
    """相对 output_dir/source_value 解析到绑定 agent 的 working_directory，
    绝不落到进程 cwd（C1 沙箱路径缺陷的直接单测）。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "water.xyz").write_text(_WATER_XYZ, encoding="utf-8")
    server_cwd = tmp_path / "cwd"
    server_cwd.mkdir()
    monkeypatch.chdir(server_cwd)

    class _Bridge:
        working_directory = str(workspace)

    tool = QmInputWriter()
    tool.subagent = _Bridge()

    result = await tool.tool_call(
        QmInputWriter_input_schema(
            source_type="xyz_file",
            source_value="water.xyz",
            output_dir="calc/water.gjf",
        ),
        session=None,
    )

    assert result.is_success is True, result.message
    written = workspace / "calc" / "water.gjf"
    assert written.is_file()
    assert result.input_path == str(written.resolve())
    assert not (server_cwd / "calc" / "water.gjf").exists()


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


# ---------------------------------------------------------------------------
# issue #33：SMILES 源不得写出含互穿片段坐标的输入文件
# 复现材料见 tests/fixtures/chemtool_issue33/（实测 F–C 0.1392 Å）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smiles_source_multifragment_writes_an_assembled_complex(tmp_path):
    """多碎片 SMILES 源：写入的必须是**已组装**的复合物坐标，不得是互穿几何。

    旧行为是把逐碎片独立嵌入的坐标（实测 F–C 0.1392 Å）逐字写进 .gjf；现在经已批准的
    组装方案（刚性放置 + 碰撞剔除 + 力场弛豫）产出候选后，再从中取坐标写文件。
    """
    import json as _json

    import numpy as np

    gjf = tmp_path / "complex.gjf"
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="gaussian",
            source_type="smiles",
            source_value="[F-].CCl",
            charge=-1,
            task_type=[{"opt": None}],
            output_dir=str(gjf),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    assert gjf.exists()
    text = gjf.read_text(encoding="utf-8")
    # 碎片划分取自构建器记录的稳定身份表（逐组分加氢，顺序不能靠重新推导）
    prepared = _json.loads(
        (tmp_path / "structure_build" / "complex" / "prepared_structure.json").read_text(
            encoding="utf-8"
        )
    )
    frag_of = {
        index: int(identity["component_id"].removeprefix("frag"))
        for index, identity in enumerate(prepared["atom_identities"])
    }
    assert len(set(frag_of.values())) == 2

    # 从 .gjf 里解析坐标块（charge/multiplicity 行之后的原子行）
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "-1 1") + 1
    coords = []
    for ln in lines[start:]:
        parts = ln.split()
        if len(parts) != 4:
            break
        coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    assert len(coords) == 6
    pos = np.asarray(coords, dtype=float)
    worst = min(
        float(np.linalg.norm(pos[i] - pos[j]))
        for i in range(len(pos)) for j in range(i + 1, len(pos))
        if frag_of[i] != frag_of[j]
    )
    assert worst >= 1.0, f"写出的输入仍含亚 1 Å 碎片间接触：{worst:.3f} Å"
    assert (tmp_path / "structure_build" / "complex" / "assembly" / "assembly.json").is_file()


@pytest.mark.asyncio
async def test_smiles_source_single_molecule_uses_shared_builder(tmp_path):
    """单分子 SMILES 源经共享构建器产出坐标，并留下轨迹现场。"""
    gjf = tmp_path / "acetic.gjf"
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="gaussian",
            source_type="smiles",
            source_value="CC(=O)O",
            task_type=[{"opt": None}],
            output_dir=str(gjf),
        ),
        session=None,
    )
    assert result.is_success is True, result.message
    text = gjf.read_text(encoding="utf-8")
    assert "expected_smiles: CC(=O)O" in text
    assert (tmp_path / "structure_build" / "acetic" / "trajectories.json").is_file()


@pytest.mark.asyncio
async def test_smiles_source_charge_mismatch_is_refused(tmp_path):
    """SMILES 形式电荷与 charge 不符时必须拒绝，不得按错误电子态写文件。"""
    gjf = tmp_path / "wrong.gjf"
    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="gaussian",
            source_type="smiles",
            source_value="[F-].CCl",
            charge=0,
            task_type=[{"opt": None}],
            output_dir=str(gjf),
        ),
        session=None,
    )
    assert result.is_success is False
    assert not gjf.exists()
    assert "charge_mismatch" in result.message


# ---------------------------------------------------------------------------
# external_program 安全闸门：ORCA ProgExt 必须在 agent 可写范围之外的可执行
# 文件；Gaussian 引擎值必须能被 method_policy 词法解析
# ---------------------------------------------------------------------------


class _WsBridge:
    def __init__(self, root):
        self.working_directory = str(root)


def _xyz(tmp_path):
    xyz = tmp_path / "water.xyz"
    xyz.write_text(_WATER_XYZ, encoding="utf-8")
    return xyz


@pytest.mark.asyncio
async def test_orca_external_program_inside_workdir_refused(tmp_path):
    """工作目录里的同名可执行文件（假 mace）不得作为 ProgExt 通过——
    method_policy 只比 basename，区内文件会被 agent 偷换成任意脚本。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    xyz = _xyz(workspace)
    fake_mace = workspace / "mace"
    fake_mace.write_text("#!/bin/sh\nrm -rf ~\n", encoding="utf-8")
    fake_mace.chmod(0o755)

    tool = QmInputWriter()
    tool.subagent = _WsBridge(workspace)
    result = await tool.tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program=str(fake_mace),
            task_type=[{"opt": None}],
            output_dir=str(workspace / "job.inp"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "agent-writable" in result.message
    assert not (workspace / "job.inp").exists()


@pytest.mark.asyncio
async def test_orca_external_program_inside_data_dir_refused(tmp_path):
    from cloudra.infra.config import get_config

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    xyz = _xyz(tmp_path)
    fake_mace = data_dir / "mace"
    fake_mace.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_mace.chmod(0o755)
    assert str(fake_mace).startswith(str(get_config().data_dir))  # conftest 隔离确认

    result = await QmInputWriter().tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program=str(fake_mace),
            task_type=[{"opt": None}],
            output_dir=str(tmp_path / "job.inp"),
        ),
        session=None,
    )
    assert result.is_success is False
    assert "agent-writable" in result.message


@pytest.mark.asyncio
async def test_orca_external_program_missing_or_not_executable_refused(tmp_path):
    xyz = _xyz(tmp_path)
    tool = QmInputWriter()

    missing = await tool.tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program=str(tmp_path / "no_such_mace"),
            task_type=[{"opt": None}],
            output_dir=str(tmp_path / "a.inp"),
        ),
        session=None,
    )
    assert missing.is_success is False
    assert "existing regular file" in missing.message

    not_exec = tmp_path / "mace"
    not_exec.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # 无执行位
    not_exec.chmod(0o644)
    denied = await tool.tool_call(
        QmInputWriter_input_schema(
            engine="orca",
            source_type="xyz_file",
            source_value=str(xyz),
            external_program=str(not_exec),
            task_type=[{"opt": None}],
            output_dir=str(tmp_path / "b.inp"),
        ),
        session=None,
    )
    assert denied.is_success is False
    assert "not executable" in denied.message


@pytest.mark.asyncio
async def test_gaussian_external_malformed_values_refused(tmp_path):
    """Gaussian external= 引擎值必须是单个 [a-z0-9_.-] token：带空格参数或
    引号/壳字符的写法会让策略层解析不出同一个值，一律拒绝。"""
    xyz = _xyz(tmp_path)
    tool = QmInputWriter()
    for bad in ("mace --model x.model", 'mace" opt=(read)', "mace;rm -rf /"):
        result = await tool.tool_call(
            QmInputWriter_input_schema(
                engine="gaussian",
                source_type="xyz_file",
                source_value=str(xyz),
                external_program=bad,
                task_type=[{"opt": None}],
                output_dir=str(tmp_path / "bad.gjf"),
            ),
            session=None,
        )
        assert result.is_success is False, bad
        assert "external engine value" in result.message or "refused" in result.message, bad
        assert not (tmp_path / "bad.gjf").exists()
