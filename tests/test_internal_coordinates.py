import os

import pytest

pytest.importorskip("rdkit", reason="未安装 chem 额外依赖（rdkit）")
pytest.importorskip("chemcoord", reason="未安装 chem 额外依赖（chemcoord）")
pytest.importorskip("ase", reason="未安装 chem 额外依赖（ase）")

from cloudra.tools.Chemtool.internal_coordinates import (
    InternalCoordinates,
    InternalCoordinates_input_schema,
)

WATER_XYZ = """3
water
O   0.000000   0.000000   0.000000
H   0.957000   0.000000   0.000000
H  -0.239000   0.927000   0.000000
"""

# MMFF 优化的丁烷（中心 C2-C3 扭转角约 -65°，gauche）
BUTANE_XYZ = """14
butane
C     -1.575217    0.469467    0.027091
C     -0.556942   -0.314570   -0.786290
C      0.648571   -0.778287    0.031876
C      1.505112    0.366682    0.550114
H     -1.162517    1.420101    0.377286
H     -1.909718   -0.104792    0.896806
H     -2.452692    0.695521   -0.587298
H     -0.220952    0.294308   -1.633701
H     -1.052250   -1.197697   -1.207185
H      0.313063   -1.392923    0.875311
H      1.271845   -1.421416   -0.600824
H      2.396656   -0.027206    1.048649
H      0.961547    0.976856    1.277361
H      1.833495    1.013955   -0.269196
"""

# 假过渡态：甲醇 C-O 拉长到 1.75 Å（ref 1.43 → elongated），
# 额外 H7 在 1.70 Å 处接近 O5（> O-H ref 0.96，< 0.75×vdW 2.04 → forming_candidate）
FAKE_TS_XYZ = """7
fake ts
C   0.000000   0.000000   0.000000
H  -0.363000   1.028000   0.000000
H  -0.363000  -0.514000   0.890000
H  -0.363000  -0.514000  -0.890000
O   1.750000   0.000000   0.000000
H   2.070000   0.905000   0.000000
H   3.450000   0.000000   0.000000
"""

# 椅式环己烷（Cremer–Pople θ ≈ 0）
CYCLOHEXANE_XYZ = """18
cyclohexane chair
C      1.413555   -0.201151   -0.371713
C      0.550931   -1.364158    0.110984
C     -0.927102   -1.131737   -0.190850
C     -1.413555    0.201151    0.371714
C     -0.550931    1.364158   -0.110985
C      0.927102    1.131737    0.190850
H      2.455758   -0.367658   -0.076984
H      1.393360   -0.163032   -1.467863
H      0.685996   -1.493806    1.191889
H      0.883316   -2.292926   -0.366181
H     -1.084165   -1.148032   -1.276424
H     -1.522700   -1.949393    0.230431
H     -1.393354    0.163033    1.467864
H     -2.455758    0.367658    0.076988
H     -0.685998    1.493804   -1.191889
H     -0.883317    2.292927    0.366177
H      1.084166    1.148033    1.276425
H      1.522699    1.949393   -0.230431
"""

# 水二聚体：O1-H2···O4 氢键（H2···O4 = 1.893 Å → forming_candidate）
WATER_DIMER_XYZ = """6
water dimer
O   0.000000   0.000000   0.000000
H   0.957000   0.000000   0.000000
H  -0.239000   0.927000   0.000000
O   2.850000   0.000000   0.000000
H   3.807000   0.000000   0.000000
H   2.611000   0.927000   0.000000
"""


def _parse_xyz_positions(xyz_text: str):
    """返回 [(symbol, (x, y, z)), ...]"""
    lines = [ln for ln in xyz_text.splitlines() if ln.strip()]
    out = []
    for ln in lines[2:]:
        tok = ln.split()
        out.append((tok[0], tuple(float(v) for v in tok[1:4])))
    return out


@pytest.mark.asyncio
async def test_analyze_water_report_sections(mock_session, tmp_path):
    """水分子：报告含全部分节，zmat 文件生成，默认路径规则正确。"""
    xyz_file = tmp_path / "water.xyz"
    xyz_file.write_text(WATER_XYZ)

    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="analyze", input_path=str(xyz_file)),
        mock_session,
    )
    assert result.is_success is True
    for section in ("== Summary ==", "== Stereochemistry ==", "== Rings ==",
                    "== Rotatable Dihedrals ==", "== Abnormal Bonds ==",
                    "== Abnormal Angles ==", "== Equivalent Atoms ==", "== Notes =="):
        assert section in result.report
    assert "H2O" in result.report
    # 默认 zmat 路径：input_path 同目录 <stem>.zmat
    assert result.zmat_path == str(tmp_path / "water.zmat")
    assert os.path.isfile(result.zmat_path)
    assert result.zmat_lines > 0
    # 正常结构不应有键异常
    assert all(a["status"] not in ("elongated", "compressed", "breaking_suspect")
               for a in result.anomalies)


@pytest.mark.asyncio
async def test_analyze_butane_rotatable_and_equivalence(mock_session, tmp_path):
    """丁烷：可旋转二面角分类（gauche/synclinal），等价原子组，反应分节存在。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=BUTANE_XYZ,
            zmat_path=str(tmp_path / "butane.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "== Rotatable Dihedrals ==" in result.report
    assert "gauche/synclinal" in result.report
    # 等价原子：两个端甲基碳、两个亚甲基碳各自等价
    assert "== Equivalent Atoms ==" in result.report
    eq_section = result.report.split("== Equivalent Atoms ==")[1].split("==")[0]
    assert "C1" in eq_section and "C4" in eq_section


@pytest.mark.asyncio
async def test_analyze_fake_ts_anomalies(mock_session, tmp_path):
    """假 TS：拉长 C-O 判为 elongated，接近的 H···O 判为 forming_candidate，反应中心块生效。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=FAKE_TS_XYZ,
            reactive_atoms=[5], watch_pairs=[[5, 7]],
            zmat_path=str(tmp_path / "ts.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True

    statuses = {(tuple(sorted(a["atoms"])), a["status"]) for a in result.anomalies}
    assert any(a["status"] == "elongated" and set(a["atoms"]) == {"C1", "O5"}
               for a in result.anomalies), statuses
    assert any(a["status"] == "forming_candidate" and set(a["atoms"]) == {"O5", "H7"}
               for a in result.anomalies), statuses

    assert "== Reactive Center ==" in result.report
    assert "O5" in result.report.split("== Reactive Center ==")[1]
    assert "forming" in result.report


@pytest.mark.asyncio
async def test_analyze_cyclohexane_ring(mock_session, tmp_path):
    """椅式环己烷：检测到 6 元环并给出 Cremer–Pople 椅式提示。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=CYCLOHEXANE_XYZ,
            zmat_path=str(tmp_path / "cyclohexane.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "== Rings ==" in result.report
    rings_section = result.report.split("== Rings ==")[1].split("==")[0]
    assert "6-membered ring" in rings_section
    assert "CP:" in rings_section
    assert "chair" in rings_section


@pytest.mark.asyncio
async def test_analyze_water_dimer_fragments(mock_session, tmp_path):
    """双分子碎片体系：不崩溃，识别 2 个碎片与氢键 forming_candidate。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=WATER_DIMER_XYZ,
            zmat_path=str(tmp_path / "dimer.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert "Fragments: 2" in result.report
    assert any(a["status"] == "forming_candidate" and set(a["atoms"]) == {"H2", "O4"}
               for a in result.anomalies)
    # 多碎片 zmat 也能生成并可 round-trip 还原坐标
    import numpy as np

    assert os.path.isfile(result.zmat_path)
    rt = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_path=result.zmat_path,
        ),
        mock_session,
    )
    assert rt.is_success is True
    orig = _parse_xyz_positions(WATER_DIMER_XYZ)
    back = _parse_xyz_positions(rt.xyz_text)
    p_orig = np.array([p for _, p in orig])
    p_back = np.array([p for _, p in back])
    rmsd = float(np.sqrt(((p_orig - p_back) ** 2).sum(axis=1).mean()))
    assert rmsd < 0.05


@pytest.mark.asyncio
async def test_roundtrip_zmatrix_to_cartesian(mock_session, tmp_path):
    """analyze → zmatrix_to_cartesian round-trip：坐标 RMSD < 0.05 Å。"""
    import numpy as np

    tool = InternalCoordinates()
    analyze_result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=BUTANE_XYZ,
            zmat_path=str(tmp_path / "butane.zmat"),
        ),
        mock_session,
    )
    assert analyze_result.is_success is True

    rt_result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian",
            zmatrix_path=analyze_result.zmat_path,
            output_path=str(tmp_path / "butane_rt.xyz"),
        ),
        mock_session,
    )
    assert rt_result.is_success is True
    assert os.path.isfile(str(tmp_path / "butane_rt.xyz"))

    orig = _parse_xyz_positions(BUTANE_XYZ)
    back = _parse_xyz_positions(rt_result.xyz_text)
    assert len(orig) == len(back)
    assert [s for s, _ in orig] == [s for s, _ in back]
    p_orig = np.array([p for _, p in orig])
    p_back = np.array([p for _, p in back])
    rmsd = float(np.sqrt(((p_orig - p_back) ** 2).sum(axis=1).mean()))
    assert rmsd < 0.05


@pytest.mark.asyncio
async def test_zmatrix_text_input(mock_session):
    """zmatrix_text 直接传文本也能还原坐标。"""
    zmatrix_text = """# Z-matrix test
  1  O1    | origin   r=0.0000 | e_z    a=0.00 | e_x    d=0.00
  2  H2    | O1       r=0.9570 | e_z    a=90.00 | e_x    d=90.00
  3  H3    | O1       r=0.9570 | H2     a=104.50 | e_x    d=0.00
"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_text=zmatrix_text,
        ),
        mock_session,
    )
    assert result.is_success is True
    atoms = _parse_xyz_positions(result.xyz_text)
    assert len(atoms) == 3
    import numpy as np

    pos = np.array([p for _, p in atoms])
    # O-H 键长应约 0.957
    assert abs(np.linalg.norm(pos[1] - pos[0]) - 0.957) < 1e-3
    assert abs(np.linalg.norm(pos[2] - pos[0]) - 0.957) < 1e-3


@pytest.mark.asyncio
async def test_zmatrix_collinear_dihedral_ref_recovers(mock_session):
    """回归：d 参考与 a-b 轴共线时（二面角数学上未定义）不应报"参考原子无效"，
    换成非共线 magic 参考继续重建，键长/键角保持精确。"""
    # C2 落在 x 轴上，第 3 行的 d=e_x 与 O1-C2 轴共线——旧实现在此报
    # "第 3 行参考原子无效，无法重建坐标"。
    zmatrix_text = """# Z-matrix collinear case
  1  O1    | origin   r=0.0000 | e_z    a=0.00   | e_x    d=0.00
  2  C2    | O1       r=1.2000 | e_z    a=90.00  | e_x    d=0.00
  3  H3    | C2       r=1.0900 | O1     a=109.50 | e_x    d=180.00
"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_text=zmatrix_text,
        ),
        mock_session,
    )
    assert result.is_success is True
    atoms = _parse_xyz_positions(result.xyz_text)
    import numpy as np

    pos = np.array([p for _, p in atoms])
    assert abs(np.linalg.norm(pos[1] - pos[0]) - 1.20) < 1e-3
    assert abs(np.linalg.norm(pos[2] - pos[1]) - 1.09) < 1e-3
    # ∠O-C-H = 109.5°
    v1 = pos[0] - pos[1]
    v2 = pos[2] - pos[1]
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    angle = float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))
    assert abs(angle - 109.5) < 0.1


# ---------------------------------------------------------------------------
# F6：平面 6 元环（Q≈0，如苯）必须标 planar，不得误标 near-chair
# ---------------------------------------------------------------------------


def _planar_benzene_xyz() -> str:
    """苯：6 C 在 xy 平面正六边形（r=1.40 Å），6 H 沿径向向外（C-H 1.09 Å），全平面。"""
    import math

    lines = ["12", "planar benzene"]
    rc, rh = 1.40, 1.09
    for i in range(6):
        ang = math.pi / 3.0 * i
        cx, cy = rc * math.cos(ang), rc * math.sin(ang)
        lines.append(f"C   {cx:>12.6f}  {cy:>12.6f}  0.000000")
    for i in range(6):
        ang = math.pi / 3.0 * i
        hx, hy = (rc + rh) * math.cos(ang), (rc + rh) * math.sin(ang)
        lines.append(f"H   {hx:>12.6f}  {hy:>12.6f}  0.000000")
    return "\n".join(lines) + "\n"


@pytest.mark.asyncio
async def test_analyze_planar_benzene_ring(mock_session, tmp_path):
    """平面苯（CP Q≈0）：必须标 planar，绝不标 near-chair。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=_planar_benzene_xyz(),
            zmat_path=str(tmp_path / "benzene.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    rings_section = result.report.split("== Rings ==")[1].split("==")[0]
    assert "6-membered ring" in rings_section
    assert "CP:" in rings_section
    assert "planar" in rings_section
    assert "near-chair" not in rings_section


# ---------------------------------------------------------------------------
# Task 5：路径收口、几何/Z-matrix 状态分离、结构化 Z-matrix 校验
# ---------------------------------------------------------------------------

from cloudra.persistence.workspace import resolve_tool_path  # noqa: E402


class _AgentBridge:
    def __init__(self, working_directory: str):
        self.working_directory = working_directory


def _bound_tool(working_directory: str) -> InternalCoordinates:
    """把工具绑定到一个 agent 工作目录（等价于运行时注入的 subagent 桥）。"""
    tool = InternalCoordinates()
    tool.subagent = _AgentBridge(working_directory)
    return tool


def test_tool_path_fields_go_through_resolve_tool_path(tmp_path):
    """路径字段必须走同一个原语：相对路径解析到 agent 工作目录，绝对路径原样。"""
    ws = tmp_path / "ws-a"
    ws.mkdir()
    tool = _bound_tool(str(ws))
    assert resolve_tool_path(tool, "x.zmat") == str((ws / "x.zmat").resolve())
    assert resolve_tool_path(tool, "/abs/x.zmat") == "/abs/x.zmat"


@pytest.mark.asyncio
async def test_two_agents_with_same_named_files_do_not_cross_directories(mock_session, tmp_path):
    """两个 agent 工作目录下同名文件互不串目录（读、写、默认 zmat 路径都要隔开）。"""
    ws_a = tmp_path / "agent_a"
    ws_b = tmp_path / "agent_b"
    ws_a.mkdir()
    ws_b.mkdir()
    (ws_a / "structure.xyz").write_text(WATER_XYZ, encoding="utf-8")
    (ws_b / "structure.xyz").write_text(BUTANE_XYZ, encoding="utf-8")

    results = {}
    for name, ws in (("a", ws_a), ("b", ws_b)):
        tool = _bound_tool(str(ws))
        result = await tool.safe_call(
            InternalCoordinates_input_schema(mode="analyze", input_path="structure.xyz"),
            mock_session,
        )
        assert result.is_success is True, result.message
        results[name] = result

    # 各自读到了自己的工作目录里的文件（原子数不同）
    assert "Atoms: 3" in results["a"].report
    assert "Atoms: 14" in results["b"].report
    # 默认 zmat 路径落在各自的工作目录里，且两个输出文件互不覆盖
    assert results["a"].zmat_path == str(ws_a / "structure.zmat")
    assert results["b"].zmat_path == str(ws_b / "structure.zmat")
    assert os.path.isfile(results["a"].zmat_path)
    assert os.path.isfile(results["b"].zmat_path)
    assert "O1" in open(results["a"].zmat_path, encoding="utf-8").read()
    assert "C1" in open(results["b"].zmat_path, encoding="utf-8").read()


@pytest.mark.asyncio
async def test_text_only_analyze_writes_zmat_into_the_agent_workspace(mock_session, tmp_path):
    """纯文本输入时的默认 zmat 路径也必须落在 agent 工作目录（不是进程 cwd）。"""
    ws = tmp_path / "ws_text"
    ws.mkdir()
    tool = _bound_tool(str(ws))
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="analyze", input_text=WATER_XYZ), mock_session,
    )
    assert result.is_success is True, result.message
    assert result.zmat_path == str(ws / "structure.zmat")
    assert os.path.isfile(result.zmat_path)


@pytest.mark.asyncio
async def test_missing_zmatrix_file_reports_the_resolved_target(mock_session, tmp_path):
    """读取失败必须报出**解析后的目标路径**与具体错误，不得说成"没提供参数"。"""
    ws = tmp_path / "ws_missing"
    ws.mkdir()
    tool = _bound_tool(str(ws))
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_path="absent.zmat",
        ),
        mock_session,
    )
    assert result.is_success is False
    assert str(ws / "absent.zmat") in result.message
    assert "No such file" in result.message or "not found" in result.message.lower()
    assert "requires zmatrix_path or zmatrix_text" not in result.message


@pytest.mark.asyncio
async def test_geometry_report_survives_zmatrix_export_failure(mock_session, tmp_path, monkeypatch):
    """故意让 Z-matrix 导出失败：已完成的距离/角度测量必须仍然可用。"""
    import cloudra.tools.Chemtool.internal_coordinates as ic_mod

    def boom(self, zmat_frame):
        raise RuntimeError("simulated chemcoord z-matrix failure")

    monkeypatch.setattr(ic_mod.InternalCoordinates, "_render_zmatrix", boom)
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=FAKE_TS_XYZ, zmat_path=str(tmp_path / "boom.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert result.zmat_status == "failed"
    assert "simulated chemcoord z-matrix failure" in result.zmat_error
    assert result.zmat_path == ""
    assert result.zmat_lines == 0
    # 几何报告仍在，且异常（假 TS 的拉长 C-O）依然可用
    assert "== Summary ==" in result.report
    assert "Atoms: 7" in result.report
    assert "== Abnormal Bonds ==" in result.report
    assert result.anomalies, "几何异常清单必须仍然可用"
    assert any("Z-matrix export failed" in line for line in result.report.splitlines())
    assert "Z-matrix export FAILED" in result.message
    assert not (tmp_path / "boom.zmat").exists()


@pytest.mark.asyncio
async def test_successful_analyze_reports_zmat_written(mock_session, tmp_path):
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=WATER_XYZ, zmat_path=str(tmp_path / "ok.zmat"),
        ),
        mock_session,
    )
    assert result.is_success is True
    assert result.zmat_status == "written"
    assert result.zmat_error == ""
    assert result.zmat_lines > 0


# ---------- Z-matrix 输入的逐 token 校验 ----------

_LEGAL_PARTIAL_ZMAT = """# 合法绝对参考：第 1 行可省 b/a/d，第 2 行可省 a/d，第 3 行可省 d
  1  O1    | origin   r=0.0000
  2  H2    | O1       r=0.9570
  3  H3    | O1       r=0.9570 | H2     a=104.50
"""


@pytest.mark.asyncio
async def test_legal_absolute_reference_omissions_are_filled_by_position(mock_session):
    """合法绝对参考规则：前三个数据行按位置补 origin/e_z/e_x，坐标可重建。"""
    import numpy as np

    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="zmatrix_to_cartesian", zmatrix_text=_LEGAL_PARTIAL_ZMAT,
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    atoms = _parse_xyz_positions(result.xyz_text)
    assert [s for s, _ in atoms] == ["O", "H", "H"]
    pos = np.array([p for _, p in atoms])
    assert abs(float(np.linalg.norm(pos[1] - pos[0])) - 0.957) < 1e-3
    assert abs(float(np.linalg.norm(pos[2] - pos[0])) - 0.957) < 1e-3


@pytest.mark.asyncio
@pytest.mark.parametrize("case,expected", [
    # 第 4 行起缺数值 / 缺父原子 = 非法缺字段
    ("  1  O1    | origin   r=0.0000\n  2  H2    | O1       r=0.9570\n"
     "  3  H3    | O1       r=0.9570 | H2     a=104.50\n  4  H4    | O1       r=0.9570\n",
     "missing"),
    # 未知引用（既不是 magic、也不是已声明标签/行号）
    ("  1  O1    | origin   r=0.0000\n  2  H2    | O1       r=0.9570\n"
     "  3  H3    | O1       r=0.9570 | H2     a=104.50 | NOPE   d=0.00\n",
     "unknown"),
    # 非有限数值
    ("  1  O1    | origin   r=0.0000\n  2  H2    | O1       r=nan\n",
     "not a finite number"),
    # 数值根本不是数字
    ("  1  O1    | origin   r=0.0000\n  2  H2    | O1       r=abc\n",
     "is not a number"),
    # 段位置与 key 不匹配
    ("  1  O1    | origin   r=0.0000\n  2  H2    | O1       a=0.9570\n",
     "'r=<number>'"),
    # 标签编号与行号不一致
    ("  1  O1    | origin   r=0.0000\n  2  H9    | O1       r=0.9570\n",
     "disagrees with the row index"),
    # 重复行号
    ("  1  O1    | origin   r=0.0000\n  1  H2    | O1       r=0.9570\n",
     "duplicate atom index"),
    # 标签不是元素符号
    ("  1  12    | origin   r=0.0000\n", "does not start with an element symbol"),
])
async def test_illegal_zmatrix_input_is_rejected(mock_session, case, expected):
    """非法 Z-matrix 输入一律明确拒绝，绝不静默补零/猜参考。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="zmatrix_to_cartesian", zmatrix_text=case),
        mock_session,
    )
    assert result.is_success is False
    assert expected.lower() in result.message.lower(), result.message


def test_zmatrix_module_has_no_regex():
    """校验路径一律不准有正则：本模块不得再 import re（AGENTS.md 硬约束）。"""
    import cloudra.tools.Chemtool.internal_coordinates as ic_mod

    source = open(ic_mod.__file__, encoding="utf-8").read()
    import_lines = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any(
        line == "import re" or line.startswith("import re ") or line == "from re import"
        or line.startswith("from re import ")
        for line in import_lines
    ), import_lines
    assert "re.sub(" not in source and "re.search(" not in source and "re.match(" not in source
    assert not hasattr(ic_mod, "re")


def test_chemistry_thresholds_unchanged():
    """本任务不改动既有化学异常阈值（只改路径/解析/状态表达）。"""
    tool = InternalCoordinates()
    schema = InternalCoordinates_input_schema(mode="analyze", input_text=WATER_XYZ)
    assert schema.bond_tolerance == 0.15
    assert schema.angle_tolerance == 12.0
    assert schema.charge == 0
    assert tool._covalent_radius("C") == pytest.approx(0.76, abs=0.05)


# ---------------------------------------------------------------------------
# mode=transform：rotate / stretch / invert_chirality + 变换后校验
# ---------------------------------------------------------------------------


def _embed_xyz(smiles: str, seed: int = 42) -> str:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToXYZBlock(mol)


def _parse_xyz_block(xyz_text: str):
    """按 xyz 结构解析（第 1 行原子数、第 2 行注释可能为空），返回 [(symbol, (x, y, z)), ...]。"""
    lines = xyz_text.splitlines()
    out = []
    for ln in lines[2:2 + int(lines[0])]:
        tok = ln.split()
        out.append((tok[0], tuple(float(v) for v in tok[1:4])))
    return out


def _chiral_labels(xyz_text: str) -> list:
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    mol = Chem.MolFromXYZBlock(xyz_text)
    rdDetermineBonds.DetermineConnectivity(mol)
    rdDetermineBonds.DetermineBonds(mol, charge=0)
    Chem.AssignStereochemistryFrom3D(mol)
    return Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)


# 人工重叠夹具：C3 绕 C1-C2 轴（z 轴）转 120° 后精确落到 C4 上。
# 初始时全部原子对间距 > 0.75×vdW，无任何异常。
CLASH_SETUP_XYZ = """4
artificial overlap fixture
C   0.000000  0.000000  -2.000000
C   0.000000  0.000000   2.000000
C   1.600000  0.000000   0.000000
C  -0.800000  1.385641   0.000000
"""


@pytest.mark.asyncio
async def test_transform_rotate_side_of_bond(mock_session):
    """乙烷绕 C-C 键旋转甲基 60°：二面角变化 60°，无 clash，op 摘要正确。"""
    import numpy as np

    import cloudra.tools.Chemtool.internal_coordinates as ic_mod

    xyz = _embed_xyz("CC")
    p0 = np.array([p for _, p in _parse_xyz_block(xyz)])
    h1 = min(range(2, 8), key=lambda i: np.linalg.norm(p0[i] - p0[0]))
    h2 = min(range(2, 8), key=lambda i: np.linalg.norm(p0[i] - p0[1]))
    dih_before = ic_mod._dihedral_deg(p0[h1], p0[0], p0[1], p0[h2])

    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=xyz,
            operations=[{"type": "rotate", "axis_atoms": [1, 2], "degrees": 60.0,
                         "side_of_bond": [1, 2]}],
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert len(result.operations_applied) == 1
    op = result.operations_applied[0]
    assert op["type"] == "rotate"
    assert op["axis_atoms"] == [1, 2]
    assert op["degrees"] == 60.0
    # 甲基侧 = C2 + 3 H，轴上原子 C2 不计入 moved
    assert op["n_moved"] == 3
    assert 2 not in op["moved_atoms"]

    p1 = np.array([p for _, p in _parse_xyz_block(result.xyz_text)])
    dih_after = ic_mod._dihedral_deg(p1[h1], p1[0], p1[1], p1[h2])
    delta = (dih_after - dih_before + 180.0) % 360.0 - 180.0
    assert abs(abs(delta) - 60.0) < 1.0
    # 轴另一侧（C1 及其 H）不动
    assert np.allclose(p1[0], p0[0], atol=1e-8)
    assert np.allclose(p1[h1], p0[h1], atol=1e-8)
    # 刚体旋转不引入 clash
    assert not any(a["status"] == "clash" for a in result.anomalies)
    assert "== Operations Applied ==" in result.report
    assert "== Validation After Transform ==" in result.report
    assert "== Transform Comparison ==" in result.report


@pytest.mark.asyncio
async def test_transform_rotate_explicit_atoms(mock_session):
    """丁烷：显式原子组绕 C3-C4 轴旋转 120°，组外原子完全不动，片内键长保持。"""
    import numpy as np

    p0 = np.array([p for _, p in _parse_xyz_block(BUTANE_XYZ)])
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=BUTANE_XYZ,
            operations=[{"type": "rotate", "axis_atoms": [3, 4], "degrees": 120.0,
                         "atoms": [4, 12, 13, 14]}],
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    op = result.operations_applied[0]
    assert op["moved_atoms"] == [12, 13, 14]

    p1 = np.array([p for _, p in _parse_xyz_block(result.xyz_text)])
    # 组外原子（含轴原子 C3/C4）不动
    assert np.allclose(p1[:4], p0[:4], atol=1e-8)
    assert np.allclose(p1[4:11], p0[4:11], atol=1e-8)
    # 甲基 H 明显移动，C4-H 键长保持（刚体旋转）
    assert np.linalg.norm(p1[11] - p0[11]) > 0.5
    assert abs(np.linalg.norm(p1[3] - p1[11]) - np.linalg.norm(p0[3] - p0[11])) < 1e-6


@pytest.mark.asyncio
async def test_transform_stretch_elongated_and_compressed(mock_session):
    """乙烷 C-C 拉长到 2.6 Å → breaking_suspect；压缩到 1.2 Å → compressed。"""
    import numpy as np

    xyz = _embed_xyz("CC")
    tool = InternalCoordinates()
    stretched = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=xyz, watch_pairs=[[1, 2]],
            operations=[{"type": "stretch", "atoms": [1, 2], "new_length": 2.6}],
        ),
        mock_session,
    )
    assert stretched.is_success is True, stretched.message
    assert any(a["status"] == "breaking_suspect" and set(a["atoms"]) == {"C1", "C2"}
               for a in stretched.anomalies), stretched.anomalies
    p1 = np.array([p for _, p in _parse_xyz_block(stretched.xyz_text)])
    assert abs(np.linalg.norm(p1[1] - p1[0]) - 2.6) < 1e-6
    assert "== Validation After Transform ==" in stretched.report
    assert "[Reactive Center]" in stretched.report

    compressed = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=xyz,
            operations=[{"type": "stretch", "atoms": [1, 2], "delta": -0.34}],
        ),
        mock_session,
    )
    assert compressed.is_success is True, compressed.message
    assert any(a["status"] == "compressed" and set(a["atoms"]) == {"C1", "C2"}
               for a in compressed.anomalies), compressed.anomalies
    # 变换前无异常、变换后引入异常 → comparison 段计数
    assert stretched.anomalies_before == []
    comp = compressed.report.split("== Transform Comparison ==")[1]
    assert "New anomalies introduced:" in comp


@pytest.mark.asyncio
async def test_transform_invert_chirality_flips_center(mock_session):
    """CHFClBr：交换 F/H 两分支，RDKit 判定手性翻转，且所有键长保持（刚体）。"""
    import numpy as np

    xyz = _embed_xyz("FC(Cl)Br")
    before = _chiral_labels(xyz)
    assert len(before) == 1 and before[0][1] in ("R", "S"), before

    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=xyz,
            operations=[{"type": "invert_chirality", "center": 2, "swap": [1, 5]}],
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    op = result.operations_applied[0]
    assert op["type"] == "invert_chirality"
    assert op["center"] == 2 and op["swap"] == [1, 5]

    after = _chiral_labels(result.xyz_text)
    assert len(after) == 1 and after[0][1] in ("R", "S"), after
    assert after[0][1] != before[0][1]

    # 刚体性：中心到每个取代基的键长在变换前后不变
    p0 = np.array([p for _, p in _parse_xyz_block(xyz)])
    p1 = np.array([p for _, p in _parse_xyz_block(result.xyz_text)])
    for k in (0, 2, 3, 4):
        assert abs(np.linalg.norm(p1[k] - p1[1]) - np.linalg.norm(p0[k] - p0[1])) < 1e-6
    # 中心不动
    assert np.allclose(p1[1], p0[1], atol=1e-8)


@pytest.mark.asyncio
async def test_transform_rotate_creates_clash(mock_session):
    """rotate 使非键原子重叠 → 变换后 anomalies 出现 clash，变换前没有。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=CLASH_SETUP_XYZ,
            operations=[{"type": "rotate", "axis_atoms": [1, 2], "degrees": 120.0,
                         "atoms": [3]}],
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert result.anomalies_before == []
    assert any(a["status"] == "clash" and set(a["atoms"]) == {"C3", "C4"}
               for a in result.anomalies), result.anomalies


@pytest.mark.asyncio
@pytest.mark.parametrize("xyz,ops,expected", [
    # 环上 side_of_bond：删边后图仍连通
    (CYCLOHEXANE_XYZ,
     [{"type": "rotate", "axis_atoms": [1, 2], "degrees": 60.0, "side_of_bond": [1, 2]}],
     "ring"),
    # side_of_bond 不成键
    (WATER_XYZ,
     [{"type": "rotate", "axis_atoms": [1, 2], "degrees": 60.0, "side_of_bond": [2, 3]}],
     "not bonded"),
    # 环上 stretch
    (CYCLOHEXANE_XYZ,
     [{"type": "stretch", "atoms": [1, 2], "delta": 0.5}],
     "ring"),
    # stretch 不存在的键
    (WATER_XYZ,
     [{"type": "stretch", "atoms": [2, 3], "delta": 0.5}],
     "not bonded"),
    # delta 与 new_length 同时给 / 都不给
    (WATER_XYZ,
     [{"type": "stretch", "atoms": [1, 2], "delta": 0.5, "new_length": 1.5}],
     "exactly one"),
    (WATER_XYZ,
     [{"type": "stretch", "atoms": [1, 2]}],
     "exactly one"),
    # 目标长度非正
    (WATER_XYZ,
     [{"type": "stretch", "atoms": [1, 2], "new_length": -0.5}],
     "> 0"),
    # 未知 op 类型
    (WATER_XYZ,
     [{"type": "fly", "atoms": [1, 2]}],
     "unknown transform operation type"),
    # atoms 与 side_of_bond 同时给
    (WATER_XYZ,
     [{"type": "rotate", "axis_atoms": [1, 2], "degrees": 30.0,
       "atoms": [2], "side_of_bond": [1, 2]}],
     "exactly one"),
    # 原子索引越界
    (WATER_XYZ,
     [{"type": "rotate", "axis_atoms": [1, 9], "degrees": 30.0, "atoms": [2]}],
     "not a valid 1-based index"),
    # swap 原子不是 center 的成键邻居（H10 属于 C3 而非 C2）
    (BUTANE_XYZ,
     [{"type": "invert_chirality", "center": 2, "swap": [1, 10]}],
     "bonded neighbors"),
])
async def test_transform_invalid_operations_fail_loud(mock_session, xyz, ops, expected):
    """非法 op 一律 fail-loud：is_success=False 且 message 含关键信息。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="transform", input_text=xyz, operations=ops),
        mock_session,
    )
    assert result.is_success is False
    assert expected.lower() in result.message.lower(), result.message


@pytest.mark.asyncio
async def test_transform_requires_operations(mock_session):
    """mode=transform 不给 operations → 明确报错。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(mode="transform", input_text=WATER_XYZ),
        mock_session,
    )
    assert result.is_success is False
    assert "operations" in result.message


@pytest.mark.asyncio
async def test_operations_rejected_in_analyze_mode(mock_session):
    """operations 只在 mode=transform 合法，其余模式 fail-loud。"""
    tool = InternalCoordinates()
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_text=WATER_XYZ,
            operations=[{"type": "rotate", "axis_atoms": [1, 2], "degrees": 30.0, "atoms": [2]}],
        ),
        mock_session,
    )
    assert result.is_success is False
    assert "mode=transform" in result.message


@pytest.mark.asyncio
async def test_transform_output_roundtrip(mock_session, tmp_path):
    """transform 的 xyz_text/output_path 能被本工具再次读取并 analyze。"""
    tool = InternalCoordinates()
    out_file = tmp_path / "rotated.xyz"
    result = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="transform", input_text=_embed_xyz("CC"),
            operations=[{"type": "rotate", "axis_atoms": [1, 2], "degrees": 60.0,
                         "side_of_bond": [1, 2]}],
            output_path=str(out_file),
        ),
        mock_session,
    )
    assert result.is_success is True, result.message
    assert result.output_path == str(out_file)
    assert out_file.read_text(encoding="utf-8") == result.xyz_text

    atoms = InternalCoordinates._load_atoms_from_path_or_text(None, result.xyz_text, "auto")
    assert len(atoms) == 8

    analyze = await tool.safe_call(
        InternalCoordinates_input_schema(
            mode="analyze", input_path=str(out_file),
            zmat_path=str(tmp_path / "rotated.zmat"),
        ),
        mock_session,
    )
    assert analyze.is_success is True, analyze.message
    assert "Atoms: 8" in analyze.report
