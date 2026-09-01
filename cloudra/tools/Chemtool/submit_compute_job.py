import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.compute_utils import check_job_type, launch_compute_processes
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import afinalize_compute_job, ainsert_compute_job
from cloudra.tools.core.delegation_guard import coordinator_self_compute_warning

description = (
    "Submit a compute job: take a prepared input-file path, insert a record in compute_jobs, "
    "and let the framework Compute Scheduler pick it up; returns job_id immediately without waiting for the job to finish. "
    "Use for: formally running long Gaussian, CP2K, VASP, or ORCA jobs; prepare the input first with qm_input_writer or similar (CP2K uses .inp). "
    "Do not use for: generating the input (use qm_input_writer), querying progress (use query_compute_job), "
    "or inspecting results (parse the log with log_parser after the job finishes). "
    "Resource contract: you write the input file, so declare exactly what it asks for — "
    "if your .gjf sets %nprocshared=16 then request cpus=16; for ORCA, request cpus=<pal nprocs> and "
    "memory_mb=<nprocs * maxcore>. Under-declaring oversubscribes the node; over-declaring wastes queue time. "
    "Use query_compute_queue to check node capacity and queue length before choosing how much to request."
)


class SubmitComputeJob_input_schema(input_schema):
    input_file: str = Field(
        description="Absolute path of the input file (e.g. a .gjf file)."
    )
    job_type: Literal["gaussian", "vasp", "orca", "cp2k"] = Field(
        default="gaussian",
        description="Job type. Currently supports 'gaussian', 'vasp', 'orca', and 'cp2k'."
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
    cpus: int = Field(
        default=1,
        ge=1,
        le=1024,
        description=(
            "CPU cores to reserve on the node. Must match the input file you wrote "
            "(e.g. Gaussian %nprocshared, ORCA %pal nprocs). Default 1."
        ),
    )
    memory_mb: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Memory to reserve in MB (for ORCA: nprocs * maxcore). "
            "Omit to use the node's default reservation."
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


class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether submission succeeded")
    job_id: int = Field(default=-1, description="Compute job ID; query its status with query_compute_job")
    job_dir: str = Field(default="", description="Absolute path of the job working directory")
    state: str = Field(default="", description="Initial job state (normally 'ready')")
    message: str = Field(default="", description="Status or error message")


class SubmitComputeJob(Tool):
    tool_id: str = 't-21'
    tool_name: str = 'submit_compute_job'
    tool_description: str = description
    input_schema: Any = SubmitComputeJob_input_schema
    output_schema: Any = SubmitComputeJob_output_schema

    def is_write(self) -> bool:
        return True

    def _with_delegation_hint(
        self, out: SubmitComputeJob_output_schema
    ) -> SubmitComputeJob_output_schema:
        """Coordinator 自行提交时附轻量提示；照常放行。"""
        if not out.is_success:
            return out
        warning = coordinator_self_compute_warning(self.subagent)
        if warning:
            out.message = f"{warning}\n\n{out.message}" if out.message else warning
        return out

    async def tool_call(self, user_input: SubmitComputeJob_input_schema, session: Session) -> SubmitComputeJob_output_schema:
        # 兼容测试或旧调用中 session 为 None 的情况。
        session_id = getattr(session, "id", None) if session else None
        # 1. 校验 input_file 是否存在
        f_path = user_input.input_file
        workdir = os.path.dirname(f_path)
        conv_id = getattr(self.subagent, 'conversation_id', None) or 'default'

        if not os.path.exists(f_path):
            return SubmitComputeJob_output_schema(
                    is_success=False,
                    message=f"Input file does not exist: {f_path}. "
                            "Check the path, or generate the input first with qm_input_writer, then retry.")

        scheduler = user_input.execution_backend
        scheduler_options: dict = {"type": scheduler}
        from cloudra.services.nodes import NodeRegistry, default_resources

        node_resources: dict | None = None
        if scheduler == "auto":
            try:
                node, _workspace = NodeRegistry.from_environment().route_for_path(
                    Path(f_path)
                )
                scheduler_options = dict(node.scheduler)
                scheduler = str(scheduler_options.get("type", "local"))
                node_resources = dict(node.resources)
            except Exception as exc:
                if os.getenv("CLOUDRA_NODE_REGISTRY_FILE"):
                    return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"Could not resolve a node scheduler for the input file: {exc}",
                    )
                scheduler = "local"
                scheduler_options = {"type": "local"}
        if node_resources is None:
            try:
                node_resources = dict(NodeRegistry.from_environment().node(None).resources)
            except Exception:
                node_resources = default_resources()

        # 资源硬校验（唯一校验点）：申请量超过节点总量直接拒收，让调用方改小重报
        if user_input.cpus > int(node_resources.get("cpus", 1)):
            return SubmitComputeJob_output_schema(
                is_success=False,
                message=(
                    f"Requested cpus={user_input.cpus} exceeds node capacity "
                    f"({node_resources.get('cpus')} cores). Reduce cpus to fit the node "
                    "(check query_compute_queue for current capacity) and resubmit."
                ),
            )
        if user_input.memory_mb is not None and user_input.memory_mb > int(node_resources.get("memory_mb", 0)):
            return SubmitComputeJob_output_schema(
                is_success=False,
                message=(
                    f"Requested memory_mb={user_input.memory_mb} exceeds node capacity "
                    f"({node_resources.get('memory_mb')} MB). Reduce memory_mb to fit the node "
                    "(check query_compute_queue for current capacity) and resubmit."
                ),
            )

        if scheduler == "local":
            ok, msg = check_job_type(user_input.job_type, workdir)
        elif scheduler == "slurm":
            from cloudra.infra.slurm import check_slurm_tools

            ok, msg = check_slurm_tools()
        else:
            ok, msg = False, f"Unsupported execution backend: {scheduler}"
        if not ok:
            return SubmitComputeJob_output_schema(is_success=False, message=msg)

        # compute_jobs 住中央库（data_dir/compute.db）；ainit 幂等，保证表存在
        db = await ComputeDB().ainit()

        if user_input.is_async or scheduler == "slurm":
            try:
                job_id = await ainsert_compute_job(
                    db,
                    conversation_id=conv_id,
                    session_id=session_id,
                    path=f_path,
                    state="ready",
                    jobtype=user_input.job_type,
                    scheduler=scheduler,
                    scheduler_options=json.dumps(scheduler_options, ensure_ascii=False),
                    priority=user_input.priority,
                    req_cpus=user_input.cpus,
                    req_memory_mb=user_input.memory_mb,
                )
                # 调度守护进程轮询 DB 认领 ready 作业，无需事件通知
                return self._with_delegation_hint(
                    SubmitComputeJob_output_schema(
                        is_success=True,
                        job_id=job_id,
                        job_dir=workdir,
                        state="ready",
                        message=(
                            f"Job submitted to the {scheduler} backend; you will be woken at the terminal state."
                        ),
                    )
                )

            except Exception as e:
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"Job submission hit an error: {e}. "
                                "Next: check whether a partial job record was created with query_compute_job; "
                                "fix the cause and resubmit with submit_compute_job.")

        else:
            # 直接写入 running，并开始计算
            try:
                job_id = await ainsert_compute_job(
                    db,
                    conversation_id=conv_id,
                    session_id=session_id,
                    path=f_path,
                    state="running",
                    jobtype=user_input.job_type,
                    scheduler=scheduler,
                    scheduler_options=json.dumps(scheduler_options, ensure_ascii=False),
                    priority=user_input.priority,
                    req_cpus=user_input.cpus,
                    req_memory_mb=user_input.memory_mb,
                    start_timestamp=time.time(),
                )
                # 任务提交是昂贵的，必须在数据库留痕才允许进行。
                state = await self.run_now(job_id, db.path, f_path, user_input.job_type, conv_id)
                return self._with_delegation_hint(
                    SubmitComputeJob_output_schema(
                        is_success=True,
                        job_id=job_id,
                        job_dir=workdir,
                        state=state,
                        message=f"Job finished, final state: {state}",
                    )
                )

            except Exception as e:
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"Job submission hit an error: {e}. "
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


def get_class():
    return SubmitComputeJob
