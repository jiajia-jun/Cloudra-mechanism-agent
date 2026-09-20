"""CREST 运行器：持久化运行现场 + 分层失败分类（issue #33 / Task 3）。

修复的两个缺陷：

1. **现场被删除**：``conformer_search`` 过去用 ``tempfile.TemporaryDirectory`` 跑 CREST，
   函数退出即删；失败时只剩一段截断的 stdout 尾巴，"同一合法种子为何失败"无法复查。
   本模块改为在 ``<output_dir>/crest_runs/<label>_<NNNN>/`` 下**持久**运行，CREST 直接以
   该目录为工作目录，因此它写出的 ``xtb.out`` / ``xtbopt.log`` / ``crest_conformers.xyz`` /
   ``NOT_CONVERGED`` 等中间现场全部原地保留；另外单独落 ``command.txt`` / ``input.xyz`` /
   ``versions.txt`` / ``stdout.log`` / ``stderr.log``。

2. **成功判定只看产物存在**：现在把"进程退出"与"科学成功"分开表达——
   ``returncode`` / ``termination_reason`` / ``scientific_success`` 三个独立字段。
   ``returncode != 0`` 一律 ``scientific_success=False``，**即使**磁盘上留着部分
   ``crest_conformers.xyz``；这类部分产物只作为证据登记，绝不进入构象排序。

失败分类用**精确整行/token 比对**（本模块不含正则）。标记取自本机 CREST 2.12 二进制的
选项表与提示文本，并经 tests/fixtures/chemtool_issue33/ 的真实运行验证：

===========================  ==========================================================
类别                          逐字标记
===========================  ==========================================================
初始优化失败                   ``Initial geometry optimization failed!``
初始拓扑变化                   ``WARNING! Change in topology detected!``
搜索阶段失败                   ``Trial MTD ``+``did not converge!`` / ``Warning: MD
                              seemingly failed (no xtb.trj)`` / ``Automatic xtb
                              restart failed ``
正常完成                       ``CREST terminated normally.``
===========================  ==========================================================

未命中任何已知标记的非零退出落 ``unknown_failure``：保留完整原文（日志路径）并明确报错，
不猜测原因、不按"产物在就成功"放行。

除默认构象搜索外支持 CREST 2.12 的特殊 runtype（``runtype`` 字段）：``nci``（非共价复合物
系综，椭球壁势）、``qcg``（quantum cluster growth 显式溶剂壳，需 xtb-IFF——缺失有专属终止
类别 ``qcg_xtbiff_missing``，fail-loud 不猜）、``protonate``/``deprotonate``/``tautomerize``
（质子化态/互变异构筛选）。各 runtype 的产物集合文件名与产物原子数不同（CREST 2.12 实测：
``protonated.xyz`` 为输入+1 原子、``deprotonated.xyz`` 为 -1、``tautomers.xyz`` 原子数不变、
qcg 主产物 ``ensemble/final_ensemble.xyz`` 为 溶质+nsolv×溶剂 原子），完整性核对按 runtype
各自的口径执行，不匹配即 ``incomplete_artifacts``，绝不放宽。
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
from cloudra.tools.core.topology_change import (
    TopologyChangeReport,
    compare_topology,
    read_last_xtbopt_frame,
    read_xyz_frame,
)

# --- CREST 2.12 的逐字标记（精确比对，不做模糊匹配） ---
MARKER_INITIAL_OPT_FAILED = "Initial geometry optimization failed!"
MARKER_INITIAL_TOPOLOGY_CHANGE = "WARNING! Change in topology detected!"
MARKER_TOPOLOGY_CHANGE_DETAIL = "The topology change was seen in the initial geometry optimization."
MARKER_NORMAL_TERMINATION = "CREST terminated normally."
MARKER_ABNORMAL_TERMINATION = "abnormal termination of crest"
MARKER_MTD_TRIAL_PREFIX = "Trial MTD "
MARKER_MTD_TRIAL_SUFFIX = "did not converge!"
MARKER_MD_FAILED = "Warning: MD seemingly failed (no xtb.trj)"
MARKER_RESTART_FAILED_PREFIX = "Automatic xtb restart failed "
#: QCG 缺 xtb-IFF 时的 ERROR STOP 文本（CREST 2.12 实测）。
MARKER_QCG_NO_IFF = "No xtb-IFF found"
#: CREST 在初始优化失败时写出的哨兵文件（空文件）；作为标记的旁证，不单独作为判据。
SENTINEL_NOT_CONVERGED = "NOT_CONVERGED"

CONFORMERS_NAME = "crest_conformers.xyz"
#: xTB 初始优化轨迹（CREST 在运行目录里留下）；末帧即初始优化后的几何。
XTBOPT_LOG_NAME = "xtbopt.log"
RUNS_DIR_NAME = "crest_runs"
MAX_EVIDENCE_LINES = 20

CrestRuntype = Literal["default", "nci", "qcg", "protonate", "deprotonate", "tautomerize"]

#: 各 runtype 的产物集合文件（CREST 2.12 实测 + 二进制字符串核实；qcg 主产物在子目录，
#: 其 ``grow/cluster.xyz`` 只是生长终态的单体几何，不构成系综产物）。
RUNTYPE_PRODUCT = {
    "default": CONFORMERS_NAME,
    "nci": CONFORMERS_NAME,
    "qcg": os.path.join("ensemble", "final_ensemble.xyz"),
    "protonate": "protonated.xyz",
    "deprotonate": "deprotonated.xyz",
    "tautomerize": "tautomers.xyz",
}

#: 产物相对输入的原子数变化（CREST 2.12 实测；qcg 由调用方按 nsolv×溶剂原子数另算）。
RUNTYPE_ATOM_DELTA = {"protonate": 1, "deprotonate": -1}

CrestTermination = Literal[
    "completed",
    "initial_optimization_failed",
    "initial_topology_change",
    "search_failed",
    "timeout",
    "incomplete_artifacts",
    "unknown_failure",
    "executable_missing",
    "qcg_xtbiff_missing",
]

CrestStage = Literal[
    "not_started",
    "initial_optimization",
    "search",
    "cregen",
    "artifact_check",
    "done",
]


class CrestRunRequest(BaseModel):
    """一次 CREST 运行的请求。输入坐标必须已由共享结构构建器产出可用几何。"""

    xyz_text: str = Field(description="CREST 输入 xyz 文本（单帧）")
    output_dir: str = Field(description="持久运行目录的父目录；每次运行在其 crest_runs/ 下新建")
    charge: int = Field(default=0, description="总电荷（--chrg）")
    multiplicity: int = Field(default=1, description="自旋多重度 2S+1，透传为 --uhf = multiplicity-1")
    timeout: int = Field(default=600, description="子进程超时（秒）；超时后终止本次运行自己的进程组")
    method: str = Field(default="gfn2", description="GFN 方法，如 gfn2 / gfn1 / gfnff")
    quick: bool = Field(default=True, description="是否加 --quick（缩减设置的粗筛搜索）")
    extra_args: list[str] = Field(default_factory=list, description="追加到命令行的原生选项")
    run_label: str = Field(default="run", description="运行目录前缀，便于按用途区分")
    noreftopo: bool = Field(
        default=False,
        description="加 ``--noreftopo``：只关闭**搜索前的初始拓扑检查**（用户批准：多碎片输入默认开启）。"
                    "刻意**不**同时加 ``-notopo``——那是关闭 CREGEN 的全部拓扑检查，会连搜索过程中的"
                    "结构身份检查一起去掉，本模块不提供该组合。开启时运行结果里会显式记录这个事实。",
    )
    runtype: CrestRuntype = Field(
        default="default",
        description="CREST 运行类型：default/nci 为构象系综搜索（nci 加椭球壁势，非共价复合物专用）；"
                    "qcg 为 quantum cluster growth 显式溶剂壳生长（需 solvent_xyz_text 与 nsolv，"
                    "且依赖外部 xtb-IFF）；protonate/deprotonate/tautomerize 为质子化态/互变异构筛选。",
    )
    solvent_xyz_text: str = Field(
        default="", description="runtype='qcg' 的溶剂分子 xyz 文本（单帧）；其余 runtype 必须为空",
    )
    nsolv: int = Field(default=0, description="runtype='qcg' 要生长的溶剂分子数（--nsolv）")
    expected_product_xyz: str = Field(
        default="",
        description="可选的预期产物单帧 xyz 文本。给出时，拓扑变更报告会额外汇总优化末帧的"
                    "连接表是否与它一致（仍是**对比事实**，不是「该变化被允许」的判定）",
    )
    expected_atoms: Optional[int] = Field(
        default=None,
        description="产物完整性核对用的原子数；None 时从输入 xyz 首行推断（推断失败即报错）",
    )


class CrestArtifact(BaseModel):
    """运行目录里的一个文件。"""

    name: str
    path: str
    size_bytes: int


class CrestConformer(BaseModel):
    """一条 CREST 构象（能量 + 坐标）。仅在 ``scientific_success`` 时产出。"""

    frame_index: int
    energy_eh: float
    positions: list[list[float]]
    symbols: list[str] = Field(
        default_factory=list,
        description="该帧的元素序列。protonate/qcg 等 runtype 的产物原子集合与输入不同，"
                    "调用方必须用这里的元素序列而不是输入的；default/nci 与输入一致",
    )


class CrestRunResult(BaseModel):
    """运行结果：进程退出与科学成功分开表达。"""

    run_dir: str
    command: list[str] = Field(default_factory=list)
    returncode: Optional[int] = None
    stage: CrestStage = "not_started"
    termination_reason: CrestTermination = "unknown_failure"
    scientific_success: bool = False
    conformers: list[CrestConformer] = Field(default_factory=list)
    conformer_count: int = 0
    artifacts: list[CrestArtifact] = Field(default_factory=list)
    input_path: str = ""
    command_path: str = ""
    versions_path: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    conformers_path: str = ""
    topology_change: Optional[TopologyChangeReport] = Field(
        default=None,
        description="变化前（交给 CREST 的输入）与变化后（CREST 留下的 xtbopt.log 末帧）的"
                    "连接表差异，逐条标注片内/片间。只在能读到优化末帧时给出；只记录不判定。",
    )
    evidence: list[str] = Field(default_factory=list, description="命中的逐字标记行（原样保留）")
    diagnostics: list[str] = Field(default_factory=list)
    message: str = ""


def build_crest_command(request: CrestRunRequest) -> list[str]:
    """构造 CREST 命令行。

    电荷与自旋**显式**透传（``--uhf = multiplicity - 1``，与 xtb 通道口径一致），
    绝不依赖 CREST 对带电/开壳层体系的默认推断。qcg 的溶剂文件与 nsolv 是位置性要件，
    缺失即在这里 fail-loud，不留到 CREST 报错。
    """
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")
    method = f"-{request.method.lstrip('-')}"
    if request.runtype == "qcg":
        if not request.solvent_xyz_text.strip():
            raise ValueError("runtype='qcg' requires solvent_xyz_text (the solvent molecule xyz)")
        if request.nsolv < 1:
            raise ValueError(f"runtype='qcg' requires nsolv >= 1, got {request.nsolv}")
        command = ["crest", "input.xyz", "--qcg", "solvent.xyz", "--nsolv", str(request.nsolv), method]
    else:
        if request.solvent_xyz_text.strip() or request.nsolv:
            raise ValueError("solvent_xyz_text/nsolv are only valid with runtype='qcg'")
        command = ["crest", "input.xyz", method]
    if request.quick and request.runtype in ("default", "nci"):
        command.append("--quick")
    command += ["--chrg", str(request.charge), "--uhf", str(request.multiplicity - 1)]
    if request.runtype == "nci":
        command.append("--nci")
    elif request.runtype in ("protonate", "deprotonate", "tautomerize"):
        command.append(f"--{request.runtype}")
    if request.noreftopo:
        # 只关初始拓扑检查；绝不同时加 -notopo（那会关掉 CREGEN 的全部拓扑检查）
        command.append("--noreftopo")
    command += list(request.extra_args)
    return command


def _scan_markers(lines: list[str]) -> tuple[list[str], Optional[CrestTermination], CrestStage]:
    """精确整行/token 扫描标记，返回 ``(命中行, 终止类别或 None, 阶段)``。

    用 ``in``/``startswith`` 做整行包含判定而不是模糊匹配：标记是 CREST 打印的固定文本，
    命中即原样保留该行，未知文本一律不猜。
    """
    hits: list[str] = []
    termination: Optional[CrestTermination] = None
    stage: CrestStage = "not_started"

    def note(line: str) -> None:
        if len(hits) < MAX_EVIDENCE_LINES:
            hits.append(line)

    for line in lines:
        stripped = line.strip()
        if MARKER_INITIAL_OPT_FAILED in stripped:
            note(stripped)
            # 初始优化失败优先于拓扑变化：它发生得更早，且拓扑检查根本没跑到
            if termination != "initial_optimization_failed":
                termination = "initial_optimization_failed"
                stage = "initial_optimization"
        elif MARKER_INITIAL_TOPOLOGY_CHANGE in stripped or MARKER_TOPOLOGY_CHANGE_DETAIL in stripped:
            note(stripped)
            if termination is None:
                termination = "initial_topology_change"
                stage = "initial_optimization"
        elif (
            (MARKER_MTD_TRIAL_PREFIX in stripped and MARKER_MTD_TRIAL_SUFFIX in stripped)
            or MARKER_MD_FAILED in stripped
            or MARKER_RESTART_FAILED_PREFIX in stripped
        ):
            note(stripped)
            if termination is None:
                termination = "search_failed"
                stage = "search"
        elif MARKER_ABNORMAL_TERMINATION in stripped:
            note(stripped)
        elif MARKER_QCG_NO_IFF in stripped:
            note(stripped)
            if termination is None:
                termination = "qcg_xtbiff_missing"
        elif MARKER_NORMAL_TERMINATION in stripped:
            note(stripped)
            if termination is None:
                termination = "completed"
                stage = "done"
    return hits, termination, stage


def _parse_conformers(path: str, expected_atoms: int) -> tuple[list[CrestConformer], Optional[str]]:
    """解析 ``crest_conformers.xyz``；返回 ``(构象, 失败原因或 None)``。

    注释行就是 Hartree 能量本身（CREST 2.12 实测：``        -11.39433938``），
    因此直接对整个注释行做浮点解析，不从中"搜数字"。任何不完整帧都判失败，不静默丢帧。
    """
    if not os.path.isfile(path):
        return [], "missing"
    if os.path.getsize(path) == 0:
        return [], "empty"
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    conformers: list[CrestConformer] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        try:
            count = int(lines[index].strip())
        except ValueError:
            return [], f"unparsable atom count at line {index + 1}: {lines[index]!r}"
        if count != expected_atoms:
            return [], (
                f"frame {len(conformers) + 1} declares {count} atoms but the input has "
                f"{expected_atoms} (truncated or mixed-ensemble output)"
            )
        if index + 1 >= len(lines):
            return [], f"frame {len(conformers) + 1} has no energy comment line (truncated)"
        comment = lines[index + 1].strip()
        try:
            energy = float(comment)
        except ValueError:
            return [], f"frame {len(conformers) + 1} energy line is not a number: {comment!r}"
        block = lines[index + 2: index + 2 + count]
        if len(block) != count:
            return [], (
                f"frame {len(conformers) + 1} declares {count} atoms but only {len(block)} "
                "coordinate lines follow (truncated)"
            )
        positions: list[list[float]] = []
        symbols: list[str] = []
        for line in block:
            parts = line.split()
            if len(parts) < 4:
                return [], f"malformed coordinate line in frame {len(conformers) + 1}: {line!r}"
            try:
                positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
            except ValueError:
                return [], f"non-numeric coordinate in frame {len(conformers) + 1}: {line!r}"
            symbols.append(parts[0])
        conformers.append(CrestConformer(
            frame_index=len(conformers), energy_eh=energy, positions=positions, symbols=symbols,
        ))
        index += 2 + count
    if not conformers:
        return [], "empty"
    return conformers, None


def _xyz_atom_count(xyz_text: str, what: str) -> int:
    lines = xyz_text.splitlines()
    if not lines:
        raise ValueError(f"the {what} xyz text is empty")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(
            f"the {what} xyz first line must be the atom count, got {lines[0]!r}"
        ) from exc
    if count < 1:
        raise ValueError(f"the {what} xyz declares {count} atoms")
    return count


def _expected_atom_count(request: CrestRunRequest) -> int:
    """产物帧应有的原子数：default/nci/tautomerize 与输入一致；protonate/deprotonate 各 ±1
    （CREST 2.12 实测，默认单轮质子化/去质子化）；qcg 为 溶质 + nsolv×溶剂。"""
    base = request.expected_atoms
    if base is not None:
        if base < 1:
            raise ValueError(f"expected_atoms must be >= 1, got {base}")
    else:
        base = _xyz_atom_count(request.xyz_text, "CREST input")
    if request.runtype in RUNTYPE_ATOM_DELTA:
        base += RUNTYPE_ATOM_DELTA[request.runtype]
    elif request.runtype == "qcg":
        base += request.nsolv * _xyz_atom_count(request.solvent_xyz_text, "QCG solvent")
    if base < 1:
        raise ValueError(f"the expected product atom count is {base} (runtype={request.runtype})")
    return base


def run_crest(request: CrestRunRequest) -> CrestRunResult:
    """在持久运行目录里跑一次 CREST，返回分层分类后的结果。

    本函数是同步的（子进程 + 文件 IO）；异步调用方必须经 ``asyncio.to_thread`` 卸载。
    """
    expected_atoms = _expected_atom_count(request)
    command = build_crest_command(request)
    run_dir = next_run_dir(request.output_dir, RUNS_DIR_NAME, request.run_label)

    product_name = RUNTYPE_PRODUCT[request.runtype]
    input_path = os.path.join(run_dir, "input.xyz")
    command_path = os.path.join(run_dir, "command.txt")
    versions_path = os.path.join(run_dir, "versions.txt")
    stdout_path = os.path.join(run_dir, "stdout.log")
    stderr_path = os.path.join(run_dir, "stderr.log")
    conformers_path = os.path.join(run_dir, product_name)

    atomic_write_text(input_path, request.xyz_text)
    if request.runtype == "qcg":
        atomic_write_text(os.path.join(run_dir, "solvent.xyz"), request.solvent_xyz_text)
    atomic_write_text(command_path, " ".join(command) + "\n")
    atomic_write_text(versions_path, capture_versions(("crest", "xtb"), ("Version", "version", "xTB program")))

    result = CrestRunResult(
        run_dir=run_dir,
        command=command,
        input_path=input_path,
        command_path=command_path,
        versions_path=versions_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        conformers_path=conformers_path,
    )

    if not _which("crest"):
        result.termination_reason = "executable_missing"
        result.diagnostics.append(
            "the 'crest' executable was not found on PATH; nothing was run (install CREST and "
            "retry, or use backend='rdkit')"
        )
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        result.artifacts = [
            CrestArtifact(name=name, path=path, size_bytes=size)
            for name, path, size in list_artifact_files(run_dir)
        ]
        result.message = "CREST executable not found; no run was started."
        return result

    timed_out = False
    returncode: Optional[int] = None
    # 独立进程组：超时只能终止**本次运行自己**的进程树（CREST 会再起 xtb 子进程）。
    # 绝不按进程名匹配杀进程，也绝不触碰调度器/guard 拥有的计算。
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
            f"CREST exceeded the {request.timeout}s timeout; this run's own process group was "
            "terminated (its logs and intermediate files are kept)"
        )

    atomic_write_text(stdout_path, stdout or "")
    atomic_write_text(stderr_path, stderr or "")
    result.returncode = returncode
    result.artifacts = [
        CrestArtifact(name=name, path=path, size_bytes=size)
        for name, path, size in list_artifact_files(run_dir)
    ]
    # 初始优化一旦跑过，CREST 就把逐帧轨迹留在 xtbopt.log；末帧即它真正拿到的几何。
    # 这里记录"输入 → 优化末帧"的连接表差异（片内/片间）供人判断，绝不代替人判断。
    # 只有 default/nci 的产物与输入同原子集合，对比才有意义；protonate/tautomerize/qcg
    # 的产物刻意改变原子数或连接性，跳过对比（xtbopt.log 在这些模式下也未必存在）。
    if request.runtype in ("default", "nci"):
        result.topology_change = _topology_change_report(request, run_dir, input_path)

    if request.noreftopo:
        result.diagnostics.append(
            "--noreftopo was used: the INITIAL topology check before the search was disabled, so this "
            "run would NOT have stopped on an initial-topology change. CREGEN's in-search topology "
            "checks are untouched (-notopo was deliberately NOT passed). Any topology change is still "
            "recorded in topology_change; treat the ensemble accordingly."
        )
    lines = (stdout or "").splitlines()
    # Fortran ERROR STOP（如 QCG 缺 xtb-IFF）写 stderr 而非 stdout，两路都要扫。
    scan_lines = lines + (stderr or "").splitlines()
    hits, marker, stage = _scan_markers(scan_lines)
    result.evidence = hits
    result.stage = stage

    if timed_out:
        result.termination_reason = "timeout"
        result.stage = stage if stage != "not_started" else "search"
        result.message = (
            f"CREST timed out after {request.timeout}s (returncode={returncode}). Increase timeout "
            f"or use backend='rdkit'. Full log: {stdout_path}"
        )
        return result

    if os.path.isfile(os.path.join(run_dir, SENTINEL_NOT_CONVERGED)):
        result.diagnostics.append(
            f"CREST wrote its '{SENTINEL_NOT_CONVERGED}' sentinel in the run directory "
            "(corroborates an optimization failure; the log marker is the primary evidence)"
        )

    if returncode != 0:
        result.termination_reason = marker if marker and marker != "completed" else "unknown_failure"
        if result.termination_reason == "qcg_xtbiff_missing":
            result.diagnostics.append(
                "QCG requires the external xtb-IFF program, which CREST did not find "
                "(https://github.com/grimme-lab/xtbiff); install it or use a non-QCG runtype"
            )
        if result.termination_reason == "unknown_failure":
            tail = "\n".join(lines[-15:]) if lines else (stderr or "")[-2000:]
            result.diagnostics.append(
                "CREST failed with no recognised marker; raw log tail follows (no cause is guessed)"
            )
            result.diagnostics.append(tail)
        if os.path.isfile(conformers_path):
            result.diagnostics.append(
                f"a partial {product_name} exists in the run directory; it is kept as evidence "
                "but NOT used, because the process did not exit successfully"
            )
        result.message = (
            f"CREST failed ({result.termination_reason}, stage={result.stage}, "
            f"returncode={returncode}). Full log: {stdout_path}"
        )
        return result

    # returncode == 0：仍要确认正常结束标记 + 产物完整性，"产物在"不构成成功判据。
    if marker != "completed":
        result.termination_reason = "unknown_failure"
        result.diagnostics.append(
            "CREST exited 0 but never printed its normal-termination marker "
            f"({MARKER_NORMAL_TERMINATION!r}); refusing to treat the exit code alone as success"
        )
        result.message = f"CREST did not report normal termination. Full log: {stdout_path}"
        return result

    conformers, problem = _parse_conformers(conformers_path, expected_atoms)
    result.stage = "artifact_check"
    if problem is not None:
        result.termination_reason = "incomplete_artifacts"
        result.diagnostics.append(
            f"{product_name} is unusable: {problem} (the file is kept in the run directory)"
        )
        result.message = (
            f"CREST reported normal termination but its {product_name} output is unusable "
            f"({problem}). Full log: {stdout_path}"
        )
        return result

    result.termination_reason = "completed"
    result.stage = "done"
    result.conformers = conformers
    result.conformer_count = len(conformers)
    result.scientific_success = True
    result.message = (
        f"CREST completed (runtype={request.runtype}): {len(conformers)} structures in "
        f"{product_name}. Run directory: {run_dir}"
    )
    return result


def _topology_change_report(request: CrestRunRequest, run_dir: str,
                            initial_path: str) -> Optional[TopologyChangeReport]:
    """读 CREST 留下的初始优化轨迹末帧，与交给它的输入结构对比连接表。

    只记录变化。任何读取/对比失败都只落 diagnostics，绝不让"对比不出来"变成运行结果的一部分。
    """
    optimized_path = os.path.join(run_dir, XTBOPT_LOG_NAME)
    if not os.path.isfile(optimized_path):
        return None
    try:
        after = read_last_xtbopt_frame(optimized_path)
        before = read_xyz_frame(initial_path)
        expected = read_xyz_frame_text(request.expected_product_xyz) if request.expected_product_xyz else None
        return compare_topology(
            before_path=initial_path,
            after_path=optimized_path,
            before=before,
            after=after,
            expected_product_path="<request.expected_product_xyz>" if expected else "",
            expected_product=expected,
        )
    except Exception:  # noqa: BLE001 - 对比失败不改变运行结论，如实记录为"无报告"
        return None


def read_xyz_frame_text(xyz_text: str) -> tuple[list[str], list[list[float]]]:
    """从 xyz 文本读单帧 ``(元素, 坐标)``。"""
    lines = xyz_text.splitlines()
    if not lines:
        raise ValueError("the provided xyz text is empty")
    count = int(lines[0].strip())
    if len(lines) < 2 + count:
        raise ValueError(f"the provided xyz text declares {count} atoms but has too few lines")
    symbols: list[str] = []
    positions: list[list[float]] = []
    for line in lines[2: 2 + count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"malformed xyz coordinate line: {line!r}")
        symbols.append(parts[0])
        positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return symbols, positions


def _which(name: str) -> str:
    import shutil

    return shutil.which(name) or ""
