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
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Literal, Optional

from pydantic import BaseModel, Field

from cloudra.persistence.fs_utils import atomic_write_text

PATH_XYZ_NAME = "xtbpath.xyz"
TS_XYZ_NAME = "xtbpath_ts.xyz"
RUNS_DIR_NAME = "xtb_path_runs"
MAX_EVIDENCE_LINES = 20

# --- xtb 6.7.1 的逐字标记（精确比对，不做模糊匹配；本模块不含正则） ---
MARKER_NORMAL_TERMINATION = "normal termination of xtb"
MARKER_FINISHED_RUN = " * finished run on"
MARKER_PATH_FINDER = " path finder:"

#: 初猜来源标识（SOP §2：初猜是怎么来的必须写明，不许静默降级）。
PATH_KIND_XTB = "xtb_path"
PATH_KIND_IDPP = "idpp_fallback"

PathTermination = Literal[
    "completed",
    "executable_missing",
    "timeout",
    "invalid_endpoints",
    "incomplete_artifacts",
    "failed",
    "unknown_failure",
]


class XtbPathRequest(BaseModel):
    """一次 MTD 路径搜索的请求。"""

    reactant_xyz: str = Field(description="反应物几何（单帧 xyz 文本）")
    product_xyz: str = Field(description="产物几何（单帧 xyz 文本）；元素序列必须与反应物一致")
    output_dir: str = Field(description="持久运行目录的父目录；每次运行在其 xtb_path_runs/ 下新建")
    charge: int = Field(default=0, description="总电荷（--chrg）")
    multiplicity: int = Field(default=1, description="自旋多重度 2S+1，透传为 --uhf = multiplicity-1")
    timeout: int = Field(default=900, description="子进程超时（秒）；超时只终止本次运行自己的进程组")
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
    versions_path: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    path_xyz_path: str = ""
    ts_xyz_path: str = ""
    artifacts: list[XtbArtifact] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, description="命中的逐字标记行（原样保留）")
    diagnostics: list[str] = Field(default_factory=list)
    message: str = ""


def build_xtb_path_command(request: XtbPathRequest) -> list[str]:
    """构造命令行。电荷与自旋显式透传，绝不依赖引擎默认推断。"""
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")
    return [
        "xtb", "reactant.xyz", "--path", "product.xyz",
        "--chrg", str(request.charge), "--uhf", str(request.multiplicity - 1),
        *request.extra_args,
    ]


def _next_run_dir(output_dir: str, run_label: str) -> str:
    safe_label = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in run_label) or "run"
    runs_root = os.path.join(output_dir, RUNS_DIR_NAME)
    os.makedirs(runs_root, exist_ok=True)
    used = set()
    for name in os.listdir(runs_root):
        head, _, tail = name.rpartition("_")
        if head == safe_label and tail.isdigit():
            used.add(int(tail))
    index = 1
    while index in used:
        index += 1
    run_dir = os.path.join(runs_root, f"{safe_label}_{index:04d}")
    os.makedirs(run_dir, exist_ok=False)
    return run_dir


def _capture_versions() -> str:
    try:
        proc = subprocess.run(["xtb", "--version"], capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001 - 版本取不到不阻塞运行，如实记录
        return f"xtb --version failed: {type(exc).__name__}: {exc}\n"
    text = (proc.stdout or "") + (proc.stderr or "")
    lines = [line.strip() for line in text.splitlines() if "xtb version" in line]
    return "xtb --version (returncode=%d):\n%s\n" % (
        proc.returncode, "\n".join(f"    {line}" for line in (lines or ["<no version line found>"])),
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


def _list_artifacts(run_dir: str) -> list[XtbArtifact]:
    artifacts: list[XtbArtifact] = []
    for name in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, name)
        if os.path.isfile(path):
            artifacts.append(XtbArtifact(name=name, path=path, size_bytes=os.path.getsize(path)))
    return artifacts


def _scan_markers(lines: list[str]) -> tuple[list[str], bool, bool]:
    """精确 token 扫描：``(命中行, 是否正常终止, 是否跑了路径搜索)``。"""
    hits: list[str] = []
    normal = False
    path_finder = False
    for line in lines:
        stripped = line.strip()
        if MARKER_NORMAL_TERMINATION in stripped:
            hits.append(stripped)
            normal = True
        elif stripped.startswith(MARKER_FINISHED_RUN.strip()):
            hits.append(stripped)
        elif MARKER_PATH_FINDER.strip() in stripped:
            hits.append(stripped)
            path_finder = True
    return hits[:MAX_EVIDENCE_LINES], normal, path_finder


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
        run_dir = _next_run_dir(output_dir, request.run_label)
        return XtbPathResult(
            run_dir=run_dir, termination_reason="invalid_endpoints",
            message=f"the endpoints were rejected before starting xtb: {exc}",
            diagnostics=[str(exc)],
        )

    command = build_xtb_path_command(request)
    run_dir = _next_run_dir(request.output_dir, request.run_label)
    reactant_path = os.path.join(run_dir, "reactant.xyz")
    product_path = os.path.join(run_dir, "product.xyz")
    command_path = os.path.join(run_dir, "command.txt")
    versions_path = os.path.join(run_dir, "versions.txt")
    stdout_path = os.path.join(run_dir, "stdout.log")
    stderr_path = os.path.join(run_dir, "stderr.log")

    atomic_write_text(reactant_path, request.reactant_xyz)
    atomic_write_text(product_path, request.product_xyz)
    atomic_write_text(command_path, " ".join(command) + "\n")
    atomic_write_text(versions_path, _capture_versions())

    result = XtbPathResult(
        run_dir=run_dir, command=command, symbols=reactant_symbols,
        reactant_path=reactant_path, product_path=product_path,
        command_path=command_path, versions_path=versions_path,
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
        result.artifacts = _list_artifacts(run_dir)
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
        result.artifacts = _list_artifacts(run_dir)
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
        _terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        returncode = proc.returncode
        result.diagnostics.append(
            f"the xtb path search exceeded the {request.timeout}s timeout; this run's own process "
            "group was terminated (its logs and intermediate files are kept)"
        )

    atomic_write_text(stdout_path, stdout or "")
    atomic_write_text(stderr_path, stderr or "")
    result.returncode = returncode
    result.artifacts = _list_artifacts(run_dir)

    # 实测（本机 xtb 6.7.1）：``normal termination of xtb`` 落在 **stderr**，而计时块落在
    # stdout。因此标记必须在两个流上一起扫——只看 stdout 会把正常的运行判成失败。
    hits, normal, path_finder = _scan_markers(
        (stdout or "").splitlines() + (stderr or "").splitlines()
    )
    result.evidence = hits

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

    if not normal:
        result.termination_reason = "unknown_failure"
        result.diagnostics.append(
            f"xtb exited 0 but never printed its normal-termination marker "
            f"({MARKER_NORMAL_TERMINATION!r}, which this build writes to stderr); refusing to treat "
            "the exit code alone as success"
        )
        result.message = f"xtb did not report normal termination. Full log: {stdout_path}"
        return result

    if not path_finder:
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
    result.message = (
        f"xtb path search completed: {len(frames)} path frames and a TS candidate "
        f"({ts_energy:.6f} Eh). Run directory: {run_dir}"
    )
    return result


def _terminate_process_group(proc: subprocess.Popen) -> None:
    """先 SIGTERM 再 SIGKILL **本进程组**，并 wait/reap，绝不只发信号不回收。"""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        proc.wait()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue
    proc.wait()
