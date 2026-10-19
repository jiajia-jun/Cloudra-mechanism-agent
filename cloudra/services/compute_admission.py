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
import shlex
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from cloudra.infra.compute_utils import check_job_type, validate_xtb_params


class AdmissionOutcome(BaseModel):
    """准入结论。``ok=False`` 时 ``message`` 是可直接展示给调用方的拒绝原因。"""

    ok: bool
    input_path: str = Field(default="", description="解析后的输入文件绝对路径")
    workdir: str = Field(default="", description="作业工作目录（输入文件所在目录）")
    node_id: str = Field(default="", description="作业归属的注册节点（容量分池记账依据）")
    scheduler: str = Field(default="", description="解析后的调度器类型，如 local / slurm")
    scheduler_options: dict = Field(default_factory=dict)
    node_resources: dict = Field(default_factory=dict)
    message: str = ""


def _resource_integer(value: str, declaration: str) -> int:
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ValueError(f"Invalid resource declaration {declaration}: expected a positive integer, got {value!r}")
    return int(value)


def _record_resource(resources: dict[str, int], name: str, value: int) -> None:
    previous = resources.get(name)
    if previous is not None and previous != value:
        raise ValueError(f"Conflicting resource declarations for {name}: {previous} and {value}")
    resources[name] = value


def _orca_resources(content: str) -> tuple[Optional[int], Optional[int]]:
    resources: dict[str, int] = {}
    in_pal = False
    for line in content.splitlines():
        stripped = line.strip()
        if not in_pal:
            command = stripped.split(maxsplit=1)[0].lower().partition("=")[0].partition("#")[0] if stripped else ""
            if not stripped.startswith("!") and command not in ("%pal", "%maxcore"):
                continue
        # Keep quoted strings as quoted tokens, so native string arguments cannot
        # become resource declarations; # comments have no resource meaning.
        lexer = shlex.shlex(stripped, posix=False, punctuation_chars="=")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = []
        try:
            tokens.extend(lexer)
        except ValueError:
            # A malformed scientific string is outside resource validation.
            # Parse the complete tokens before it. Missing resource values or a
            # missing %pal end still fail below; an unrelated later block must
            # not invalidate an already complete declaration.
            pass
        if not tokens:
            continue
        if not in_pal and tokens[0].startswith("!"):
            keywords = [tokens[0][1:], *tokens[1:]]
            for keyword in keywords:
                suffix = keyword[3:] if keyword.lower().startswith("pal") else ""
                if suffix and (suffix[0].isdecimal() or suffix[0] in "+-"):
                    _record_resource(resources, "cpus", _resource_integer(suffix, keyword))
            continue
        index = 0
        while index < len(tokens):
            token = tokens[index].lower()
            if not in_pal and token == "%pal":
                in_pal = True
            elif not in_pal and token == "%maxcore":
                index += 1
                if index < len(tokens) and tokens[index] == "=":
                    index += 1
                if index == len(tokens):
                    raise ValueError("Invalid resource declaration %maxcore: missing MB value")
                _record_resource(resources, "maxcore", _resource_integer(tokens[index], "%maxcore"))
                if index + 1 < len(tokens) and not tokens[index + 1].startswith("%"):
                    raise ValueError("Invalid resource declaration %maxcore: expected one positive MB value")
            elif not in_pal:
                break
            elif token == "end":
                in_pal = False
            elif token == "nprocs":
                index += 1
                if index < len(tokens) and tokens[index] == "=":
                    index += 1
                if index == len(tokens):
                    raise ValueError("Invalid resource declaration %pal nprocs: missing CPU count")
                _record_resource(resources, "cpus", _resource_integer(tokens[index], "%pal nprocs"))
            index += 1
    if in_pal:
        raise ValueError("Invalid resource declaration %pal: missing end")
    cpus = resources.get("cpus")
    maxcore = resources.get("maxcore")
    # ORCA is serial without a parallel declaration; maxcore is still a real
    # memory declaration and must be reserved for that one process.
    return cpus, maxcore * (cpus or 1) if maxcore is not None else None


def _gaussian_memory_mb(value: str) -> int:
    parts = value.split()
    if len(parts) not in (1, 2) or (len(parts) == 2 and not parts[1].isalpha()):
        raise ValueError(f"Invalid resource declaration %mem={value!r}: expected one amount and unit")
    compact = "".join(parts).upper()
    index = 0
    while index < len(compact) and (compact[index] in "0123456789."):
        index += 1
    number, unit = compact[:index], compact[index:]
    scales = {
        "B": Decimal(1) / 1024**2, "KB": Decimal(1) / 1024,
        "MB": Decimal(1), "GB": Decimal(1024),
        "": Decimal(8) / 1024**2, "W": Decimal(8) / 1024**2,
        "KW": Decimal(8) / 1024, "MW": Decimal(8), "GW": Decimal(8192),
    }
    if (not number or number == "." or number.count(".") > 1
            or unit not in scales or Decimal(number) <= 0):
        raise ValueError(f"Invalid resource declaration %mem={value!r}: expected a positive byte/word amount")
    return int((Decimal(number) * scales[unit]).to_integral_value(rounding=ROUND_CEILING))


def _gaussian_resources(content: str) -> tuple[Optional[int], Optional[int]]:
    sections: list[dict[str, int]] = [{}]
    in_link0 = True
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower() == "--link1--":
            sections.append({})
            in_link0 = True
        elif stripped.startswith("#"):
            in_link0 = False
        elif in_link0 and stripped.startswith("%"):
            key, equals, value = stripped.partition("=")
            key = key.strip().lower()
            # Match whole Link 0 command names, never text in titles/geometry.
            if key.split()[0] not in ("%nprocshared", "%nproc", "%mem"):
                continue
            if not equals or key not in ("%nprocshared", "%nproc", "%mem"):
                raise ValueError(f"Invalid resource declaration {stripped!r}: expected command=value")
            name = "memory_mb" if key == "%mem" else "cpus"
            amount = _gaussian_memory_mb(value) if key == "%mem" else _resource_integer(value.strip(), key)
            _record_resource(sections[-1], name, amount)
    # Link1 jobs execute sequentially; reserve each resource's largest declaration.
    cpus = max((section["cpus"] for section in sections if "cpus" in section), default=None)
    memory_mb = max((section["memory_mb"] for section in sections if "memory_mb" in section), default=None)
    return cpus, memory_mb


def _read_declared_requirements(
    job_type: str, input_file: str
) -> tuple[Optional[int], Optional[int]]:
    """Read native resource declarations; unknown items stay None, invalid ones raise ValueError."""
    if job_type not in ("orca", "gaussian"):
        return None, None
    try:
        with open(input_file, encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return None, None
    return _orca_resources(content) if job_type == "orca" else _gaussian_resources(content)


def declared_memory_mb(input_file: str, job_type: str) -> Optional[int]:
    """输入文件自述的内存需求（MB）；未声明返回 None。

    供提交路径在调用方未显式申请 ``memory_mb`` 时派生申请值——省略申请不再
    等于脱账（输入说什么就按什么记账），超容量声明随即被容量硬校验拒收。
    """
    _, required_mem_mb = _read_declared_requirements(job_type, input_file)
    return required_mem_mb


def declared_cpus(input_file: str, job_type: str) -> Optional[int]:
    """CPU count declared by a Gaussian or ORCA input; otherwise unknown."""
    required_cpus, _ = _read_declared_requirements(job_type, input_file)
    return required_cpus


def resource_underestimate(
    job_type: str, input_file: str, cpus: int, memory_mb: Optional[int]
) -> Optional[str]:
    """申请量低于输入文件自述需求的诊断（ORCA %pal/%maxcore、Gaussian
    %nprocshared/%mem）。输入未声明的资源不猜；ORCA maxcore 是每核值，
    总需求 = nprocs * maxcore。外部程序的资源占用未知时不推断其内存。
    调用方未申请 memory_mb 时应先用 ``declared_memory_mb`` 派生申请值，
    再走到这里做低估比对。"""
    try:
        required_cpus, required_mem_mb = _read_declared_requirements(job_type, input_file)
    except ValueError as exc:
        return f"Invalid resource declarations: {exc}"
    if required_cpus is not None and cpus < required_cpus:
        return (
            f"Resource under-provisioned: the input asks for {required_cpus} cores "
            f"but cpus={cpus} was requested. Request cpus={required_cpus} to match "
            "the input, or omit cpus to infer it (under-declaring oversubscribes the node)."
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
            "to match the input, or omit memory_mb to infer it "
            "(ORCA maxcore is per-core: total = nprocs * maxcore)."
        )
    return None


def _route_node(input_file: str) -> tuple[Optional[object], str]:
    """按注册表工作区路由解析作业归属节点，返回 ``(node, 失败原因)``。

    注册表缺失/损坏、或路径不在任何注册工作区内都返回 ``(None, 原因)``——调用方
    决定是 fail-loud 还是回落默认节点。
    """
    from cloudra.services.nodes import NodeRegistry

    try:
        node, _workspace = NodeRegistry.from_environment().route_for_path(Path(input_file))
    except Exception as exc:  # noqa: BLE001 - 路由失败的种类由调用方定性
        return None, str(exc)
    return node, ""


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
    execution_backend: str = "auto",
    node_id: Optional[str] = None,
) -> AdmissionOutcome:
    """跑完整套准入校验，返回结论（不落库、不拉起计算）。

    ``input_file`` 必须是**已解析好**的绝对路径：路径语义（相对 → agent 工作目录）
    属于调用方，因为它依赖工具/agent 桥。

    ``charge``/``multiplicity``/``task``/``solvent`` 是 **xtb 专属**的运行参数：非 xtb 作业
    留默认值即可（电荷/自旋写在输入文件里）。给非 xtb 作业传非默认值会被 fail-loud 拒收——
    这正是"绝不静默丢弃"的那道门。

    ``node_id`` 显式指定注册表节点（agent 选远端服务器的入口）：给定后跳过工作区
    路由，调度器类型与容量记账都以该节点为准；``execution_backend`` 非 auto 时
    必须与节点自身的 scheduler.type 一致，否则 fail-loud。带 SSH connection 的
    节点生效调度器落 ``ssh_local``/``ssh_slurm``（本地记账、远端执行），connection
    快照并入 scheduler_options——账本行自包含，重启/改注册表后仍可恢复。
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

    # 作业归属节点：显式 node_id 优先（agent 指定远端服务器），否则按注册表
    # 工作区路由解析（execution_backend=auto 时它同时决定调度器）。**资源硬校验
    # 与容量分池记账用的是同一个节点**，否则"按谁的额度校验"与"记到谁的账上"
    # 会分叉。解析不到时回落默认节点；auto 且显式配了注册表却路由不到 = 提交
    # 配置错误，fail-loud（不静默降级到本机跑）。
    connection: dict = {}
    if node_id is not None:
        try:
            node = NodeRegistry.from_environment().node(node_id)
        except Exception:  # noqa: BLE001 - 统一成准入拒绝消息
            return AdmissionOutcome(
                ok=False, input_path=f_path, workdir=workdir,
                message=(
                    f"Unknown node: {node_id!r}. List registered nodes and their "
                    "free capacity with query_compute_queue, then pick a valid node_id."
                ),
            )
        node_scheduler_type = str(node.scheduler.get("type", "local"))
        if scheduler not in ("auto", node_scheduler_type):
            return AdmissionOutcome(
                ok=False, input_path=f_path, workdir=workdir,
                message=(
                    f"execution_backend={scheduler!r} conflicts with node {node_id!r} "
                    f"(scheduler {node_scheduler_type!r}); omit execution_backend or "
                    "match the node's scheduler."
                ),
            )
        route_error = ""
    else:
        node, route_error = _route_node(f_path)
    if node is None and scheduler == "auto" and os.getenv("CLOUDRA_NODE_REGISTRY_FILE"):
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            message=f"Could not resolve a node scheduler for the input file: {route_error}",
        )
    if node is not None:
        assigned_node_id = node.node_id
        from cloudra.services.host_capacity import effective_node_resources

        node_resources = dict(effective_node_resources(node))
        connection = dict(getattr(node, "connection", None) or {})
        if scheduler == "auto":
            scheduler_options = dict(node.scheduler)
            scheduler = str(scheduler_options.get("type", "local"))
    else:
        if scheduler == "auto":
            scheduler = "local"
            scheduler_options = {"type": "local"}
        try:
            default_node = NodeRegistry.from_environment().node(None)
            assigned_node_id = default_node.node_id
            from cloudra.services.host_capacity import effective_node_resources

            node_resources = dict(effective_node_resources(default_node))
            connection = dict(getattr(default_node, "connection", None) or {})
        except Exception:  # noqa: BLE001 - 注册表缺失/损坏：单节点兜底
            assigned_node_id = os.getenv("CLOUDRA_NODE_ID", "node-local")
            node_resources = default_resources()

    # SSH 远端节点：生效调度器加 ssh_ 前缀（本地调度记账、远端执行）。
    if connection.get("type") == "ssh":
        scheduler = f"ssh_{scheduler}"
        scheduler_options = dict(
            scheduler_options, type=scheduler, connection=connection
        )

    # 资源硬校验（唯一校验点）：申请量超过节点总量直接拒收，让调用方改小重报
    if cpus > int(node_resources.get("cpus", 1)):
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            node_id=assigned_node_id, scheduler=scheduler, scheduler_options=scheduler_options,
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
            node_id=assigned_node_id, scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources,
            message=(
                f"Requested memory_mb={memory_mb} exceeds node capacity "
                f"({node_resources.get('memory_mb')} MB). Reduce memory_mb to fit the node "
                "(check query_compute_queue for current capacity) and resubmit."
            ),
        )

    # The capacity ledger and the physical Slurm allocation must describe the
    # same request.  Node registry values provide routing and scheduler
    # defaults, but using their fixed cpus/memory here would make every job run
    # with a different allocation than the one admitted and recorded below.
    if scheduler in ("slurm", "ssh_slurm"):
        scheduler_options = dict(scheduler_options)
        scheduler_options["cpus"] = cpus
        if memory_mb is not None:
            scheduler_options["memory"] = f"{memory_mb}M"

    # 显式申请低于输入自述需求：返回诊断，不静默超额占用节点。
    manifest = None
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import ChemTask
        try:
            manifest = ChemTask.model_validate_json(Path(f_path).read_text())
            if manifest.cpus > cpus:
                raise ValueError('chemistry task CPU allocation is smaller than manifest request')
        except (OSError, ValueError) as exc:
            return AdmissionOutcome(ok=False, message=str(exc))

    underestimate = resource_underestimate(job_type, f_path, cpus, memory_mb)
    if underestimate:
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            node_id=assigned_node_id, scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources, message=underestimate,
        )

    if scheduler == "local":
        ok, msg = check_job_type(job_type, workdir)
        if ok and manifest is not None and manifest.task == 'xtb_scan':
            ok, msg = check_job_type('xtb', workdir)
    elif scheduler == "slurm":
        from cloudra.infra.slurm import check_slurm_tools

        ok, msg = check_slurm_tools()
    elif scheduler in ("ssh_local", "ssh_slurm"):
        from cloudra.infra.ssh_transport import (
            SshEndpoint,
            check_remote_environment,
        )

        ok, msg = check_remote_environment(
            SshEndpoint.from_connection(connection),
            job_type,
            slurm=scheduler == "ssh_slurm",
        )
    else:
        ok, msg = False, f"Unsupported execution backend: {scheduler}"
    if not ok:
        return AdmissionOutcome(
            ok=False, input_path=f_path, workdir=workdir,
            node_id=assigned_node_id, scheduler=scheduler, scheduler_options=scheduler_options,
            node_resources=node_resources, message=msg,
        )

    return AdmissionOutcome(
        ok=True, input_path=f_path, workdir=workdir,
        node_id=assigned_node_id, scheduler=scheduler, scheduler_options=scheduler_options,
        node_resources=node_resources,
        message="Admitted.",
    )
