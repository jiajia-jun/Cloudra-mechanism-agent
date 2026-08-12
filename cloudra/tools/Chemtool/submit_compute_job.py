import json
import os
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra import events
from cloudra.infra.compute_utils import check_job_type, launch_compute_processes
from cloudra.persistence.database import ConversationDB, get_database_path
from cloudra.tools.core.delegation_guard import coordinator_self_compute_warning

description = (
    "提交计算任务：接收已生成的输入文件路径，在 compute_jobs 表中创建任务记录，"
    "由框架层的 Compute Executor 自动捞取并执行；提交后立刻返回 job_id，不会等待计算完成。"
    "适用：Gaussian、CP2K、VASP、ORCA 等耗时计算的正式提交执行，"
    "输入文件需先用 gjf_writer 等工具（CP2K 为 .inp）准备好。"
    "不适用：生成输入文件（用 gjf_writer）、查询任务进度（用 query_compute_job）、"
    "查看计算结果（算完后用 log_parser 解析日志）。"
)


class SubmitComputeJob_input_schema(input_schema):
    input_file: str = Field(
        description="输入文件的绝对路径（如 .gjf 文件）。"
    )
    job_type: Literal["gaussian", "vasp", "orca", "cp2k"] = Field(
        default="gaussian",
        description="计算任务类型。当前支持 'gaussian'，'vasp'，'orca' 和 'cp2k'。"
    )
    is_async: bool = Field(
        default=False,
        description="是否异步运行该任务，若任务时长较久，建议异步运行"
            )
    execution_backend: Literal["auto", "local", "slurm"] = Field(
        default="auto",
        description=(
            "执行后端。auto 根据 Phase 8 node registry 中输入文件所属 workspace "
            "选择 local/slurm；Slurm 任务始终异步提交。"
        ),
    )


class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="提交是否成功")
    job_id: int = Field(default=-1, description="计算任务 ID，用 query_compute_job 查询其状态")
    job_dir: str = Field(default="", description="计算任务的工作目录绝对路径")
    state: str = Field(default="", description="任务初始状态（正常为 'ready'）")
    message: str = Field(default="", description="状态或错误信息")


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
        conv_id = getattr(self.subagent, 'conversation_id', 'default')

        if not os.path.exists(f_path):
            return SubmitComputeJob_output_schema(
                    is_success=False,
                    message="文件或目录不存在。")

        scheduler = user_input.execution_backend
        scheduler_options: dict = {"type": scheduler}
        if scheduler == "auto":
            try:
                from cloudra.services.nodes import NodeRegistry

                node, _workspace = NodeRegistry.from_environment().route_for_path(
                    Path(f_path)
                )
                scheduler_options = dict(node.scheduler)
                scheduler = str(scheduler_options.get("type", "local"))
            except Exception as exc:
                if os.getenv("CLOUDRA_NODE_REGISTRY_FILE"):
                    return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"无法为输入文件解析 node scheduler：{exc}",
                    )
                scheduler = "local"
                scheduler_options = {"type": "local"}

        if scheduler == "local":
            ok, msg = check_job_type(user_input.job_type, workdir)
        elif scheduler == "slurm":
            from cloudra.infra.slurm import check_slurm_tools

            ok, msg = check_slurm_tools()
        else:
            ok, msg = False, f"不支持的执行后端: {scheduler}"
        if not ok:
            return SubmitComputeJob_output_schema(is_success=False, message=msg)

        db_path = get_database_path(conv_id)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = ConversationDB(conv_id)

        if user_input.is_async or scheduler == "slurm":
            try:
                async with db.aconnect() as con:
                    cur = await con.execute('''
                    INSERT INTO compute_jobs
                    (conversation_id, session_id, path, state, jobtype,
                     start_timestamp, end_timestamp, scheduler, scheduler_options)
                    VALUES (?,?,?,?,?,?,?,?,?)
                            ''',
                    (
                        conv_id, session_id, f_path, 'ready', user_input.job_type,
                        -1, -1, scheduler,
                        json.dumps(scheduler_options, ensure_ascii=False),
                    ))
                    job_id = cur.lastrowid
                    await con.commit()
                    await events.aemit(
                        conv_id,
                        "compute_job_ready",
                        task_id=job_id,
                        job_type=user_input.job_type,
                    )
                    return self._with_delegation_hint(
                        SubmitComputeJob_output_schema(
                            is_success=True,
                            job_id=job_id,
                            job_dir=workdir,
                            state="ready",
                            message=(
                                f"任务已提交到 {scheduler} 后端，将会在终态时唤醒。"
                            ),
                        )
                    )

            except Exception as e:
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"任务提交遇到错误：{e}")

        else:
            # 直接写入 running，并开始计算
            try:
                async with db.aconnect() as con:
                    now = time.time()
                    cur = await con.execute('''
                    INSERT INTO compute_jobs
                    (conversation_id, session_id, path, state, jobtype,
                     start_timestamp, end_timestamp, scheduler, scheduler_options)
                    VALUES (?,?,?,?,?,?,?,?,?)
                            ''',
                    (
                        conv_id, session_id, f_path, 'running', user_input.job_type,
                        now, -1, scheduler,
                        json.dumps(scheduler_options, ensure_ascii=False),
                    ))
                    job_id = cur.lastrowid
                    await con.commit()
                    # 任务提交是昂贵的，必须在数据库留痕才允许进行。
                    state = await self.run_now(job_id, db_path, f_path, user_input.job_type, conv_id)
                    return self._with_delegation_hint(
                        SubmitComputeJob_output_schema(
                            is_success=True,
                            job_id=job_id,
                            job_dir=workdir,
                            state=state,
                            message=f"任务运行完毕，最终状态：{state}",
                        )
                    )

            except Exception as e:
                return SubmitComputeJob_output_schema(
                        is_success=False,
                        message=f"任务提交遇到错误：{e}")


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

        db = ConversationDB.from_path(db_path)
        if not ok:
            async with db.aconnect() as con:
                await con.execute(
                    "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                    ('failed', time.time(), job_id)
                )
                await con.commit()
            raise RuntimeError(f"运行计算任务失败：{msg}")

        state = 'done'
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                (state, time.time(), job_id)
            )
            await con.commit()
        return state


def get_class():
    return SubmitComputeJob
