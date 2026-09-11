"""共享结构构建产物契约：组分身份、跨帧原子身份与力场优化轨迹。

本模块是 ``structure_builder`` 与三个建模入口（``smiles_to_mol`` / ``qm_input_writer`` /
``conformer_search``）共用的**唯一**产物类型来源。存在理由（issue #33 / #19）：

- 三个入口过去各自 ``AddHs`` + ``EmbedMolecule`` + ``MMFFOptimizeMolecule``，于是
  （a）同一缺陷要在三处分别修、（b）"优化返回 0"被当成"坐标可用"交给下游引擎，
  导致互穿几何（实测 F–C 0.1392 Å）被喂给 CREST/xTB 后梯度爆炸。
- 因此本模块把"**收敛状态**"表达为枚举与收敛码而不是自由文本，把"**原子身份**"表达为
  显式的来源记录而不是 ``AddHs`` 之后的数组下标。

轨迹为什么**流式落盘**而不留在内存：一条力场优化的迭代数是千级到万级（实测辛烷 11,371 步），
把每一帧的位置都留在 Python 对象里会到几百 MB。因此 ``TrajectoryWriter`` 每迭代追加一帧到
``frames.xyz``（坐标）与 ``frames.jsonl``（step/能量/最大梯度），``TrajectoryRecord`` 只持有
初始帧、终态、帧计数与收敛元数据；测试与下游复核从这两个文件读回全部逐迭代帧。
"保存每个优化迭代帧"这一要求仍被满足——只是落在文件里而不是对象里。

**为什么不用 ``ForceField.MinimizeTrajectory``**：本模块的目标 RDKit 构建（2026.03.5）
虽然导出该方法，但其返回的 ``RDKit::Snapshot`` **没有注册 Python 类**，调用即
``TypeError: No Python class registered for C++ class RDKit::Snapshot``（``rdForceField.so``
里只有 ``ForceField`` 与 ``MMFFMolProperties`` 两个导出名）。``ForceField.Positions()`` 返回
**只读 tuple**，外部优化器无法驱动 RDKit 的力场。因此在同一 ``ForceField`` 实例上逐迭代
``Minimize(maxIts=1)`` 并逐次采样，是本构建下唯一能取到逐迭代快照的手段；它是**同一条连续
优化**（同一实例、能量单调下降，且终态与一次性 ``Minimize(maxIts=N)`` 逐位一致，实测
dE ≤ 1e-4 kcal/mol），不是"每次新建力场从头再算"式的伪轨迹。
"""

from __future__ import annotations

import json
import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

from cloudra.persistence.fs_utils import atomic_write_text

# 力场能量单位：RDKit MMFF94/UFF 均以 kcal/mol 报告。
FORCE_FIELD_ENERGY_UNIT = "kcal/mol"

TRAJECTORY_JSON_NAME = "trajectory.json"
TRAJECTORY_XYZ_NAME = "frames.xyz"
TRAJECTORY_FRAMES_NAME = "frames.jsonl"
TRAJECTORY_MANIFEST_NAME = "trajectories.json"
TRAJECTORY_DIR_NAME = "trajectories"

ConvergenceStatus = Literal[
    "converged",      # 优化器报告收敛（收敛码 0）
    "not_converged",  # 达到迭代上限仍未收敛（收敛码 1）
    "failed",         # 力场构建/优化抛异常，异常前已记录的帧保留
]


class GeometryFrame(BaseModel):
    """优化轨迹上的一个确定状态（一帧坐标 + 该帧的能量/梯度）。"""

    step: int = Field(description="优化迭代序号；0 为初始帧，1..N 为每次迭代后的帧")
    symbols: list[str] = Field(description="元素符号，顺序即本构建输出的原子顺序")
    positions: list[list[float]] = Field(description="N×3 坐标（Å）")
    energy: float = Field(description="该帧的力场能量")
    energy_unit: str = Field(default=FORCE_FIELD_ENERGY_UNIT, description="能量单位")
    max_gradient: Optional[float] = Field(
        default=None, description="该帧最大梯度分量绝对值；无法取得时为 None（不填 0 冒充）"
    )


class TrajectoryRecord(BaseModel):
    """一条力场优化轨迹的元数据（逐迭代帧见 ``frames_path`` / ``frames_jsonl_path``）。

    失败轨迹同样保留：``status='failed'`` 时 ``failure`` 必非空，且异常前已记录的帧照常保留。
    """

    trajectory_id: str = Field(description="稳定编号 <component_id>-<engine>-attempt<N>，可作目录名")
    component_id: str = Field(description="所属组分编号，如 frag0")
    attempt: int = Field(description="该组分的第几次尝试（回退/重试各自独立编号，从 1 起）")
    engine: str = Field(description="实际使用的力场名，如 MMFF94 / UFF")
    symbols: list[str] = Field(description="本轨迹的原子序列（全程不变；力场优化不改元素集）")
    random_seed: Optional[int] = Field(
        default=None, description="构象采样随机种子；不采样时为 None"
    )
    frame_count: int = Field(description="总帧数（含初始帧），等于 iterations + 1")
    iterations: int = Field(description="实际发生的优化迭代次数（不含初始帧）")
    initial_frame: GeometryFrame = Field(description="初始帧（step=0）")
    final_frame: GeometryFrame = Field(description="终态帧（step=frame_count-1）")
    convergence_code: int = Field(
        description="优化器收敛码：0=收敛，1=达迭代上限未收敛，负值=力场不可用/异常"
    )
    status: ConvergenceStatus = Field(description="收敛状态（枚举，不用自由文本表达）")
    failure: str = Field(default="", description="status='failed' 时的具体异常文本；否则空串")
    notes: list[str] = Field(default_factory=list, description="该轨迹的补充事实")
    frames_path: str = Field(default="", description="逐迭代帧坐标文件（多帧 xyz）")
    frames_jsonl_path: str = Field(default="", description="逐迭代帧标量文件（step/能量/最大梯度）")
    json_path: str = Field(default="", description="本记录 JSON 路径")

    def model_post_init(self, __context) -> None:  # noqa: D105 - pydantic 钩子
        self._validate_consistency()

    def _validate_consistency(self) -> None:
        """轨迹自洽性 fail-loud：编号、帧计数、元素序列、收敛状态与收敛码必须一致。"""
        if self.frame_count < 1:
            raise ValueError(f"trajectory {self.trajectory_id}: frame_count must be >= 1")
        if self.iterations != self.frame_count - 1:
            raise ValueError(
                f"trajectory {self.trajectory_id}: iterations={self.iterations} is inconsistent "
                f"with frame_count={self.frame_count}"
            )
        if not self.symbols:
            raise ValueError(f"trajectory {self.trajectory_id}: symbols must not be empty")
        if self.initial_frame.step != 0:
            raise ValueError(
                f"trajectory {self.trajectory_id}: initial_frame.step must be 0, "
                f"got {self.initial_frame.step}"
            )
        if self.final_frame.step != self.frame_count - 1:
            raise ValueError(
                f"trajectory {self.trajectory_id}: final_frame.step must be {self.frame_count - 1}, "
                f"got {self.final_frame.step}"
            )
        for label, frame in (("initial", self.initial_frame), ("final", self.final_frame)):
            if len(frame.symbols) != len(self.symbols):
                raise ValueError(
                    f"trajectory {self.trajectory_id}: {label} frame has {len(frame.symbols)} "
                    f"symbols but the trajectory declares {len(self.symbols)}"
                )
            if frame.symbols != self.symbols:
                raise ValueError(
                    f"trajectory {self.trajectory_id}: {label} frame changed the element sequence; "
                    "a force-field trajectory must keep atom identity fixed"
                )
            if len(frame.positions) != len(frame.symbols):
                raise ValueError(
                    f"trajectory {self.trajectory_id}: {label} frame has {len(frame.positions)} "
                    f"positions for {len(frame.symbols)} atoms"
                )
            if frame.energy_unit != FORCE_FIELD_ENERGY_UNIT:
                raise ValueError(
                    f"trajectory {self.trajectory_id}: {label} frame reports energy unit "
                    f"{frame.energy_unit!r}, expected {FORCE_FIELD_ENERGY_UNIT!r}"
                )
        if self.status == "failed" and not self.failure:
            raise ValueError(
                f"trajectory {self.trajectory_id}: status='failed' requires a non-empty failure text"
            )
        if self.status != "failed" and self.failure:
            raise ValueError(
                f"trajectory {self.trajectory_id}: status={self.status!r} must not carry a failure text"
            )
        if (self.status == "converged") != (self.convergence_code == 0):
            raise ValueError(
                f"trajectory {self.trajectory_id}: status={self.status!r} is inconsistent with "
                f"convergence_code={self.convergence_code}"
            )

    def to_xyz(self) -> str:
        """本记录的初始帧 + 终态帧（区间摘要）；完整逐迭代帧在 ``frames_path``。"""
        chunks: list[str] = []
        for frame in (self.initial_frame, self.final_frame):
            chunks.append(str(len(frame.symbols)))
            chunks.append(
                f"trajectory_id={self.trajectory_id} step={frame.step} "
                f"energy={frame.energy:.6f} {frame.energy_unit}"
            )
            for symbol, position in zip(frame.symbols, frame.positions):
                x, y, z = position
                chunks.append(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}")
        return "\n".join(chunks) + "\n"


class TrajectoryArtifact(BaseModel):
    """一条轨迹落盘后的产物路径与计数。"""

    trajectory_id: str
    component_id: str
    status: ConvergenceStatus
    engine: str
    iterations: int
    frame_count: int
    json_path: str
    frames_path: str
    frames_jsonl_path: str


class FrameSummary(BaseModel):
    """``frames.jsonl`` 的一行：逐迭代帧的标量部分（坐标在 ``frames.xyz`` 的同序号帧里）。"""

    step: int
    energy: float
    energy_unit: str
    max_gradient: Optional[float] = None


def trajectory_dir_name(trajectory_id: str) -> str:
    """把轨迹编号收敛成安全的单层目录名（编号里不允许出现路径分隔符）。"""
    if "/" in trajectory_id or os.sep in trajectory_id or trajectory_id in ("", ".", ".."):
        raise ValueError(f"trajectory_id must be a single path-safe token, got {trajectory_id!r}")
    return trajectory_id


class TrajectoryWriter:
    """流式轨迹记录器：每迭代追加一帧，``finish()`` 产出校验过的 ``TrajectoryRecord``。

    用文件句柄就地追加而不是攒列表，是因为一条轨迹的帧数在千级到万级
    （实测辛烷 11,371 步），全部留在内存会到几百 MB。
    """

    def __init__(self, root_dir: str, trajectory_id: str, component_id: str, attempt: int,
                 engine: str, symbols: list[str], random_seed: Optional[int]):
        self.trajectory_id = trajectory_dir_name(trajectory_id)
        self.component_id = component_id
        self.attempt = attempt
        self.engine = engine
        self.symbols = list(symbols)
        self.random_seed = random_seed
        target = os.path.join(root_dir, TRAJECTORY_DIR_NAME, self.trajectory_id)
        os.makedirs(target, exist_ok=True)
        self.dir = target
        self.frames_path = os.path.join(target, TRAJECTORY_XYZ_NAME)
        self.frames_jsonl_path = os.path.join(target, TRAJECTORY_FRAMES_NAME)
        self.json_path = os.path.join(target, TRAJECTORY_JSON_NAME)
        self._xyz = open(self.frames_path, "w", encoding="utf-8")
        self._jsonl = open(self.frames_jsonl_path, "w", encoding="utf-8")
        self._count = 0
        self._initial: Optional[GeometryFrame] = None
        self._final: Optional[GeometryFrame] = None
        self._closed = False

    @property
    def frame_count(self) -> int:
        """已追加的帧数（下一个合法 ``step`` 即此值）。"""
        return self._count

    def append(self, step: int, positions, energy: float, max_gradient: Optional[float]) -> None:
        """追加一帧。``step`` 必须连续（调用方保证 0,1,2,...）。"""
        if self._closed:
            raise RuntimeError(f"trajectory {self.trajectory_id}: writer already closed")
        if step != self._count:
            raise ValueError(
                f"trajectory {self.trajectory_id}: frames must be appended in order; expected step "
                f"{self._count}, got {step}"
            )
        rows = [[float(v) for v in position] for position in positions]
        if len(rows) != len(self.symbols):
            raise ValueError(
                f"trajectory {self.trajectory_id}: frame {step} has {len(rows)} positions for "
                f"{len(self.symbols)} atoms"
            )
        frame = GeometryFrame(
            step=step,
            symbols=list(self.symbols),
            positions=rows,
            energy=float(energy),
            energy_unit=FORCE_FIELD_ENERGY_UNIT,
            max_gradient=None if max_gradient is None else float(max_gradient),
        )
        self._xyz.write(str(len(self.symbols)) + "\n")
        self._xyz.write(
            f"trajectory_id={self.trajectory_id} step={step} energy={frame.energy:.6f} "
            f"{FORCE_FIELD_ENERGY_UNIT}\n"
        )
        for symbol, position in zip(self.symbols, rows):
            x, y, z = position
            self._xyz.write(f"{symbol:<3} {x:>16.8f} {y:>16.8f} {z:>16.8f}\n")
        self._jsonl.write(json.dumps({
            "step": step,
            "energy": frame.energy,
            "energy_unit": FORCE_FIELD_ENERGY_UNIT,
            "max_gradient": frame.max_gradient,
        }) + "\n")
        if self._count == 0:
            self._initial = frame
        self._final = frame
        self._count += 1

    def finish(self, convergence_code: int, status: ConvergenceStatus,
               failure: str = "", notes: Optional[list[str]] = None) -> TrajectoryRecord:
        """收尾并落 ``trajectory.json``；帧文件在此之前已完整落盘。"""
        if self._closed:
            raise RuntimeError(f"trajectory {self.trajectory_id}: writer already closed")
        self._closed = True
        self._xyz.close()
        self._jsonl.close()
        if self._initial is None or self._final is None:
            raise ValueError(f"trajectory {self.trajectory_id}: no frames were appended")
        record = TrajectoryRecord(
            trajectory_id=self.trajectory_id,
            component_id=self.component_id,
            attempt=self.attempt,
            engine=self.engine,
            symbols=list(self.symbols),
            random_seed=self.random_seed,
            frame_count=self._count,
            iterations=self._count - 1,
            initial_frame=self._initial,
            final_frame=self._final,
            convergence_code=convergence_code,
            status=status,
            failure=failure,
            notes=list(notes or []),
            frames_path=self.frames_path,
            frames_jsonl_path=self.frames_jsonl_path,
            json_path=self.json_path,
        )
        atomic_write_text(self.json_path, record.model_dump_json(indent=2) + "\n")
        return record

    def abort(self) -> None:
        """异常路径下关闭句柄（已写入的帧保留）。"""
        if self._closed:
            return
        self._closed = True
        self._xyz.close()
        self._jsonl.close()


def trajectory_artifact(record: TrajectoryRecord) -> TrajectoryArtifact:
    return TrajectoryArtifact(
        trajectory_id=record.trajectory_id,
        component_id=record.component_id,
        status=record.status,
        engine=record.engine,
        iterations=record.iterations,
        frame_count=record.frame_count,
        json_path=record.json_path,
        frames_path=record.frames_path,
        frames_jsonl_path=record.frames_jsonl_path,
    )


def write_trajectory_manifest(root_dir: str, artifacts: list[TrajectoryArtifact]) -> str:
    """写轨迹清单：让"失败轨迹也被保留"可被下游与测试直接核对。"""
    path = os.path.join(root_dir, TRAJECTORY_MANIFEST_NAME)
    payload = {
        "count": len(artifacts),
        "trajectories": [a.model_dump(mode="json") for a in artifacts],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def read_trajectory(json_path: str) -> TrajectoryRecord:
    """读回一条轨迹的元数据（测试与下游复核用）。"""
    with open(json_path, encoding="utf-8") as handle:
        return TrajectoryRecord.model_validate(json.load(handle))


def read_frame_summaries(frames_jsonl_path: str) -> list[FrameSummary]:
    """读回全部逐迭代帧的标量记录。"""
    summaries: list[FrameSummary] = []
    with open(frames_jsonl_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                summaries.append(FrameSummary.model_validate(json.loads(line)))
    return summaries


def read_frame_positions(frames_path: str) -> list[list[list[float]]]:
    """读回 ``frames.xyz`` 中全部逐迭代帧的坐标。"""
    frames: list[list[list[float]]] = []
    with open(frames_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        count = int(lines[index].strip())
        positions = []
        for line in lines[index + 2: index + 2 + count]:
            parts = line.split()
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        if len(positions) != count:
            raise ValueError(
                f"{frames_path}: frame at line {index + 1} declares {count} atoms but has "
                f"{len(positions)} coordinate lines (truncated file?)"
            )
        frames.append(positions)
        index += 2 + count
    return frames


def read_xyz_atoms(path: str) -> list[tuple[str, list[float]]]:
    """读单帧 xyz 的 ``(元素, [x, y, z])`` 列表。

    行尾的附加注释（构建器写的稳定身份 tag）被忽略，只取前四个字段；坐标以文件里
    写下的精度原样返回（构建器写 8 位小数），因此不经 MOL block 的 4 位小数往返损失。
    """
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    if not lines:
        raise ValueError(f"{path}: empty xyz file")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(f"{path}: first line must be the atom count, got {lines[0]!r}") from exc
    if len(lines) < 2 + count:
        raise ValueError(
            f"{path}: declares {count} atoms but only {max(0, len(lines) - 2)} coordinate lines"
        )
    atoms: list[tuple[str, list[float]]] = []
    for line in lines[2: 2 + count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"{path}: malformed coordinate line {line!r}")
        atoms.append((parts[0], [float(parts[1]), float(parts[2]), float(parts[3])]))
    return atoms
