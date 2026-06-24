from pydantic import Field
from typing import Any, Literal

from pydantic_core.core_schema import field_after_validator_function
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session
from cloudra.config import CloudraConfig
import sqlite3
import os
import time


datadir = CloudraConfig().data_dir
db_path = os.path.join(datadir, "tasks", "database.db")

description = (
    "提交计算任务的工具。"
    "接收已生成的输入文件路径，在 compute_jobs 表中创建任务记录，"
    "由框架层的 Compute Executor 自动捞取并执行。"
    "任务提交后立刻返回 job_id，不会等待计算完成。"
)


class SubmitComputeJob_input_schema(input_schema):
    input_file: str = Field(
        description="输入文件的绝对路径（如 .gjf 文件）。"
    )
    job_type: Literal["gaussian", "vasp", "orca"] = Field(
        default="gaussian",
        description="计算任务类型。当前支持 'gaussian'，'vasp' 和 'orca' 为预留选项。"
    )
    is_async: bool = Field(
        default=False,
        description="是否异步运行该任务，若任务时长较久，建议异步运行"
            )


class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="提交是否成功")
    job_id: int = Field(default=-1, description="计算任务 ID，后续用于查询状态")
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

    async def tool_call(self, user_input: SubmitComputeJob_input_schema, session: Session) -> SubmitComputeJob_output_schema:
        # 1. 校验 input_file 是否存在
        f_path = user_input.input_file
        workdir = os.path.dirname(f_path)
        conv_id = getattr(self.subagent, 'conversation_id', 'default')
        if os.path.exists(f_path):
            if user_input.is_async:
                try:
                    con = sqlite3.connect(db_path)
                    cur = con.cursor()
                    # 4. INSERT INTO compute_jobs (conversation_id, path, state, job_type, start_timestamp)
                    try:
                        cur.execute('''
                        INSERT INTO compute_jobs (conversation_id, path, state, jobtype, start_timestamp, end_timestamp) 
                        VALUES (?,?,?,?,?,?)
                                ''',
                        (conv_id, f_path, 'ready', user_input.job_type, -1, -1))
                        job_id = cur.lastrowid
                        con.commit()
                        con.close()
                        # 5. 返回 job_id, job_dir, state='ready'
                        return SubmitComputeJob_output_schema(
                                is_success=True,
                                job_id=job_id,
                                job_dir=workdir,
                                state="ready",
                                message="任务提交成功，将会定时唤醒你去监测任务。")
                    except Exception as e:
                        con.rollback()
                        con.close()
                        return SubmitComputeJob_output_schema(
                                is_success=False,
                                message=f"任务提交遇到错误：{e}")

                except Exception as e:
                    return SubmitComputeJob_output_schema(
                            is_success=False,
                            message=f"数据库连接遇到错误：{e}")

            else:
                # 直接写入running，并开始计算
                try:
                    con = sqlite3.connect(db_path)
                    cur = con.cursor()
                    try:
                        now = time.time()
                        cur.execute('''
                        INSERT INTO compute_jobs (conversation_id, path, state, jobtype, start_timestamp, end_timestamp) 
                        VALUES (?,?,?,?,?,?)
                                ''',
                        (conv_id, f_path, 'running', user_input.job_type, now, -1))
                        job_id = cur.lastrowid
                        con.commit()
                        # 任务提交是昂贵的，必须在数据库留痕才允许进行。
                        await self.run_now(job_id, db_path, f_path, user_input.job_type, conv_id)
                        con.close()
                        return SubmitComputeJob_output_schema(
                                is_success=True,
                                job_id=job_id,
                                job_dir=workdir,
                                state="ready",
                                message="任务运行完毕")


                    except Exception as e:
                        con.close()
                        return SubmitComputeJob_output_schema(
                                is_success=False,
                                message=f"任务提交遇到错误：{e}")
                
                except Exception as e:
                    return SubmitComputeJob_output_schema(
                            is_success=False,
                            message=f"数据库连接遇到错误：{e}")

        else:
            return SubmitComputeJob_output_schema(
                    is_success=False,
                    message="文件或目录不存在。")


    async def run_now(self, job_id: int, db_path: str, input_file: str, job_type: str, conv_id: str):
        """在主进程中阻塞执行计算任务，并在完成后更新数据库状态。"""
        import sys
        import asyncio

        guard_cmd = [
            sys.executable, '-m', 'cloudra.guard',
            '--path', input_file,
            '--timeout', '1800',
            '--conv_id', conv_id,
            '--task_id', str(job_id),
            '--db_path', db_path,
        ]
        calculate_cmd = ['calculator.sh', input_file, job_type]

        guard_proc = None
        try:
            # 启动 guard 在后台周期性解析输出并唤醒 agent
            guard_proc = await asyncio.create_subprocess_exec(*guard_cmd)

            # 阻塞执行实际计算脚本，直到其结束
            calc_proc = await asyncio.create_subprocess_exec(*calculate_cmd)
            returncode = await calc_proc.wait()

            # 给 guard 一段短暂的解析窗口（最多 10 秒）
            if guard_proc.returncode is None:
                try:
                    await asyncio.wait_for(guard_proc.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass

            # 更新数据库中的任务状态
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            state = 'done' if returncode == 0 else 'failed'
            cur.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                (state, time.time(), job_id)
            )
            con.commit()
            con.close()
        finally:
            # 确保 guard 不会成为僵尸/常驻进程
            if guard_proc is not None and guard_proc.returncode is None:
                guard_proc.kill()
                await guard_proc.wait()


def get_class():
    return SubmitComputeJob
