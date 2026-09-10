"""拓扑变更对比：只**记录**变化，不判定变化是否被允许（Task 4）。

CREST 在初始几何优化后若发现拓扑变化会打印 ``WARNING! Change in topology detected!``；
CREST 2.12 自己在提示文本里给了三条出路（单独 xTB 预优化、``--noreftopo``、加键长约束或换
固定拓扑的方法），但选哪条属于科学决策，必须由用户确认。本模块只负责把"到底变了什么"
确定性地列出来：

- 变化前（我们交给 CREST 的输入）与变化后（CREST 留下的 ``xtbopt.log`` 末帧）的连接表差集；
- 每条变化标注 ``intra_component``（片内）还是 ``inter_component``（片间）——碎片是否开始
  成键/断键是判断"是不是真的在反应"的关键事实，必须先摆出来而不是先下结论；
- 可选：与"预期产物"结构对比，报告连接表是否一致（仍是**对比事实**，不是"允许"）。

**判据复用**：连接表由 ``internal_coordinates.distance_connectivity`` 给出（``r ≤ 1.25 ×
Cordero 共价半径和``），与本仓库既有的几何分析共用同一套阈值，本模块不新立任何化学参数。

**本模块不做的事**：不把任何变化判为允许/不允许，不把"跑完没报错"当成"进入预期产物"，
也不把几何启发式提升为已证实的成键/断键。
"""

from __future__ import annotations

from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

CONNECTIVITY_RULE = (
    "r <= 1.25 x (Cordero covalent-radius sum)  [internal_coordinates.distance_connectivity]"
)

Bond = tuple[int, int]


class BondChange(BaseModel):
    """一条连接表变化。"""

    kind: Literal["formed", "broken"]
    atoms: tuple[int, int] = Field(description="0-based 原子序号，升序")
    symbols: tuple[str, str]
    scope: Literal["intra_component", "inter_component"] = Field(
        description="intra_component：同一组分内部；inter_component：跨越两个组分（片间成键/断键）"
    )
    distance_before: Optional[float] = Field(default=None, description="变化前距离（Å）；断键方为 None")
    distance_after: Optional[float] = Field(default=None, description="变化后距离（Å）；成键方为 None")


class TopologyChangeReport(BaseModel):
    """一次对比的完整记录。"""

    before_path: str = Field(description="变化前结构文件（交给引擎的输入）")
    after_path: str = Field(description="变化后结构文件（引擎留下的优化末帧）")
    connectivity_rule: str = Field(default=CONNECTIVITY_RULE, description="所用连接表判据的原样说明")
    component_of_atom: list[int] = Field(
        default_factory=list, description="**变化前**每个原子所属连通分量编号"
    )
    formed: list[BondChange] = Field(default_factory=list)
    broken: list[BondChange] = Field(default_factory=list)
    intra_component_changes: int = 0
    inter_component_changes: int = 0
    expected_product_path: str = Field(default="", description="可选的预期产物结构文件")
    matches_expected_product: Optional[bool] = Field(
        default=None,
        description="给出预期产物时：优化末帧的连接表是否与其完全一致。None = 未提供预期产物，"
                    "因此「是否进入预期产物」在本报告中**未判定**",
    )
    notes: list[str] = Field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.formed) + len(self.broken)


def default_connectivity() -> Callable:
    """默认连接表判据。

    复用 ``internal_coordinates`` 的原语（延迟导入：``tools/core`` 不在导入期依赖 Chemtool，
    而判据本身仍然只有一份实现，绝不在这里另立阈值）。
    """
    from cloudra.tools.Chemtool.internal_coordinates import distance_connectivity

    return distance_connectivity


def components_of(symbols: list[str], positions, connectivity: Callable) -> list[int]:
    """按连接表求连通分量编号（每个原子的分量 id，按首次出现顺序从 0 起）。"""
    adjacency: dict[int, set[int]] = {i: set() for i in range(len(symbols))}
    for (i, j) in connectivity(symbols, positions):
        adjacency[i].add(j)
        adjacency[j].add(i)
    component = [-1] * len(symbols)
    next_id = 0
    for start in range(len(symbols)):
        if component[start] >= 0:
            continue
        stack = [start]
        while stack:
            node = stack.pop()
            if component[node] >= 0:
                continue
            component[node] = next_id
            stack.extend(adjacency[node])
        next_id += 1
    return component


def canonical_symbols(symbols) -> list[str]:
    """把元素符号规范成大小写正确的形式并校验它确实是元素。

    xTB 的 ``xtbopt.log`` 用小写写元素符号（``f c cl h``），而输入 xyz 用标准大小写
    （``F C Cl H``）。不规范化就会把"同一个体系"误判成"元素序列变了"而拒绝对比——
    这正是"不同格式的同一事实"问题，必须在读入侧解决，不能靠对比侧放宽。
    """
    from ase.data import chemical_symbols

    known = set(chemical_symbols)
    canonical: list[str] = []
    for raw in symbols:
        candidate = raw[:1].upper() + raw[1:].lower()
        if candidate not in known:
            raise ValueError(
                f"{raw!r} is not a recognised element symbol (canonical form {candidate!r})"
            )
        canonical.append(candidate)
    return canonical


def read_xyz_frame(path: str) -> tuple[list[str], list[list[float]]]:
    """读单帧 xyz 的 ``(元素, 坐标)``；文件缺失或帧不完整即 fail-loud。"""
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms

    atoms = read_xyz_atoms(path)
    if not atoms:
        raise ValueError(f"{path}: no atoms in the xyz frame")
    return canonical_symbols([symbol for symbol, _ in atoms]), [position for _, position in atoms]


def read_last_xtbopt_frame(path: str) -> tuple[list[str], list[list[float]]]:
    """读 xTB 优化轨迹 ``xtbopt.log`` 的**末帧**（每帧为 xyz + ``energy:`` 注释行）。

    xTB 逐帧追加写入，末帧即初始优化结束时我们真正拿到的几何；只有末帧完整才算读成功。
    """
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    frames: list[tuple[list[str], list[list[float]]]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        try:
            count = int(stripped)
        except ValueError:
            index += 1
            continue
        symbols: list[str] = []
        positions: list[list[float]] = []
        for line in lines[index + 2: index + 2 + count]:
            parts = line.split()
            if len(parts) < 4:
                break
            symbols.append(parts[0])
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        if len(symbols) == count:
            frames.append((symbols, positions))
        index += 2 + count
    if not frames:
        raise ValueError(f"{path}: no complete xyz frame could be read")
    symbols, positions = frames[-1]
    return canonical_symbols(symbols), positions


def _distance(positions, i: int, j: int) -> float:
    import numpy as np

    return float(np.linalg.norm(np.asarray(positions[i], dtype=float)
                                - np.asarray(positions[j], dtype=float)))


def compare_topology(
    *,
    before_path: str,
    after_path: str,
    before: tuple[list[str], list[list[float]]],
    after: tuple[list[str], list[list[float]]],
    connectivity: Optional[Callable] = None,
    expected_product_path: str = "",
    expected_product: Optional[tuple[list[str], list[list[float]]]] = None,
) -> TopologyChangeReport:
    """对比变化前后的连接表，逐条记录增/减键及其片内/片间归属。

    原子数或元素序列不一致时 fail-loud：那说明对比的**不是**同一个体系（例如产物结构被
    误当成优化末帧），此时给出"变化清单"只会误导。
    """
    symbols_before, positions_before = before
    symbols_after, positions_after = after
    if symbols_before != symbols_after:
        raise ValueError(
            "cannot compare topology: the element sequence changed between the two structures "
            f"({len(symbols_before)} vs {len(symbols_after)} atoms, "
            f"{symbols_before[:6]}... vs {symbols_after[:6]}...) — these are not the same system"
        )

    connectivity = connectivity or default_connectivity()
    bonds_before = set(connectivity(symbols_before, positions_before))
    bonds_after = set(connectivity(symbols_after, positions_after))
    component_of_atom = components_of(symbols_before, positions_before, connectivity)

    def make_change(kind: str, bond: Bond) -> BondChange:
        i, j = bond
        scope = (
            "intra_component" if component_of_atom[i] == component_of_atom[j]
            else "inter_component"
        )
        return BondChange(
            kind=kind,
            atoms=(i, j),
            symbols=(symbols_before[i], symbols_before[j]),
            scope=scope,
            distance_before=(_distance(positions_before, i, j) if kind == "broken" else None),
            distance_after=(_distance(positions_after, i, j) if kind == "formed" else None),
        )

    formed = [make_change("formed", b) for b in sorted(bonds_after - bonds_before)]
    broken = [make_change("broken", b) for b in sorted(bonds_before - bonds_after)]

    report = TopologyChangeReport(
        before_path=before_path,
        after_path=after_path,
        component_of_atom=component_of_atom,
        formed=formed,
        broken=broken,
        intra_component_changes=sum(
            1 for c in formed + broken if c.scope == "intra_component"
        ),
        inter_component_changes=sum(
            1 for c in formed + broken if c.scope == "inter_component"
        ),
        expected_product_path=expected_product_path,
        notes=[
            "changes are RECORDED ONLY: this report does not judge whether any change is "
            "allowed, expected, or an artifact",
            "connectivity is a distance criterion, not proof of bonding; a formed/broken entry "
            "is a geometric fact about these two structures, not a claim about the potential "
            "energy surface",
        ],
    )

    if expected_product is not None:
        symbols_product, positions_product = expected_product
        if symbols_product != symbols_before:
            raise ValueError(
                "cannot compare with the expected product: its element sequence differs from the "
                "reactant/complex structure"
            )
        bonds_product = set(connectivity(symbols_product, positions_product))
        report.matches_expected_product = bonds_product == bonds_after
        report.notes.append(
            "comparison with the expected product is a connectivity-set equality check on the "
            "optimized frame; it is not a verdict that the change is chemically allowed"
        )
    elif not expected_product_path:
        report.notes.append(
            "no expected product was provided, so whether the system entered the expected product "
            "is NOT determined here"
        )

    return report
