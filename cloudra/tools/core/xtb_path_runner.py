"""xTB MTD 路径搜索运行器：TS 初猜的便宜端（SOP `guess` 阶段）。

**事实核对（本机 xtb 6.7.1 实测，不是推断）**

- xTB **没有 NEB**。它有 ``--path [FILE]``：元动力学（MTD）路径搜索，从输入几何走到
  给定的产物几何。所以本模块叫 path 不叫 neb。
- 调用形式：``xtb reactant.xyz --path product.xyz``。**两个几何必需**，元素序列必须一致。
- 产出（持久运行目录里原地保留）：

  ====================  ==================================================
  文件                   内容
  ====================  ==================================================
  ``xtbpath.xyz``        路径的逐帧几何（含起点）。注释行 ``energy: X`` 是
                         **相对输入几何的能量，单位 kcal/mol**
  ``xtbpath_ts.xyz``     MTD 找到的 TS **候选**。注释行 ``energy: X`` 是
                         **绝对能量，单位 Eh**
  ``xtbopt.log``         产物侧预优化的轨迹
  ``xtbopt.xyz`` 等      引擎其余中间产物
  ====================  ==================================================

  **两个文件的注释行单位不同，这是最容易静默出错的地方**：实测
  ``xtbpath_ts.xyz`` 的 ``-4.987083865354`` 与单点 ``TOTAL ENERGY -4.987083865355 Eh``
  一致到 1e-12；而 ``xtbpath.xyz`` 里某帧注释 ``52.271`` 对应的真实能量差是
  ``-4.987083865354 − (−5.070383095108) = 0.083299 Eh = 52.272 kcal/mol``。
  因此本模块把两者**分别标注**（``rel_energy_kcal`` / ``ts_candidate_energy_eh``），
  绝不放进同一个字段。

**这个结果只是初猜**：``xtbpath_ts.xyz`` 是 MTD 采到的最高点附近结构，不是鞍点，
更不是"已验证"。验证仍归频率/IRC 判定。

**随机性**：MTD 是随机的，同一次输入重跑路径不同。因此结果按**采样**看待，命令与
stdout 全部落盘以备复查。

**路径精修必须跑到引擎自己判收敛**（本机 xtb 6.7.1 实测，逐字证据与可重跑脚本在
``docs/evidence/ts_guess_mtd_artifact/``）：xTB 的路径是**迭代精修**的，而它的内建上限只有
3 轮，3 轮后会打印 ``terminated because max. # cycles reached`` —— 那不是收敛，是**被截断**。
截断路径的最高帧落在反应物自己的盆地里（实测：最高帧离起点只有 21°，相对能 44.865 kcal/mol，
拿去做 ORCA ``OptTS`` 跑 56 轮不收敛、一路滑回极小值）。把上限放开后，同一个端点对在第 31 轮
由引擎自己判收敛（``terminated because grad at TS <threshold``），barrier 降到 18.299 kcal/mol，
最高帧落在扭转极大上，``OptTS`` 9 轮即收敛到一阶鞍点。因此本模块：

- **总是**写一份 ``$path`` 输入并把 ``nrun`` 上限显式传给引擎（内建默认 3 轮不能用）；
- 把这两句终止语**分开分类**：``converged`` / ``cycles_exhausted``；
- 触到上限一律报 ``path_not_converged`` 且 ``usable_as_guess=False``，绝不把截断路径当可用初猜。
"""

from __future__ import annotations

import os
import subprocess
from typing import Literal, Optional

from pydantic import BaseModel, Field

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.run_dirs import (
    capture_versions,
    list_artifact_files,
    next_run_dir,
    terminate_process_group,
)

PATH_XYZ_NAME = "xtbpath.xyz"
TS_XYZ_NAME = "xtbpath_ts.xyz"
RUNS_DIR_NAME = "xtb_path_runs"
#: 引擎逐迭代写下的中间帧命名（``xtbpath_1.xyz`` … ``xtbpath_N.xyz``）。只在引擎没走到收敛、
#: 没写出最终 ``xtbpath.xyz`` 时才存在——它们是**采样现场，不是初猜**（GH #39）。
PARTIAL_FRAME_PREFIX = "xtbpath_"
PARTIAL_FRAME_SUFFIX = ".xyz"
MAX_EVIDENCE_LINES = 20

# --- xtb 6.7.1 的逐字标记（精确比对，不做模糊匹配；本模块不含正则） ---
MARKER_NORMAL_TERMINATION = "normal termination of xtb"
MARKER_FINISHED_RUN = " * finished run on"
MARKER_PATH_FINDER = " path finder:"
#: 路径精修的两句终止语。前者是引擎判的收敛，后者是**触到轮数上限被截断**，二者绝不等价。
MARKER_PATH_CONVERGED = "terminated because grad at TS <threshold"
MARKER_PATH_CYCLES_EXHAUSTED = "terminated because max. # cycles reached"
#: 每轮精修打印的 barrier（第一列是空格对齐，逐字保留）
MARKER_FORWARD_BARRIER = "forward  barrier (kcal)"
MARKER_BACKWARD_BARRIER = "backward barrier (kcal)"

#: 路径精修的轮数上限（``$path nrun``）。这**不是**收敛判据，只是机时上限：收敛由引擎自己判
#: （见模块 docstring 的实测）。默认给足，让引擎跑到自己的收敛判据为止。
DEFAULT_REFINEMENT_RUNS = 100
#: ``$path`` 输入文件名（与命令行一起落盘备查）
PATH_INPUT_NAME = "path.inp"

#: 初猜来源标识（SOP §2：初猜是怎么来的必须写明，不许静默降级）。
PATH_KIND_XTB = "xtb_path"
PATH_KIND_IDPP = "idpp_fallback"

PathTermination = Literal[
    "completed",
    "executable_missing",
    "timeout",
    "invalid_endpoints",
    "incomplete_artifacts",
    "path_not_converged",
    "failed",
    "unknown_failure",
]

#: 引擎**确实启动过**的那些终止类别（子进程起来了、stdout 落盘、可能已有采样帧）：
#: "跑了但没产出可用初猜"与"根本没搜过"必须分开上报——GH #39 实测
#: ``incomplete_artifacts`` 时目录里已留下 ``xtbpath_1..24.xyz`` 可用采样，
#: 报成 ``not_attempted`` 会让上层误判"根本没搜"。``executable_missing`` 与
#: ``invalid_endpoints`` 都发生在子进程启动之前，不在本集合。
XTB_ENGINE_STARTED_TERMINATIONS: frozenset[str] = frozenset({
    "timeout",
    "failed",
    "unknown_failure",
    "incomplete_artifacts",
    "path_not_converged",
})

#: 引擎自己报的路径精修结局。``""`` = 日志里没有这两句终止语（本模块按未知处理，不默认成功）。
RefinementTermination = Literal["", "converged", "cycles_exhausted"]


class XtbPathRequest(BaseModel):
    """一次 MTD 路径搜索的请求。"""

    reactant_xyz: str = Field(description="反应物几何（单帧 xyz 文本）")
    product_xyz: str = Field(description="产物几何（单帧 xyz 文本）；元素序列必须与反应物一致")
    output_dir: str = Field(description="持久运行目录的父目录；每次运行在其 xtb_path_runs/ 下新建")
    charge: int = Field(default=0, description="总电荷（--chrg）")
    multiplicity: int = Field(default=1, description="自旋多重度 2S+1，透传为 --uhf = multiplicity-1")
    timeout: int | None = Field(default=900, description="子进程耗时上限（秒）；超时只终止本次运行自己的进程组")
    refinement_runs: int | None = Field(
        default=DEFAULT_REFINEMENT_RUNS, ge=1,
        description="路径精修的轮数上限（$path nrun）。**只是机时上限**：收敛由引擎自己判，"
                    "触到这个上限即报 path_not_converged。实测内建默认 3 轮远不够收敛，"
                    "不要把它调小",
    )
    run_label: str = Field(default="xtbpath", description="运行目录前缀")
    extra_args: list[str] = Field(default_factory=list, description="追加到命令行的原生选项")


class XtbArtifact(BaseModel):
    name: str
    path: str
    size_bytes: int


class PathFrame(BaseModel):
    """路径上的一帧。"""

    frame_index: int
    rel_energy_kcal: Optional[float] = Field(
        default=None,
        description="文件注释里的能量，单位**已核实为 kcal/mol**，相对输入几何；取不到时为 None",
    )
    positions: list[list[float]]


class XtbPathResult(BaseModel):
    """路径搜索结果。进程退出与"能不能用来当初猜"分开表达。"""

    run_dir: str
    command: list[str] = Field(default_factory=list)
    returncode: Optional[int] = None
    path_kind: Literal["xtb_path"] = PATH_KIND_XTB
    termination_reason: PathTermination = "unknown_failure"
    refinement_runs: int | None = Field(default=0, description="本次传给引擎的路径精修轮数上限")
    refinement_termination: RefinementTermination = Field(
        default="",
        description="引擎自己报的精修结局：converged（引擎判收敛）/ cycles_exhausted（触顶截断）",
    )
    usable_as_guess: bool = Field(
        default=False,
        description="是否产出了可用的初猜（路径 + TS 候选齐全且几何自洽）。"
                    "**这不等于已验证**：初猜仍需频率/IRC 判定",
    )
    symbols: list[str] = Field(default_factory=list)
    frames: list[PathFrame] = Field(default_factory=list)
    ts_candidate_energy_eh: Optional[float] = Field(
        default=None, description="TS 候选的**绝对**能量（Eh）；与路径帧的相对 kcal/mol 不是一个字段"
    )
    ts_candidate_positions: list[list[float]] = Field(default_factory=list)
    reactant_path: str = ""
    product_path: str = ""
    command_path: str = ""
    path_input_path: str = ""
    versions_path: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    path_xyz_path: str = ""
    ts_xyz_path: str = ""
    artifacts: list[XtbArtifact] = Field(default_factory=list)
    partial_frames: list[str] = Field(
        default_factory=list,
        description="引擎异常退出时留下的逐迭代中间帧（xtbpath_<n>.xyz）。**不是初猜**——"
                    "只做可发现性：让上层知道有一批采样可自行检视（GH #39）",
    )
    evidence: list[str] = Field(default_factory=list, description="命中的逐字标记行（原样保留）")
    diagnostics: list[str] = Field(default_factory=list)
    message: str = ""


def build_path_input(refinement_runs: int | None) -> str:
    """``$path`` 输入块：把精修轮数上限显式交给引擎，**不使用内建默认 3 轮**。

    本机 6.7.1 实测：``$path`` 块被读取；它认得的键是 ``nrun`` / ``npoint`` / ``kpush`` /
    ``kpull``，其余（``npoints`` / ``alpha`` / ``step`` / ``time`` / ``seed`` 等）会被逐字拒掉
    （``the key '...' is not recognized by path``），因此这里只写实测可用的键。
    """
    if refinement_runs is None:
        return "$path\n$end\n"
    if refinement_runs < 1:
        raise ValueError(f"refinement_runs must be >= 1, got {refinement_runs}")
    return f"$path\n   nrun={refinement_runs}\n$end\n"


def build_xtb_path_command(request: XtbPathRequest) -> list[str]:
    """构造命令行。电荷与自旋显式透传，绝不依赖引擎默认推断。"""
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")
    return [
        "xtb", "reactant.xyz", "--path", "product.xyz", "--input", PATH_INPUT_NAME,
        "--chrg", str(request.charge), "--uhf", str(request.multiplicity - 1),
        *request.extra_args,
    ]


def list_partial_frames(run_dir: str) -> list[str]:
    """列出引擎留下的逐迭代中间帧（``xtbpath_<n>.xyz``），按序号升序。

    显式 token 扫描（前缀 + 纯数字 + 后缀），不用正则——``xtbpath_ts.xyz``（TS 候选）与
    ``xtbpath.xyz``（最终路径）因此天然被排除。
    """
    if not os.path.isdir(run_dir):
        return []
    found: list[tuple[int, str]] = []
    for name in os.listdir(run_dir):
        if not (name.startswith(PARTIAL_FRAME_PREFIX) and name.endswith(PARTIAL_FRAME_SUFFIX)):
            continue
        middle = name[len(PARTIAL_FRAME_PREFIX):-len(PARTIAL_FRAME_SUFFIX)]
        if not middle.isdigit():
            continue
        found.append((int(middle), os.path.join(run_dir, name)))
    found.sort()
    return [path for _, path in found]


def _record_partial_frames(result: XtbPathResult) -> None:
    """把中间帧写进结果与诊断。**只做可发现性**：不作初猜（GH #39）。

    崩溃退出的中间帧比"迭代到上限的截断路径"更可疑（引擎是异常退出的），因此不能放宽
    ``usable_as_guess``；但它们必须能被上层看见——否则连"这里有一批采样"都不知道。
    """
    result.partial_frames = list_partial_frames(result.run_dir)
    if result.partial_frames:
        result.diagnostics.append(
            f"{len(result.partial_frames)} partial iteration frame(s) were left behind "
            f"(first: {os.path.basename(result.partial_frames[0])}); they are sampling "
            f"artifacts, not a usable TS guess"
        )


def _symbols_and_positions(xyz_text: str, *, label: str) -> tuple[list[str], list[list[float]]]:
    """解析单帧 xyz；不完整即 fail-loud。"""
    lines = xyz_text.splitlines()
    if not lines:
        raise ValueError(f"{label}: empty xyz text")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(f"{label}: first line must be the atom count, got {lines[0]!r}") from exc
    if count < 1:
        raise ValueError(f"{label}: declares {count} atoms")
    if len(lines) < 2 + count:
        raise ValueError(f"{label}: declares {count} atoms but has too few lines")
    symbols: list[str] = []
    positions: list[list[float]] = []
    for line in lines[2: 2 + count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"{label}: malformed coordinate line {line!r}")
        symbols.append(parts[0])
        positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return symbols, positions


def _parse_path_frames(path: str) -> list[PathFrame]:
    """解析 ``xtbpath.xyz``。注释里的能量是**相对 kcal/mol**，取不到就留 None，不猜。"""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    frames: list[PathFrame] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        try:
            count = int(lines[index].strip())
        except ValueError:
            break
        comment = lines[index + 1] if index + 1 < len(lines) else ""
        rel: Optional[float] = None
        tokens = comment.split()
        # 形如 ``energy: <float> xtb: <version>``；逐 token 取，不做模糊匹配
        if len(tokens) >= 2 and tokens[0] == "energy:":
            try:
                rel = float(tokens[1])
            except ValueError:
                rel = None
        block = lines[index + 2: index + 2 + count]
        if len(block) != count:
            break
        positions = []
        for line in block:
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"{path}: malformed coordinate line {line!r}")
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        frames.append(PathFrame(frame_index=len(frames), rel_energy_kcal=rel, positions=positions))
        index += 2 + count
    if not frames:
        raise ValueError(f"{path}: no complete frame could be read")
    return frames


def _parse_ts_candidate(path: str) -> tuple[float, list[list[float]]]:
    """解析 ``xtbpath_ts.xyz``。注释里的能量是**绝对 Eh**——与路径帧的单位不同。"""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    if len(lines) < 3:
        raise ValueError(f"{path}: too few lines for a single frame")
    count = int(lines[0].strip())
    tokens = lines[1].split()
    if len(tokens) < 2 or tokens[0] != "energy:":
        raise ValueError(
            f"{path}: comment line must start with 'energy: <Eh>', got {lines[1]!r}"
        )
    energy = float(tokens[1])
    block = lines[2: 2 + count]
    if len(block) != count:
        raise ValueError(f"{path}: declares {count} atoms but only {len(block)} coordinates follow")
    positions = []
    for line in block:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"{path}: malformed coordinate line {line!r}")
        positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return energy, positions


class PathMarkers(BaseModel):
    """日志里命中的逐字标记。"""

    evidence: list[str] = Field(default_factory=list)
    normal_termination: bool = False
    path_finder: bool = False
    refinement_termination: RefinementTermination = ""


def _scan_markers(lines: list[str]) -> PathMarkers:
    """精确 token 扫描。两条终止语**分开**判定：收敛与触顶绝不等价。

    barrier 行每轮精修都打印一次，只保留**最后一次**（更靠后的那个才是当前精修程度）。
    """
    markers = PathMarkers()
    last_forward = ""
    last_backward = ""
    for line in lines:
        stripped = line.strip()
        if MARKER_NORMAL_TERMINATION in stripped:
            markers.evidence.append(stripped)
            markers.normal_termination = True
        elif stripped.startswith(MARKER_FINISHED_RUN.strip()):
            markers.evidence.append(stripped)
        elif MARKER_PATH_FINDER.strip() in stripped:
            markers.evidence.append(stripped)
            markers.path_finder = True
        elif MARKER_PATH_CONVERGED in stripped:
            markers.evidence.append(stripped)
            markers.refinement_termination = "converged"
        elif MARKER_PATH_CYCLES_EXHAUSTED in stripped:
            markers.evidence.append(stripped)
            markers.refinement_termination = "cycles_exhausted"
        elif MARKER_FORWARD_BARRIER in stripped:
            last_forward = stripped
        elif MARKER_BACKWARD_BARRIER in stripped:
            last_backward = stripped
    for extra in (last_forward, last_backward):
        if extra:
            markers.evidence.append(extra)
    markers.evidence = markers.evidence[:MAX_EVIDENCE_LINES]
    return markers


def run_xtb_path(request: XtbPathRequest) -> XtbPathResult:
    """在持久运行目录里跑一次 MTD 路径搜索。

    同步函数（子进程 + 文件 IO）；异步调用方必须经 ``asyncio.to_thread`` 卸载。
    """
    try:
        reactant_symbols, _ = _symbols_and_positions(request.reactant_xyz, label="reactant")
        product_symbols, _ = _symbols_and_positions(request.product_xyz, label="product")
    except ValueError as exc:
        # 端点先自检：几何不完整或元素序列不一致时，跑引擎只会浪费机时
        output_dir = request.output_dir
        os.makedirs(output_dir, exist_ok=True)
        run_dir = next_run_dir(output_dir, RUNS_DIR_NAME, request.run_label)
        return XtbPathResult(
            run_dir=run_dir, termination_reason="invalid_endpoints",
            message=f"the endpoints were rejected before starting xtb: {exc}",
            diagnostics=[str(exc)],
        )

    command = build_xtb_path_command(request)
    run_dir = next_run_dir(request.output_dir, RUNS_DIR_NAME, request.run_label)
    reactant_path = os.path.join(run_dir, "reactant.xyz")
    product_path = os.path.join(run_dir, "product.xyz")
    command_path = os.path.join(run_dir, "command.txt")
    path_input_path = os.path.join(run_dir, PATH_INPUT_NAME)
    versions_path = os.path.join(run_dir, "versions.txt")
    stdout_path = os.path.join(run_dir, "stdout.log")
    stderr_path = os.path.join(run_dir, "stderr.log")

    atomic_write_text(reactant_path, request.reactant_xyz)
    atomic_write_text(product_path, request.product_xyz)
    atomic_write_text(command_path, " ".join(command) + "\n")
    atomic_write_text(path_input_path, build_path_input(request.refinement_runs))
    atomic_write_text(versions_path, capture_versions(("xtb",), ("xtb version",)))

    result = XtbPathResult(
        run_dir=run_dir, command=command, symbols=reactant_symbols,
        reactant_path=reactant_path, product_path=product_path,
        command_path=command_path, path_input_path=path_input_path, versions_path=versions_path,
        refinement_runs=request.refinement_runs,
        stdout_path=stdout_path, stderr_path=stderr_path,
        path_xyz_path=os.path.join(run_dir, PATH_XYZ_NAME),
        ts_xyz_path=os.path.join(run_dir, TS_XYZ_NAME),
    )

    if reactant_symbols != product_symbols:
        result.termination_reason = "invalid_endpoints"
        result.diagnostics.append(
            f"reactant and product element sequences differ ({reactant_symbols} vs "
            f"{product_symbols}); the path search needs one consistent atom set"
        )
        result.message = "Endpoints rejected: the element sequences differ."
        result.artifacts = [
            XtbArtifact(name=name, path=path, size_bytes=size)
            for name, path, size in list_artifact_files(run_dir)
        ]
        return result

    import shutil

    if not shutil.which("xtb"):
        result.termination_reason = "executable_missing"
        result.diagnostics.append(
            "the 'xtb' executable was not found on PATH; no run was started. The caller should "
            f"fall back to IDPP interpolation and report path_kind={PATH_KIND_IDPP!r}"
        )
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        result.artifacts = [
            XtbArtifact(name=name, path=path, size_bytes=size)
            for name, path, size in list_artifact_files(run_dir)
        ]
        result.message = "xtb executable not found; no path search was started."
        return result

    timed_out = False
    proc = subprocess.Popen(
        command, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=request.timeout)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        returncode = proc.returncode
        result.diagnostics.append(
            f"the xtb path search exceeded the {request.timeout}s timeout; this run's own process "
            "group was terminated (its logs and intermediate files are kept)"
        )

    atomic_write_text(stdout_path, stdout or "")
    atomic_write_text(stderr_path, stderr or "")
    result.returncode = returncode
    result.artifacts = [
        XtbArtifact(name=name, path=path, size_bytes=size)
        for name, path, size in list_artifact_files(run_dir)
    ]

    # 实测（本机 xtb 6.7.1）：``normal termination of xtb`` 落在 **stderr**，而计时块落在
    # stdout。因此标记必须在两个流上一起扫——只看 stdout 会把正常的运行判成失败。
    markers = _scan_markers(
        (stdout or "").splitlines() + (stderr or "").splitlines()
    )
    result.evidence = markers.evidence
    result.refinement_termination = markers.refinement_termination

    if timed_out:
        result.termination_reason = "timeout"
        result.message = (
            f"the xtb path search timed out after {request.timeout}s (returncode={returncode}). "
            f"Full log: {stdout_path}"
        )
        return result

    if returncode != 0:
        result.termination_reason = "failed"
        tail = "\n".join((stdout or "").splitlines()[-15:]) or (stderr or "")[-2000:]
        result.diagnostics.append(
            "xtb exited non-zero; raw log tail follows (no cause is guessed)"
        )
        result.diagnostics.append(tail)
        result.message = (
            f"the xtb path search failed (returncode={returncode}). Full log: {stdout_path}"
        )
        return result

    if not markers.normal_termination:
        result.termination_reason = "unknown_failure"
        result.diagnostics.append(
            f"xtb exited 0 but never printed its normal-termination marker "
            f"({MARKER_NORMAL_TERMINATION!r}, which this build writes to stderr); refusing to treat "
            "the exit code alone as success"
        )
        result.message = f"xtb did not report normal termination. Full log: {stdout_path}"
        return result

    if not markers.path_finder:
        result.termination_reason = "unknown_failure"
        result.diagnostics.append(
            f"xtb exited 0 but never printed its path-finder timing block "
            f"({MARKER_PATH_FINDER.strip()!r}); refusing to treat the exit code alone as success"
        )
        result.message = f"xtb did not report a completed path search. Full log: {stdout_path}"
        return result

    # 产物完整性：路径与 TS 候选都要在，且几何自洽——"文件在"不构成成功判据
    try:
        frames = _parse_path_frames(result.path_xyz_path)
        ts_energy, ts_positions = _parse_ts_candidate(result.ts_xyz_path)
    except (OSError, ValueError) as exc:
        result.termination_reason = "incomplete_artifacts"
        result.diagnostics.append(f"path artifacts are unusable: {exc}")
        _record_partial_frames(result)
        result.message = (
            f"xtb reported normal termination but its path artifacts are unusable ({exc}). "
            f"Full log: {stdout_path}"
        )
        return result

    for frame in frames:
        if len(frame.positions) != len(reactant_symbols):
            result.termination_reason = "incomplete_artifacts"
            result.diagnostics.append(
                f"frame {frame.frame_index} has {len(frame.positions)} atoms but the endpoints have "
                f"{len(reactant_symbols)}"
            )
            result.message = "xtb reported normal termination but the path frames are inconsistent."
            return result
    if len(frames) < 2:
        result.termination_reason = "incomplete_artifacts"
        result.diagnostics.append(
            f"the path has only {len(frames)} frame(s); a path needs at least the two endpoints"
        )
        result.message = "xtb reported normal termination but produced no usable path."
        return result
    if len(ts_positions) != len(reactant_symbols):
        result.termination_reason = "incomplete_artifacts"
        result.diagnostics.append(
            f"the TS candidate has {len(ts_positions)} atoms but the endpoints have "
            f"{len(reactant_symbols)}"
        )
        result.message = "xtb reported normal termination but the TS candidate is inconsistent."
        return result

    result.frames = frames
    result.ts_candidate_energy_eh = ts_energy
    result.ts_candidate_positions = ts_positions

    if markers.refinement_termination == "cycles_exhausted":
        # **被截断的路径不是初猜**：实测这种路径的最高帧落在反应物自己的盆地里
        # （离起点只有 21°、相对能 44.865 kcal/mol，做 OptTS 跑 56 轮不收敛）。
        # 这里把截断的现场（路径帧 + TS 候选）保留下来供复查，但明确标成不可用。
        result.termination_reason = "path_not_converged"
        result.usable_as_guess = False
        result.diagnostics.append(
            f"the engine stopped its path refinement at the {request.refinement_runs}-run cap "
            f"({MARKER_PATH_CYCLES_EXHAUSTED!r}); that is a truncated path, not a converged one. "
            "The frames and TS candidate are kept for inspection only. Measured consequence of "
            "accepting a truncated path (docs/evidence/ts_guess_mtd_artifact/): its highest frame "
            "sits in the reactant's own basin, 21 deg from the start, and an ORCA OptTS started "
            "from it never converged (56 cycles, slid back to the minimum). Raise "
            "`refinement_runs` and rerun"
        )
        result.message = (
            f"the xTB path refinement hit its {request.refinement_runs}-run cap before the engine "
            f"declared convergence, so no usable TS guess was produced. Raise `refinement_runs` and "
            f"rerun. Run directory (truncated path kept for inspection): {run_dir}"
        )
        return result

    if markers.refinement_termination != "converged":
        result.termination_reason = "unknown_failure"
        result.usable_as_guess = False
        result.diagnostics.append(
            "xtb exited 0 and produced path artifacts, but its log carries neither refinement "
            f"termination line ({MARKER_PATH_CONVERGED!r} / {MARKER_PATH_CYCLES_EXHAUSTED!r}); "
            "whether the path refinement converged cannot be established from this output, and a "
            "non-converged path must not be handed over as a TS guess"
        )
        result.message = (
            f"the xTB path search reported no path-refinement termination line, so convergence "
            f"could not be confirmed. Full log: {stdout_path}"
        )
        return result

    result.termination_reason = "completed"
    result.usable_as_guess = True
    result.diagnostics.append(
        "path-frame comment energies are RELATIVE kcal/mol; the TS candidate's comment energy is "
        "ABSOLUTE Eh — the two are reported in separate fields on purpose "
        "(verified against single points on this machine)"
    )
    result.diagnostics.append(
        "the TS candidate is a guess sampled by metadynamics, NOT a saddle point and NOT verified; "
        "frequency/IRC judgement still has to run"
    )
    result.diagnostics.append(
        f"the engine declared the path refinement converged ({MARKER_PATH_CONVERGED!r}) within the "
        f"{request.refinement_runs}-run cap"
    )
    result.message = (
        f"xtb path search completed: {len(frames)} path frames and a TS candidate "
        f"({ts_energy:.6f} Eh). Run directory: {run_dir}"
    )
    return result
