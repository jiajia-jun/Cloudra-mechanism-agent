"""计算作业准入的**唯一实现**：提交前的全部校验与节点/调度器解析。

存在理由：`submit_compute_job` 与 TS 搜索 SOP 的 `submit` 阶段都必须做同一套准入判断
（输入文件存在、xtb 参数合法、节点/调度器解析、资源硬校验、申请量不得低于输入自述、
引擎可用性）。这些判断散在两处就会出现"同一份作业在两条入口下准入结论不同"的漏洞，
所以只留一份，调用方各自只负责**入库方式**（工具走异步入库于事件循环之外，
SOP 在自己的工作线程里走同步入库）。

本模块**不碰数据库**：准入是纯校验，入库留给调用方，层次才不混。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from cloudra.infra.compute_utils import check_job_type, validate_xtb_params


class AdmissionOutcome(BaseModel):
    """准入结论。``ok=False`` 时 ``message`` 是可直接展示给调用方的拒绝原因。"""

    ok: bool
    input_path: str = Field(default="", description="解析后的输入文件绝对路径")
    workdir: str = Field(default="", description="作业工作目录（输入文件所在目录）")
    scheduler: str = Field(default="", description="解析后的调度器类型，如 local / slurm")
    scheduler_options: dict = Field(default_factory=dict)
    node_resources: dict = Field(default_factory=dict)
    message: str = ""


def _read_declared_requirements(
    job_type: str, input_file: str
) -> tuple[Optional[int], Optional[int]]:
    """读输入文件自述的资源需求 ``(cpus, memory_mb)``；未声明的项返回 None（不猜）。"""
    try:
        with open(input_file, encoding="utf-8", errors="replace") as handle:
            content = handle.read(200_000)
    except OSError:
        return None, None
    required_cpus = required_mem_mb = None
    if job_type == "orca":
        pal = re.search(r"%pal\s+nprocs\s+(\d+)", content, re.I)
        maxcore = re.search(r"%maxcore\s+(\d+)", content, re.I)
        if pal:
            required_cpus = int(pal.group(1))
        if pal and maxcore:
            required_mem_mb = int(pal.group(1)) * int(maxcore.group(1))
    elif job_type == "gaussian":
        nproc = re.search(r"%nprocshared=(\d+)|%nproc=(\d+)", content, re.I)
        mem = re.search(r"%mem=(\d+(?:\.\d+)?)([GgMm][Bb]?)", content, re.I)
        if nproc:
            required_cpus = int(nproc.group(1) or nproc.group(2))
        if mem:
            amount = float(mem.group(1))
            required_mem_mb = (
                int(amount * 1024) if mem.group(2).lower().startswith("g") else int(amount)
            )
    return required_cpus, required_mem_mb


def declared_memory_mb(input_file: str, job_type: str) -> Optional[int]:
    """输入文件自述的内存需求（MB）；未声明返回 None。

    供提交路径在调用方未显式申请 ``memory_mb`` 时派生申请值——省略申请不再
    等于脱账（输入说什么就按什么记账），超容量声明随即被容量硬校验拒收。
    """
    _, required_mem_mb = _read_declared_requirements(job_type, input_file)
    return required_mem_mb


def resource_underestimate(
    job_type: str, input_file: str, cpus: int, memory_mb: Optional[int]
) -> Optional[str]:
    """申请量低于输入文件自述需求的诊断（ORCA %pal/%maxcore、Gaussian
    %nprocshared/%mem）。输入未声明的资源不猜；ORCA maxcore 是每核值，
    总需求 = nprocs * maxcore。外部程序的资源占用未知时不推断其内存。
    调用方未申请 memory_mb 时应先用 ``declared_memory_mb`` 派生申请值，
    再走到这里做低估比对。"""
    required_cpus, required_mem_mb = _read_declared_requirements(job_type, input_file)
    if required_cpus is not None and cpus < required_cpus:
        return (
            f"Resource under-provisioned: the input asks for {required_cpus} cores "
            f"but cpus={cpus} was requested. Request cpus={required_cpus} to match "
            "the input (under-declaring oversubscribes the node)."
        )
    if memory_mb is None:
        memory_mb = required_mem_mb
    if (
        required_mem_mb is not None
        and memory_mb is not None
        and memory_mb < required_mem_mb
    ):
        return (
            f"Resource under-provisioned: the input asks for {required_mem_mb} MB total "
            f"but memory_mb={memory_mb} was requested. Request memory_mb={required_mem_mb} "
            "to match the input (ORCA maxcore is per-core: total = nprocs * maxcore)."
        )
    return None


def admit_job(
    *,
    input_file: str,
    job_type: str,
    cpus: int,
    memory_mb: Optional[int],
    charge: int = 0,
    multiplicity: int = 1,
    task: str = "sp",
    solvent: Optional[str] = None,
    execution_backend: str = "local",
) -> AdmissionOutcome:
    """跑完整套准入校验，返回结论（不落库、不拉起计算）。

    ``input_file`` 必须是**已解析好**的绝对路径：路径语义（相对 → agent 工作目录）
    属于调用方，因为它依赖工具/agent 桥。

    ``charge``/``multiplicity``/``task``/``solvent`` 是 **xtb 专属**的运行参数：非 xtb 作业
    留默认值即可（电荷/自旋写在输入文件里）。给非 xtb 作业传非默认值会被 fail-loud 拒收——
    这正是"绝不静默丢弃"的那道门。
    """
    f_path = input_file
    workdir = os.path.dirname(f_path)

    if not os.path.exists(f_path):
        return AdmissionOutcome(
            ok=False,
            input_path=f_path,
            workdir=workdir,
            message=(
                f"Input file does not exist: {f_path}. "
                "Check the path, or generate the input first with qm_input_writer, then retry."
            ),
        )

    # xtb 任务参数 fail-loud 校验：非法组合在提交时显式报错，
    # 绝不静默降级为裸 SP（xyz 注释行的 charge/mult 对 xtb 无效）。
    param_error = validate_xtb_params(
        job_type=job_type, charge=charge, multiplicity=multiplicity,
        task=task, solvent=solvent,
    )
    if param_error:
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir, message=param_error,
        )

    scheduler = execution_backend
    scheduler_options: dict = {"type": scheduler}
    from cloudra.services.nodes import NodeRegistry, default_resources

    node_resources: Optional[dict] = None
    if scheduler == "auto":
        try:
            node, _workspace = NodeRegistry.from_environment().route_for_path(Path(f_path))
            scheduler_options = dict(node.scheduler)
            scheduler = str(scheduler_options.get("type", "local"))
            node_resources = dict(node.resources)
        except Exception as exc:  # noqa: BLE001 - 未配注册表时退回 local
            if os.getenv("CLOUDRA_NODE_REGISTRY_FILE"):
                return AdmissionOutcome(
                    ok=False, input_path=f_path, workdir=workdir,
                    message=f"Could not resolve a node scheduler for the input file: {exc}",
                )
            scheduler = "local"
            scheduler_options = {"type": "local"}
    if node_resources is None:
        try:
            node_resources = dict(NodeRegistry.from_environment().node(None).resources)
        except Exception:  # noqa: BLE001 - 同上，用默认容量
            node_resources = default_resources()

    # 资源硬校验（唯一校验点）：申请量超过节点总量直接拒收，让调用方改小重报
    if cpus > int(node_resources.get("cpus", 1)):
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources,
            message=(
                f"Requested cpus={cpus} exceeds node capacity ({node_resources.get('cpus')} cores). "
                "Reduce cpus to fit the node (check query_compute_queue for current capacity) and "
                "resubmit."
            ),
        )
    if memory_mb is not None and memory_mb > int(node_resources.get("memory_mb", 0)):
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources,
            message=(
                f"Requested memory_mb={memory_mb} exceeds node capacity "
                f"({node_resources.get('memory_mb')} MB). Reduce memory_mb to fit the node "
                "(check query_compute_queue for current capacity) and resubmit."
            ),
        )

    # 显式申请低于输入自述需求：返回诊断，不静默超额占用节点。
    underestimate = resource_underestimate(job_type, f_path, cpus, memory_mb)
    if underestimate:
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources, message=underestimate,
        )

    if scheduler == "local":
        ok, msg = check_job_type(job_type, workdir)
    elif scheduler == "slurm":
        from cloudra.infra.slurm import check_slurm_tools

        ok, msg = check_slurm_tools()
    else:
        ok, msg = False, f"Unsupported execution backend: {scheduler}"
    if not ok:
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources, message=msg,
        )

    return AdmissionOutcome(
        ok=True, input_path=f_path, workdir=workdir,
        scheduler=scheduler, scheduler_options=scheduler_options,
        node_resources=node_resources,
        message="Admitted.",
    )
