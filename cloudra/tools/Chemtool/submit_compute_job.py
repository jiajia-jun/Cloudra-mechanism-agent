import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.compute_utils import (
    launch_compute_processes,
)
from cloudra.persistence.database import ComputeDB
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.services.compute_admission import admit_job, declared_cpus, declared_memory_mb
from cloudra.services.compute_store import afinalize_compute_job, ainsert_compute_job

description = (
    "Submit a compute job: take a prepared input-file path, insert a record in compute_jobs, "
    "and let the framework Compute Scheduler pick it up. Async, Slurm and SSH jobs return job_id immediately; "
    "local jobs with is_async=false wait for completion. "
    "Terminal states are pushed to the submitting session: non-coordinator sessions can be woken as individual "
    "jobs finish without waiting for their other jobs; coordinator notices stay in its inbox until another wake event. "
    "Do not poll query_compute_job or re-parse the log to wait. If you need an interim checkpoint, call `schedule` "
    "with a read-only check_command instead of polling in a loop. "
    "Use for: formally running long Gaussian, CP2K, VASP, ORCA, xtb or shell jobs; prepare the input first with qm_input_writer or similar (CP2K uses .inp; ordinary xtb takes .xyz; native xTB scans use the typed manifest prepared by ts_guess and job_type='chem_task'). "
    "For job_type='shell', input_file is a Bash script executed in its own directory. "
    "The script manages its environment and commands; inspect its captured log and output files after completion. "
    "For xtb jobs you must also declare charge, multiplicity, task (sp/opt/hess/ohess) and optionally solvent — "
    "xtb is CLI-flag driven and ignores any charge/multiplicity written inside the .xyz file. "
    "Do not use for: generating the input (use qm_input_writer), failure diagnosis (use query_compute_job), "
    "or inspecting chemistry results (parse the native log with log_parser after the job finishes). "
    "Resource contract: omit cpus and memory_mb to reserve the values declared in a Gaussian/ORCA "
    "input; when declaring them explicitly, they must cover the input request. "
    "For ORCA, memory_mb is total memory (nprocs * maxcore); for xtb, cpus is passed to "
    "the engine as --parallel. Shell resources are declared with cpus and memory_mb, never inferred from script text; "
    "omitting them keeps the ordinary one-CPU and default memory reservation. "
    "Under-declaring oversubscribes the node; over-declaring wastes queue time. "
    "Use query_compute_queue to check node capacity and queue length before choosing how much to request. "
    "Manual TS/IRC inputs are accepted. Use ts_prepare/ts_resume when you want the durable TS workflow."
)


class SubmitComputeJob_input_schema(input_schema):
    input_file: str = Field(
        description="Path of the input file (e.g. a .gjf file or Bash script for shell): absolute as-is, "
                    "or relative to the Agent working directory."
    )
    job_type: Literal["gaussian", "vasp", "orca", "cp2k", "xtb", "chem_task", "shell"] = Field(
        default="gaussian",
        description="Job type. For 'xtb' the input is a plain XYZ; 'chem_task' accepts only a typed xtb_scan manifest prepared by ts_guess. "
                    "For 'shell', input_file is a Bash script; it runs in the script's directory and manages its own environment."
    )
    is_async: bool = Field(
        default=False,
        description="Whether to run the job asynchronously; recommended for long jobs"
            )
    execution_backend: Literal["auto", "local", "slurm"] = Field(
        default="auto",
        description=(
            "Execution backend. auto picks local/slurm from the Phase 8 node registry "
            "based on the input file's workspace; Slurm jobs are always submitted asynchronously."
        ),
    )
    node_id: str | None = Field(
        default=None,
        description=(
            "Target node from the node registry (e.g. an SSH remote server or an HPC "
            "login node). When given, the node's own scheduler/capacity/connection decide "
            "execution — omit execution_backend. Remote (SSH) nodes are always asynchronous: "
            "files are staged to the remote host and results pulled back automatically. "
            "Use query_compute_queue to list registered nodes and free capacity."
        ),
    )
    cpus: int | None = Field(
        default=None,
        ge=1,
        le=1024,
        description=(
            "CPU cores to reserve on the node. Omit to infer Gaussian %nprocshared/%nproc "
            "or ORCA PALn/%pal nprocs from the input; when absent there too, defaults to 1. "
            "An explicit value must be at least the input's request. Shell scripts are not parsed for resources; "
            "declare the cores their commands need, or omit for 1 CPU."
        ),
    )
    memory_mb: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Memory to reserve in MB (for ORCA: nprocs * maxcore). "
            "Omit to infer the input's %mem or %maxcore declaration; when the "
            "input has none, node admission applies its default reservation. For shell scripts, declare "
            "the required memory here; script text is not parsed."
        ),
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=9,
        description=(
            "Queue priority, 0-9; higher runs first among queued jobs (same priority is FIFO). "
            "Use 5+ only for genuinely urgent jobs. Never preempts running jobs."
        ),
    )
    charge: int = Field(
        default=0,
        description=(
            "Molecular charge (xtb jobs only; passed as --chrg). xtb is CLI-flag driven: "
            "a charge/multiplicity line inside the .xyz comment is ignored by xtb — "
            "you MUST declare it here. Default 0."
        ),
    )
    multiplicity: int = Field(
        default=1,
        ge=1,
        description=(
            "Spin multiplicity (xtb jobs only; converted to --uhf = multiplicity-1). Default 1."
        ),
    )
    task: Literal["sp", "opt", "hess", "ohess"] = Field(
        default="sp",
        description=(
            "xtb run level (xtb jobs only): 'sp' single point (default), 'opt' geometry "
            "optimization (--opt), 'hess' frequencies (--hess), 'ohess' opt+freq (--ohess)."
        ),
    )
    solvent: str | None = Field(
        default=None,
        description=(
            "Implicit solvent name for xtb jobs (passed as --alpb NAME, e.g. 'water'). "
            "Omit for gas phase."
        ),
    )


class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether submission succeeded")
    job_id: int = Field(default=-1, description="Compute job ID; query its status with query_compute_job")
    job_dir: str = Field(default="", description="Absolute path of the job working directory")
    state: str = Field(default="", description="Initial job state (normally 'ready')")
    message: str = Field(default="", description="Status or error message")


class SubmitComputeJob(Tool):
    tool_id: str = 't-21'
    tool_name: str = 'submit_compute_job'
    tool_description: str = (
        "Submit a chemistry job or a Bash script (job_type='shell'). With is_async=true, a Slurm backend, or an "
        "SSH remote node (node_id), return the queued job id immediately; local jobs "
        "with is_async=false wait for completion. Provide the prepared input path; "
        "CPU and memory reservations are inferred from chemistry input declarations when omitted. "
        "Shell scripts run in their own directory, manage their own environment, and use declared resources "
        "(default 1 CPU and the node's ordinary memory reservation). Manual TS/IRC inputs are accepted; "
        "ts_prepare/ts_resume provides the durable TS workflow."
    )
    input_schema: Any = SubmitComputeJob_input_schema
    output_schema: Any = SubmitComputeJob_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(self, user_input: SubmitComputeJob_input_schema, session: Session) -> SubmitComputeJob_output_schema:
        from cloudra.runtime_v2.event_writer import EventPersistenceError
        from cloudra.runtime_v2.invocation_context import report_tool_progress
        from cloudra.runtime_v2.schemas import ToolProgress, ToolWaitTarget

        await report_tool_progress(ToolProgress(phase="validating", message="Checking compute input and admission"))
        # 兼容测试或旧调用中 session 为 None 的情况。
        session_id = getattr(session, "id", None) if session else None
        # 路径语义与 read/write 一致：相对路径解析到 agent 工作目录（沙箱），绝不读进程
        # cwd 的同名文件（C1 缺陷）。准入校验（输入存在、xtb 参数、节点/调度器解析、资源
        # 硬校验、申请量不得低于输入自述、引擎可用性）是**唯一实现**，在
        # services/compute_admission；TS 搜索 SOP 的 submit 阶段复用同一份，
        # 否则同一份作业会在两条入口下得出不同准入结论。
        f_path = resolve_tool_path(self, user_input.input_file)
        conv_id = getattr(self.subagent, 'conversation_id', None)
        if not conv_id:
            return SubmitComputeJob_output_schema(
                is_success=False,
                message=(
                    "submit_compute_job requires conversation_id on the agent; "
                    "refusing to attribute the job to 'default'."
                ),
            )

        scan_task = None
        if user_input.job_type == 'chem_task':
            from cloudra.runtime.chem_task import ChemTask
            from cloudra.tools.core.irc_path import parse_xyz
            from cloudra.tools.core.xtb_scan_runner import _xcontrol

            if {'charge', 'multiplicity', 'task', 'solvent'} & user_input.model_fields_set:
                return SubmitComputeJob_output_schema(is_success=False,
                    message='chem_task takes charge, multiplicity, task and solvent from its typed scan manifest')
            try:
                workspace = getattr(self.subagent, 'working_directory', None)
                if not workspace:
                    raise ValueError('native scan requires an Agent workspace')
                await asyncio.to_thread(lambda: Path(f_path).resolve().relative_to(Path(workspace).resolve()))
                scan_task = await asyncio.to_thread(lambda: ChemTask.model_validate_json(Path(f_path).read_text()))
                if scan_task.task != 'xtb_scan':
                    raise ValueError('public chem_task submission accepts only xtb_scan')
                xyz = parse_xyz(scan_task.reactant_xyz)
                if (xyz is None or len(scan_task.reactant_xyz.splitlines()) != len(xyz[0]) + 2
                        or not all(math.isfinite(value) for point in xyz[1] for value in point)):
                    raise ValueError('xtb_scan manifest has an invalid single-frame XYZ')
                _xcontrol(scan_task.scan, len(xyz[0]))
            except (OSError, ValueError) as exc:
                return SubmitComputeJob_output_schema(is_success=False, message=f'Invalid xtb_scan manifest: {exc}')

        # Omitted resources follow the input file's declarations.  Explicit
        # under-declarations remain errors in the shared admission check.
        try:
            cpus = user_input.cpus
            if cpus is None:
                cpus = scan_task.cpus if scan_task else await asyncio.to_thread(declared_cpus, f_path, user_input.job_type) or 1
            memory_mb = user_input.memory_mb
            if memory_mb is None:
                memory_mb = await asyncio.to_thread(declared_memory_mb, f_path, user_input.job_type)
        except ValueError as exc:
            return SubmitComputeJob_output_schema(is_success=False, message=f"Invalid resource declarations: {exc}")

        # 准入可能含 SSH 远端环境探测（阻塞 subprocess），一律离开事件循环线程。
        admission = await asyncio.to_thread(
            admit_job,
            input_file=f_path,
            job_type=user_input.job_type,
            cpus=cpus,
            memory_mb=memory_mb,
            charge=user_input.charge,
            multiplicity=user_input.multiplicity,
            task=user_input.task,
            solvent=user_input.solvent,
            execution_backend=user_input.execution_backend,
            node_id=user_input.node_id,
        )
        if not admission.ok:
            return SubmitComputeJob_output_schema(is_success=False, message=admission.message)
        workdir = admission.workdir
        scheduler = admission.scheduler
        scheduler_options = admission.scheduler_options
        await report_tool_progress(ToolProgress(
            phase="submitting", message="Admission passed; recording job in compute ledger",
            effective_arguments={**user_input.model_dump(mode="json"), "input_file": f_path,
                                 "cpus": cpus, "memory_mb": memory_mb,
                                 "node_id": admission.node_id, "execution_backend": scheduler},
        ))

        # compute_jobs 住中央库（data_dir/compute.db）；ainit 幂等，保证表存在
        db = await ComputeDB().ainit()

        # Slurm/SSH 远端作业永远异步（远端 stage/提交/轮询由调度守护的 poller 承担）；
        # 只有本机 local 支持 is_async=false 的同步等待路径。
        if user_input.is_async or scheduler != "local":
            try:
                job_id = await ainsert_compute_job(
                    db,
                    conversation_id=conv_id,
                    session_id=session_id,
                    path=f_path,
                    state="ready",
                    jobtype=user_input.job_type,
                    node_id=admission.node_id,
                    scheduler=scheduler,
                    scheduler_options=json.dumps(scheduler_options, ensure_ascii=False),
                    priority=user_input.priority,
                    req_cpus=cpus,
                    req_memory_mb=memory_mb,
                    charge=user_input.charge,
                    multiplicity=user_input.multiplicity,
                    xtb_task=user_input.task,
                    xtb_solvent=user_input.solvent,
                )
                # 调度守护进程轮询 DB 认领 ready 作业，无需事件通知
                await report_tool_progress(ToolProgress(
                    phase="submitting", message="Job recorded; scheduler will claim it",
                    compute_job_ids=[job_id],
                ))
                return SubmitComputeJob_output_schema(
                        is_success=True,
                        job_id=job_id,
                        job_dir=workdir,
                        state="ready",
                        message=(
                            f"Job submitted to node {admission.node_id} ({scheduler} backend); "
                            "a terminal notice will be delivered to the submitting session. "
                            "Do not poll for status — the terminal state is pushed automatically."
                        ),
                    )

            except EventPersistenceError:
                raise
            except Exception as e:
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"Job submission hit an error: {e}. "
                                "Next: check whether a partial job record was created with query_compute_job; "
                                "fix the cause and resubmit with submit_compute_job.")

        else:
            # 直接写入 running，并开始计算——同步路径也要过容量闸门，
            # 否则 is_async=false 能绕开 scheduler claim 打满节点。
            from cloudra.services.compute_store import sync_local_fits_capacity

            fits = await asyncio.to_thread(
                sync_local_fits_capacity,
                db,
                node_id=admission.node_id,
                cpus=cpus,
                memory_mb=memory_mb,
                node_resources=admission.node_resources,
            )
            if not fits:
                return SubmitComputeJob_output_schema(
                    is_success=False,
                    message=(
                        f"Node {admission.node_id} has no free slot "
                        f"(max_concurrent={admission.node_resources.get('max_concurrent', 1)}). "
                        "Wait for a running job to finish, or submit with is_async=true "
                        "so the scheduler queues it."
                    ),
                )
            job_id = -1
            try:
                job_id = await ainsert_compute_job(
                    db,
                    conversation_id=conv_id,
                    session_id=session_id,
                    path=f_path,
                    state="running",
                    jobtype=user_input.job_type,
                    node_id=admission.node_id,
                    scheduler=scheduler,
                    scheduler_options=json.dumps(scheduler_options, ensure_ascii=False),
                    priority=user_input.priority,
                    req_cpus=cpus,
                    req_memory_mb=memory_mb,
                    charge=user_input.charge,
                    multiplicity=user_input.multiplicity,
                    xtb_task=user_input.task,
                    xtb_solvent=user_input.solvent,
                    start_timestamp=time.time(),
                )
                # 任务提交是昂贵的，必须在数据库留痕才允许进行。
                await report_tool_progress(ToolProgress(
                    phase="waiting", message="Job recorded; starting local execution and awaiting result",
                    compute_job_ids=[job_id],
                    waits=[ToolWaitTarget(kind="compute_job", target_id=str(job_id))],
                ))
                state = await self.run_now(job_id, db.path, f_path, user_input.job_type, conv_id)
                return SubmitComputeJob_output_schema(
                    is_success=True,
                    job_id=job_id,
                    job_dir=workdir,
                    state=state,
                    message=f"Job finished, final state: {state}",
                )

            except EventPersistenceError:
                raise
            except Exception as e:
                # 已入库的作业不得丢编号：执行失败是"已提交作业失败"，回执必须
                # 带 job_id/job_dir/state 让调用方 query 同一编号拿到失败详情
                # （guard 已写终态与 last_error）。入库前失败的 job_id 保持 -1，
                # 与"提交失败"区分开，绝不按异常路径再插一条作业。
                if job_id is None or job_id < 0:
                    return SubmitComputeJob_output_schema(
                            is_success=False,
                            message=f"Job submission hit an error: {e}. "
                                    "Next: check whether a partial job record was created with query_compute_job; "
                                    "fix the cause and resubmit with submit_compute_job.")
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        job_id=job_id,
                        job_dir=workdir,
                        state="failed",
                        message=f"Job {job_id} failed during execution: {e}. "
                                "Next: use query_compute_job to inspect the job state and last_error, "
                                "read the log to locate the failure, then fix the input and resubmit.")


    async def run_now(self, job_id: int, db_path: str, input_file: str, job_type: str, conv_id: str) -> str:
        """在主进程中阻塞执行计算任务，并在完成后更新数据库状态。返回最终状态 'done' 或 'failed'。"""
        ok, msg = await launch_compute_processes(
            task_id=job_id,
            input_file=input_file,
            job_type=job_type,
            conv_id=conv_id,
            db_path=db_path,
            wait_for_calculator=True,
        )

        db = ComputeDB.from_path(db_path)
        if not ok:
            # CAS：guard 已写终态时不覆盖（双写竞态防护）
            await afinalize_compute_job(db, job_id, 'failed')
            raise RuntimeError(f"Compute job failed: {msg}")

        state = 'done'
        await afinalize_compute_job(db, job_id, state)
        return state
