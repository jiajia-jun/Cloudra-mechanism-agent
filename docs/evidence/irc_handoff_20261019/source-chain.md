# 独立 IRC 端点交接：真实源码快照

本附录记录本次已改调用链的完整 AST 定义，保留所有分支、参数与返回。它是交付证据快照，不是持续维护文档。原生 Gaussian/ORCA 解析、调度转发及未改的基础函数，按调用顺序见 [原审计完整附录](../qm_consistency_20261019/source-chain.md)。本次没有修改那些科学解析与几何判据。

调用顺序：准备输入并 submit → 本地完成冻结或远端回收 → 同源双端导出 → 查询/通知/Artifact 交付 → XYZ 续算输入 → DAG 不可变入库 → 同源严格验收与具体恢复 → 缓存版本核对。正式 TS process 的自动端点输入对照在末尾。所有实际公开 schema 保留完整定义；新路径只增加可选输出，没有新必填入参。


## cloudra/tools/Chemtool/submit_compute_job.py:47 — SubmitComputeJob_input_schema

文件 SHA256: 252530809ee101c672d4652436266fb4a7d028637fe2ed3c20611cc1d76b365f

```python
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
```


## cloudra/tools/Chemtool/submit_compute_job.py:139 — SubmitComputeJob_output_schema

文件 SHA256: 252530809ee101c672d4652436266fb4a7d028637fe2ed3c20611cc1d76b365f

```python
class SubmitComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether submission succeeded")
    job_id: int = Field(default=-1, description="Compute job ID; query its status with query_compute_job")
    job_dir: str = Field(default="", description="Absolute path of the job working directory")
    state: str = Field(default="", description="Initial job state (normally 'ready')")
    message: str = Field(default="", description="Status or error message")
```


## cloudra/tools/Chemtool/submit_compute_job.py:147 — SubmitComputeJob

文件 SHA256: 252530809ee101c672d4652436266fb4a7d028637fe2ed3c20611cc1d76b365f

```python
class SubmitComputeJob(Tool):
    tool_id: str = 't-21'
    tool_name: str = 'submit_compute_job'
    tool_description: str = (
        "Submit a chemistry job or a Bash script (job_type='shell'). With is_async=true, a Slurm backend, or an "
        "SSH remote node (node_id), return the queued job id immediately; local jobs "
        "with is_async=false wait for completion. Provide the prepared input path; "
        "CPU and memory reservations are inferred from chemistry input declarations when omitted. "
        "Shell scripts run in their own directory, manage their own environment, and use declared resources "
        "(default 1 CPU and the node's ordinary memory reservation). Use ts_prepare/ts_resume for formal TS "
        "solving and complete verification. Direct TS/IRC submissions are for exploratory trials or capability probes only."
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
```


## cloudra/runtime/monitor.py:423 — _finalize

文件 SHA256: d8473506a098bbf98b6fac56247b034f2279d06d65ca6ad079ae22c94652fdb4

```python
async def _finalize(
    db: ComputeDB,
    taskid: int,
    log_path: Path,
    workdir: str,
    parse_timeout: int,
    job_type: str,
    returncode: int | None,
    fallback_log_path: Path | None = None,
    xtb_task: str | None = None,
):
    """calculator 退出后的统一收尾：解析日志 → 写 state json → CAS 落库 → 入箱。

    终态通知由 API 进程的 ComputeNotifyBroker 轮询 compute_jobs 表补投，
    guard 不再发进程间事件。``xtb_task`` 是行声明的 xtb 运行级别（opt 收敛
    判据只对 opt/ohess 生效）。
    """
    if job_type == "shell":
        if returncode is None:
            lock_path = await asyncio.to_thread(calc_lock_path, workdir, taskid)
            try:
                record = json.loads(await asyncio.to_thread(
                    Path(lock_path).with_suffix(".exit.json").read_text, encoding="utf-8",
                ))
                returncode = record["exit_code"]
                if type(returncode) is not int:
                    raise ValueError("exit_code must be an integer")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                await _mark_failed(db, taskid, f"Shell exit code unavailable: {exc}")
                return
        is_success = returncode == 0
        data_dic = {
            "is_success": is_success,
            "exit_code": returncode,
            "log_file": str(fallback_log_path or log_path),
        }
        if not is_success:
            data_dic["error"] = f"Shell script exited with code {returncode}"
    else:
        if job_type in {'gaussian', 'orca'}:
            receipt = Path(workdir) / '.cloudra' / f'execution-{taskid}' / 'evidence.json'
            if await asyncio.to_thread(receipt.is_file):
                row = await aget_compute_job(db, taskid)
                source = row['path']
                log_path = Path(await asyncio.to_thread(complete_execution_evidence, source, job_type, taskid))
                fallback_log_path = None
        data_dic, is_success = await _parse_log(
            log_path, parse_timeout, job_type=job_type,
            fallback_log_path=fallback_log_path, xtb_task=xtb_task,
        )
    if data_dic is None:
        # reason 从"实际应解析的日志"取：推导路径缺失时它可能在落盘回退文件里
        target, _ = await asyncio.to_thread(_resolve_log_target, log_path, fallback_log_path)
        reason = await asyncio.to_thread(_log_tail_reason, target) if target is not None else ""
        await _mark_failed(
            db,
            taskid,
            "guard 在解析窗口内无法完成日志解析"
            + (f"（calculator 退出码 {returncode}）" if returncode else "")
            + (f"；日志尾部：{reason}" if reason else "；日志为空或缺失"),
        )
        return

    state = 'done' if is_success else 'failed'
    fail_reason = ""
    if state == 'failed':
        # 解析器已给出明确原因时优先采用。
        parser_reason = str(data_dic.get("error") or "")
        # reason 从"实际应解析的日志"取：推导路径缺失时它可能在落盘回退文件里
        target, _ = await asyncio.to_thread(_resolve_log_target, log_path, fallback_log_path)
        tail = await asyncio.to_thread(_log_tail_reason, target) if target is not None else ""
        fail_reason = parser_reason or (
            f"calculator 退出码 {returncode}；" if returncode else ""
        ) + (tail or "未在日志尾部找到明确错误段")
        data_dic["error"] = fail_reason

    json_nm = f'state_{taskid}.json'
    json_path = os.path.join(workdir, json_nm)
    try:
        # CAS：同步路径 run_now 或其他收尾方已写终态时不覆盖。
        # 先落账本再写磁盘：cancel-all 赢了 CAS 则不把成功产物/审查当完成。
        wrote = await afinalize_compute_job(
            db, taskid, state, last_error=fail_reason or None
        )
    except Exception as e:
        print(f'[guard] 更新数据库失败：{e}')
        return
    if not wrote:
        print(
            f'[guard] ledger already terminal; skip artifact/review '
            f'task_id={taskid} parsed_state={state}'
        )
        return
    try:
        await asyncio.to_thread(atomic_write_json, json_path, data_dic, indent=4)
    except Exception as e:
        print(f'写入 json 失败（账本已终态）：{e}')

    print(f'[guard] 数据库状态已更新: task_id={taskid}, state={state}')

    # D5/D11：dag 模式下计算作业终态入 CallReview 收件箱（带作业终态，
    # 不是 submit 调用的成败）；standard 模式内部跳过。
    try:
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(taskid, state)
    except Exception as e:
        print(f'[guard] enqueue compute review 失败（已忽略）: {e}')
```


## cloudra/infra/compute_utils.py:502 — complete_execution_evidence

文件 SHA256: 518fc5b6fde8e4aefd89b46fb481f399bc768b16db510971efa67da40a8e3d3b

```python
def complete_execution_evidence(input_file: str, job_type: str, task_id: int) -> str:
    """Freeze this execution's selected log and its native IRC endpoint bundle."""
    if job_type not in {'gaussian', 'orca'}:
        return resolve_log_path(input_file, job_type, task_id)
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    receipt = _execution_receipt(input_file, task_id)
    metadata = receipt / 'evidence.json'
    record = json.loads(metadata.read_text()) if metadata.exists() else {}
    if record.get('log_file'):
        write_irc_endpoint_artifacts(record['log_file'])
        return record['log_file']
    native = Path(get_log_path(input_file, job_type))
    captured = Path(input_file).parent / '.cloudra' / f'calc-{task_id}.out.log'
    source = native if native.is_file() and native.stat().st_size else captured
    results = receipt / 'results'
    results.mkdir(parents=True, exist_ok=True)
    target = results / source.name
    if source.is_file():
        shutil.copy2(source, target)
        if job_type == 'orca':
            geometries = _orca_geometry_output_paths(input_file)
            record.update(input_file=input_file, job_type=job_type,
                          geometry_stems=sorted({path.name.removesuffix('_IRC_F.xyz') for path in geometries
                                                 if path.name.endswith('_IRC_F.xyz')}))
            atomic_write_json(metadata, record)
            for geometry in geometries:
                if geometry.is_file():
                    shutil.copy2(geometry, results / geometry.name)
            from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

            snapshot_irc_endpoints(str(target), results)
        write_irc_endpoint_artifacts(target)
    record['log_file'] = str(target)
    atomic_write_json(metadata, record)
    return str(target)
```


## cloudra/infra/compute_utils.py:540 — resolve_log_path

文件 SHA256: 518fc5b6fde8e4aefd89b46fb481f399bc768b16db510971efa67da40a8e3d3b

```python
def resolve_log_path(input_file: str, job_type: str = "gaussian", task_id: int | None = None) -> str:
    """解析计算作业的真实日志路径——query_compute_job 与完成通知统一走这里（GH #20）。

    预测路径（引擎惯例后缀）常与 guard 实际解析的日志不一致：部分引擎不自写
    日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
    guard 会把 calculator stdout 捕获到 ``.cloudra/calc-<id>.out.log`` 并回退解析它，
    实际解析路径记录在 guard state json 的 ``log_file`` 字段。
    远端已有本轮 results 收据时只认收据内的原生日志/捕获，不读取旧本地证据。
    有执行收据时只认其冻结日志；尚未收尾时返回本次 capture。
    没有执行收据的已有记录仍可由其 state json 定位原来的日志。
    """
    if job_type == 'chem_task':
        return input_file
    if input_file and task_id is not None:
        workdir = Path(input_file).parent
        receipt = _execution_receipt(input_file, task_id)
        try:
            evidence = json.loads((receipt / 'evidence.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            evidence = None
        if evidence is not None or receipt.is_dir():
            # An execution receipt never falls back to a later shared output.
            if (evidence or {}).get('log_file'):
                return evidence['log_file']
            native = Path(get_log_path(input_file, job_type))
            if evidence is not None and native.is_file() and native.stat().st_size:
                return str(native)
            return str(workdir / '.cloudra' / f'calc-{task_id}.out.log')
        remote_results = workdir / '.cloudra' / f'remote-{task_id}' / 'results'
        if remote_results.is_dir():
            # A remote execution receipt must never fall back to evidence left
            # by a previous local/remote run in the shared input directory.
            native = remote_results / Path(get_log_path(input_file, job_type)).name
            if native.is_file() and native.stat().st_size:
                return str(native)
            captured = remote_results / '.cloudra' / f'calc-{task_id}.out.log'
            if captured.is_file():
                return str(captured)
            return str(native)
        try:
            recorded = json.loads(
                (workdir / f"state_{task_id}.json").read_text(encoding="utf-8")
            ).get("log_file")
        except (OSError, ValueError):
            recorded = None
        if recorded and Path(recorded).is_file():
            return str(recorded)
        native = Path(get_log_path(input_file, job_type=job_type))
        if job_type == 'gaussian' and native.is_file() and native.stat().st_size:
            return str(native)
        captured = workdir / ".cloudra" / f"calc-{task_id}.out.log"
        if captured.is_file():
            return str(captured)
    return get_log_path(input_file, job_type=job_type)
```


## cloudra/runtime/remote_compute.py:545 — _pull_remote_artifacts

文件 SHA256: 32a6bbf6f10869eb3001a40fab171da8388b7d7bbbaabeb828a97694e4fdf270

```python
def _pull_remote_artifacts(transport, remote_dir: str, workdir: Path, input_file: Path, task_id: int,
                           job_type: str | None = None) -> None:
    """Pull to a receipt first, then publish outputs without replacing the input.

    Every downloaded byte stays in results, including the relocated execution
    input. Replaced local artifacts are retained alongside the receipt.
    """
    receipt = workdir / '.cloudra' / f'remote-{task_id}'
    results = receipt / 'results'
    results.mkdir(parents=True, exist_ok=True)
    transport.pull_dir(remote_dir, str(results))
    manifest_path = receipt / 'path-map.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {'files': []}
    bundled_files = set()
    if (job_type or manifest.get('job_type')) == 'orca':
        from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

        native = results / Path(get_log_path(str(input_file), 'orca')).name
        captured = results / '.cloudra' / f'calc-{task_id}.out.log'
        source = native if native.is_file() and native.stat().st_size else captured
        if source.is_file():
            snapshot_irc_endpoints(str(source), source.parent)
        archive = source.parent / 'irc_endpoints.json'
        if archive.is_file():
            endpoints = json.loads(archive.read_text())['endpoints']
            bundled_files = {(archive.parent / item['filename']).relative_to(results).as_posix()
                             for item in endpoints.values() if item.get('filename')}
    protected = {input_file.resolve()}
    protected.update(Path(item['local_path']).resolve() for item in manifest['files'] if item['role'] == 'dependency')
    staged_files = manifest.get('staged_files', {})
    baselines = {str(workdir / name): digest for name, digest in staged_files.items()}
    baselines.update({item['local_path']: item['source_sha256'] for item in manifest['files']
                      if not item['directory'] and not item['prefix']})
    protected.update((workdir / name).resolve() for name in staged_files if Path(name).suffix.casefold() in {'.gjf', '.com', '.inp'})

    def publish(source: Path, target: Path) -> None:
        relative = source.relative_to(results)
        if (relative in {Path('irc_endpoints.json'), Path('.cloudra/irc_endpoints.json')}
                or relative.as_posix() in bundled_files):
            return  # Derived receipt metadata is never a native output to publish.
        if target.resolve() in protected or source.is_symlink():
            return
        if target.is_symlink():
            raise SshError(f'artifact conflicts with local symlink; retained in {results}: {target}')
        parent = target.parent
        while parent != parent.parent:
            if parent.is_symlink():
                raise SshError(f'artifact conflicts with parent symlink; retained in {results}: {target}')
            parent = parent.parent
        if 'staged_files' in manifest:
            baseline = baselines.get(str(target))
            with source.open('rb') as stream:
                incoming = hashlib.file_digest(stream, 'sha256').hexdigest()
            if incoming == baseline:
                return  # This is an unchanged staged file, not an output.
            current = None
            if target.is_file():
                with target.open('rb') as stream:
                    current = hashlib.file_digest(stream, 'sha256').hexdigest()
            if current != baseline and current != incoming:
                raise SshError(f'local/remote artifact conflict; retained in {results}: {target}')
        if target.exists():
            if target.is_file() and filecmp.cmp(source, target, shallow=False):
                return
            digest = hashlib.sha256(str(target).encode()).hexdigest()
            backup = receipt / 'replaced' / digest / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                if target.is_dir():
                    shutil.copytree(target, backup, symlinks=True)
                else:
                    shutil.copy2(target, backup, follow_symlinks=False)
            if target.is_dir():
                raise SshError(f'artifact file conflicts with local directory; retained in {results}: {target}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for source in results.rglob('*'):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(results)
        if (relative == Path('calculator.sh') or relative.parts[0].startswith('.cloudra-files-')
                or relative.parts[:2] == ('.cloudra', f'remote-{task_id}')):
            continue
        publish(source, workdir / relative)
    for item in manifest['files']:
        if item['role'] == 'dependency':
            continue
        source = results / item['staged_path']
        target = Path(item['local_path'])
        if item['directory']:
            for child in source.rglob('*'):
                if child.is_file() and not child.is_symlink():
                    publish(child, target / child.relative_to(source))
        elif item['prefix']:
            for child in source.parent.iterdir():
                if child.name.startswith(source.name) and child.is_file() and not child.is_symlink():
                    publish(child, target.with_name(target.name + child.name[len(source.name):]))
        elif source.is_file() and not source.is_symlink():
            publish(source, target)

    if (job_type or manifest.get('job_type')) in {'gaussian', 'orca'}:
        from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

        engine = job_type or manifest['job_type']
        native = results / Path(get_log_path(str(input_file), engine)).name
        captured = results / '.cloudra' / f'calc-{task_id}.out.log'
        selected = native if native.is_file() and native.stat().st_size else captured
        if selected.is_file():
            write_irc_endpoint_artifacts(selected)
```


## cloudra/tools/core/irc_endpoint_artifacts.py:21 — _canonical_artifacts

文件 SHA256: 7b6da03d6c1ff1f6043e824764c4fecd740b3e9fd249db11523ecb49a0897064

```python
def _canonical_artifacts(log_path: str | Path) -> dict[str, tuple[Path, str]]:
    path = Path(log_path)
    try:
        native = path.read_bytes()
        text = native.decode('utf-8', errors='replace')
        engine = qm_engine.detect_qm_engine_from_text(text)
        parser = {'gaussian': gaussian_frames, 'orca': orca_frames}.get(engine)
        if parser is None or not parser.normal_termination(text):
            return {}
        # Only an execution/DAG archive may establish ORCA sidecar ownership.
        # Never invoke the native reader's unique-neighbor convenience fallback.
        if engine == 'orca' and orca_frames._archived_irc_endpoints(str(path)) is None:
            return {}
        ends = irc_evidence.irc_endpoint_geometries(path)
        if ends is None or path.read_bytes() != native:
            return {}
        digest = hashlib.sha256(native).hexdigest()
        result = {}
        for side, (symbols, positions) in zip(('a', 'b'), ends, strict=True):
            if not symbols or len(symbols) != len(positions):
                return {}
            rows = [str(len(symbols)), 'Native IRC outer frame; independent Opt/Freq required.']
            for symbol, point in zip(symbols, positions, strict=True):
                if len(point) != 3 or not all(math.isfinite(float(value)) for value in point):
                    return {}
                rows.append(f'{symbol} {point[0]:.12f} {point[1]:.12f} {point[2]:.12f}')
            target = path.parent / f'irc-{digest}.end-{side}.xyz'
            result[f'irc_end_{side}_path'] = (target, '\n'.join(rows) + '\n')
        return result
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        return {}
```


## cloudra/tools/core/irc_endpoint_artifacts.py:54 — write_irc_endpoint_artifacts

文件 SHA256: 7b6da03d6c1ff1f6043e824764c4fecd740b3e9fd249db11523ecb49a0897064

```python
def write_irc_endpoint_artifacts(log_path: str | Path) -> dict[str, str]:
    """Atomically export both native outer frames alongside this frozen log.

    Non-IRC, abnormal, one-sided or unbound ORCA evidence yields no handoff.
    Existing native logs, sidecars and submitted inputs are never rewritten.
    """
    artifacts = _canonical_artifacts(log_path)
    try:
        for path, content in artifacts.values():
            if not path.is_symlink() and path.is_file() and path.read_bytes() == content.encode('utf-8'):
                continue
            atomic_write_text(str(path), content)
    except OSError as exc:
        # These are derived handoff files, not the native calculation verdict.
        logger.warning('Could not export native IRC endpoints for %s: %s', log_path, exc)
        return {}
    return {key: str(path) for key, (path, _content) in artifacts.items()}
```


## cloudra/tools/core/irc_endpoint_artifacts.py:73 — read_irc_endpoint_artifacts

文件 SHA256: 7b6da03d6c1ff1f6043e824764c4fecd740b3e9fd249db11523ecb49a0897064

```python
def read_irc_endpoint_artifacts(log_path: str | Path) -> dict[str, str]:
    """Read only a complete, untampered native-derived pair; never create files."""
    artifacts = _canonical_artifacts(log_path)
    try:
        if any(path.is_symlink() or not path.is_file() or path.read_bytes() != content.encode('utf-8')
               for path, content in artifacts.values()):
            return {}
    except OSError:
        return {}
    return {key: str(path) for key, (path, _content) in artifacts.items()}
```


## cloudra/tools/Chemtool/query_compute_job.py:43 — ComputeJobRecord

文件 SHA256: c4fd96c6802ed4b93eb9cbd986459456e44f1b5bf565f51a3680316ae9e08a90

```python
class ComputeJobRecord(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid", strict=True)

    job_id: int
    state: str
    node_id: str
    scheduler: str | None
    scheduler_state: str
    jobtype: str | None
    path: str
    log_path: str
    started_at: str
    ended_at: str
    last_error: str
    attempt_count: int
    charge: NotRequired[int]
    multiplicity: NotRequired[int]
    task: NotRequired[str]
    solvent: NotRequired[str]
    cpus: NotRequired[int]
    irc_end_a_path: NotRequired[str]
    irc_end_b_path: NotRequired[str]
```


## cloudra/tools/Chemtool/query_compute_job.py:67 — QueryComputeJob_output_schema

文件 SHA256: c4fd96c6802ed4b93eb9cbd986459456e44f1b5bf565f51a3680316ae9e08a90

```python
class QueryComputeJob_output_schema(output_schema):
    is_success: bool = Field(description="Whether the query succeeded")
    jobs: list[ComputeJobRecord] = Field(default_factory=list, description=(
        "Compute ledger records; a successful query does not imply job completion or scientific verification. "
        "Available IRC A/B paths are native outer frames for independent Opt/Freq, not reactant/product assignments."))
    message: str = Field(default="", description="Status or error message")
```


## cloudra/tools/Chemtool/query_compute_job.py:85 — _row_to_dict

文件 SHA256: c4fd96c6802ed4b93eb9cbd986459456e44f1b5bf565f51a3680316ae9e08a90

```python
def _row_to_dict(row: Dict[str, Any]) -> ComputeJobRecord:
    path = row["path"] or ""
    # log_path 与完成通知统一走 resolve_log_path（GH #20）：优先 guard state
    # json 记录的真实日志 / calc 落盘文件，都没有才回退引擎惯例预测。
    from cloudra.infra.compute_utils import resolve_log_path

    log_path = (
        resolve_log_path(path, job_type=row["jobtype"] or "gaussian", task_id=row["id"])
        if path
        else ""
    )
    out = {
        "job_id": row["id"],
        "state": row["state"],
        "node_id": row["node_id"] or "",
        "scheduler": row["scheduler"],
        "scheduler_state": row["scheduler_state"] or "",
        "jobtype": row["jobtype"],
        "path": path,
        "log_path": log_path,
        "started_at": _iso(row["start_timestamp"]),
        "ended_at": _iso(row["end_timestamp"]),
        "last_error": row["last_error"] or "",
        "attempt_count": row["attempt_count"] or 0,
    }
    if row['state'] == 'done' and row['jobtype'] in {'gaussian', 'orca'} and log_path:
        from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts

        out.update(read_irc_endpoint_artifacts(log_path))
    if row["jobtype"] == "xtb":
        # xtb 显式任务参数（--chrg/--uhf/multiplicity、运行级别、溶剂、并行核数）
        out["charge"] = row["charge"] if row["charge"] is not None else 0
        out["multiplicity"] = row["multiplicity"] or 1
        out["task"] = row["xtb_task"] or "sp"
        out["solvent"] = row["xtb_solvent"] or ""
        out["cpus"] = row["req_cpus"] or 1
    return out
```


## cloudra/tools/Chemtool/query_compute_job.py:124 — QueryComputeJob

文件 SHA256: c4fd96c6802ed4b93eb9cbd986459456e44f1b5bf565f51a3680316ae9e08a90

```python
class QueryComputeJob(Tool):
    tool_id: str = 't-48'
    tool_name: str = 'query_compute_job'
    tool_description: str = description
    input_schema: Any = QueryComputeJob_input_schema
    output_schema: Any = QueryComputeJob_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: QueryComputeJob_input_schema, session: Session) -> QueryComputeJob_output_schema:
        conv_id = getattr(self.subagent, 'conversation_id', None) or 'default'
        # compute_jobs 住中央库（节点级共享）；按 conversation_id 过滤出本会话的作业
        db = ComputeDB()
        if not await asyncio.to_thread(os.path.exists, db.path):
            return QueryComputeJob_output_schema(is_success=True, jobs=[], message="No compute jobs have been submitted in this conversation yet.")

        try:
            if user_input.job_id is not None:
                row = await aget_compute_job(db, user_input.job_id)
                if row is None or row["conversation_id"] != conv_id:
                    return QueryComputeJob_output_schema(
                        is_success=False,
                        jobs=[],
                        message=f"No compute job found for job_id={user_input.job_id}.",
                    )
                rows = [row]
            else:
                limit = max(1, min(int(user_input.limit or 10), 50))
                rows = await alist_compute_jobs(
                    db, conversation_id=conv_id, order="recent", limit=limit
                )
        except Exception as e:
            return QueryComputeJob_output_schema(is_success=False, jobs=[], message=f"Query failed: {e}")

        jobs = await asyncio.to_thread(lambda: [_row_to_dict(row) for row in rows])
        message = f"{len(jobs)} job record(s)."
        if any(job["state"] not in TERMINAL_STATES for job in jobs):
            message += (
                " STOP POLLING. Some jobs are still in a non-terminal state, and re-querying "
                "will NOT change that: terminal states (done/failed/cancelled) are PUSHED to you "
                "to the submitting session. Non-coordinator sessions can stop and be woken as individual jobs "
                "finish; coordinator notifications are stored without waking the coordinator, so "
                "schedule a wake-up if waiting directly. Do other work while the job runs. If you need an "
                "interim checkpoint, use schedule once with a one-shot read-only check_command."
            )
        return QueryComputeJob_output_schema(
            is_success=True,
            jobs=jobs,
            message=message,
        )
```


## cloudra/runtime_v2/compute_notify.py:340 — ComputeNotifyBroker._content_for

文件 SHA256: cb30c15658b3513b86e3c389c429cacddcc465146746cb23bda6175ff31e8855

```python
    async def _content_for(
        self, task_id: int, state: str, *, view: dict | None = None, record: dict | None = None,
    ) -> str:
        """Small recorded facts; complete TS diagnostics remain available through inspect."""
        from cloudra.infra.compute_utils import resolve_log_path
        from cloudra.services.compute_store import aget_compute_job

        db = ComputeDB()
        info = await resolve_submission_info(db, task_id)
        fail_reason = ""
        job_type = "gaussian"
        try:
            row = await aget_compute_job(db, task_id)
            if row:
                info["path"] = row["path"] or info.get("path") or ""
                fail_reason = row["last_error"] or ""
                job_type = row["jobtype"] or job_type
        except Exception:
            pass
        input_path = str(info.get("path") or "")
        log_path = await asyncio.to_thread(resolve_log_path, input_path,
            job_type=job_type, task_id=task_id) if input_path else ""
        lines = [f"Compute Event: Job {task_id}, state={state}."]
        evidence = []
        if log_path:
            evidence.append(f"Log: {log_path}")
        if input_path:
            evidence.append(f"Input: {Path(input_path).name}" if log_path else f"Input: {input_path}")
            if job_type == 'shell':
                evidence.append(f"Working directory: {Path(input_path).parent}")
        if view is not None:
            verdict = view.get('result') or {}
            blocked = view.get('blocked') or {}
            verified = verdict.get('verified') is True
            attempt = view.get('failed_attempt') or {}
            purpose = attempt.get('purpose', '') if attempt.get('job_id') == task_id else ''
            if not purpose and record:
                steps = [*record.get('job_steps', []), record.get('scan_step') or {}]
                purpose = next((step.get('purpose', '') for step in steps if step.get('job_id') == task_id), '')
            stage = ' / '.join(str(part) for part in [view.get('stage'), purpose] if part)
            lines[0] += f" TS {view['run_id']}: {stage}."
            window = self._reaction_window(record, view, purpose, job_type)
            if window:
                lines.append('Reaction Window: ' + window)
            reason = fail_reason or verdict.get('reason') or blocked.get('message') or view.get('message')
            observation = f"outcome={verdict['outcome']}; " if verdict.get('outcome') else ''
            observation += f"verified={str(verified).lower()}."
            if reason:
                observation += f" {reason}"
            lines.append('Physical Reality: ' + observation)
            inspect = f"ts_inspect(run_id={view['run_id']!r})"
            frequency = view.get('frequency_analysis') or {}
            alignment = frequency.get('mode_alignment') or {}
            if (frequency.get('job_id') == task_id
                    and alignment.get('status') in {'misaligned', 'undecidable'}):
                lines.append('Advisory from ts_guess: ' + str(alignment.get('message') or alignment['status']))
                next_action = (f'Use {inspect} to review the mode and current jobs. '
                    'This check is advisory and may be wrong; it does not block or cancel jobs. '
                    'Decide whether to keep the pipeline running or call ts_stop with a reason, '
                    'then revise the guess with ts_resume when appropriate.')
            elif verified:
                next_action = ('Submit the verified native logs through the DAG evidence tools.'
                    if view.get('details_path') else f'Use {inspect} for the verified evidence, then submit its native logs through the DAG evidence tools.')
            elif blocked.get('failure_class') == 'scan_no_candidate':
                next_action = (f"Use {inspect} to compare the native structures and logs. "
                    'Test alternative approach orientation or asynchronous bond changes with sequential scans; '
                    'consider tool-generated GSM/NEB guesses. These are hypotheses, not established causes; '
                    'record the observation and evidence paths in PROCESS.md before choosing the next test.')
            elif blocked.get('failure_class') == 'wrong_mode' or verdict.get('outcome') == 'candidate_only':
                next_action = (f"Use {inspect} to check the native mode/IRC endpoints and intended bond changes. "
                    'Distinguish numerical failure from a different reaction connection, then choose the next test.')
            elif view.get('status') == 'blocked':
                next_action = f"Use {inspect} for diagnostics, then revise the research input with ts_resume as needed."
            else:
                next_action = f"Inspect the observed chemistry and choose the next distinguishing test; use {inspect} for details."
            if view.get('details_path'):
                evidence.append(f"Details: {view['details_path']}")
        elif job_type == 'shell':
            if state == 'done':
                lines.append('Process: Shell script exited successfully.')
                next_action = 'Inspect the captured log and output files in the working directory.'
            else:
                if state != 'cancelled' and fail_reason:
                    lines.append(f"Process: {fail_reason}")
                next_action = f'Use query_compute_job(task_id={task_id}) and the captured log to diagnose the failure before retrying.'
        elif state == 'done':
            lines.append('Physical Reality: Calculation finished; scientific verification is not implied.')
            next_action = 'Use log_parser on the native log to inspect energy, convergence and frequencies.'
            if job_type in {'gaussian', 'orca'} and log_path:
                from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts

                endpoints = await asyncio.to_thread(read_irc_endpoint_artifacts, log_path)
                if endpoints:
                    evidence.extend((f"IRC endpoint A: {endpoints['irc_end_a_path']}",
                                     f"IRC endpoint B: {endpoints['irc_end_b_path']}"))
                    next_action = ('Run unconstrained Opt from each canonical IRC endpoint XYZ, then Freq '
                        'at the agreed model; verify zero-imaginary minima and their identities. '
                        'A/B are path labels, not reactant/product assignments. Keep the native IRC and Opt/Freq logs.')
        else:
            if state != 'cancelled' and fail_reason:
                lines.append(f"Physical Reality: {fail_reason}")
            next_action = f'Use query_compute_job(task_id={task_id}) and the native log to diagnose the failure before retrying.'
        if state == 'cancelled':
            next_action = 'Do not resubmit or restart without a new explicit user request.'
        lines.append(f"NEXT: {next_action}")
        if evidence:
            lines.append('Evidence: ' + '; '.join(evidence))
        return '\n'.join(lines)
```


## cloudra/runtime_v2/compute_notify.py:498 — ComputeNotifyBroker._core_files_for

文件 SHA256: cb30c15658b3513b86e3c389c429cacddcc465146746cb23bda6175ff31e8855

```python
    async def _core_files_for(self, task_id: int) -> tuple[list[str], str]:
        """作业的核心证据文件与未落盘日志。

        返回 (files, missing_log)：输入文件总是入快照候选；日志按 GH #20
        同口径解析，但只有真实存在的才入候选——引擎惯例预测的日志可能
        从不落盘（如本机 ORCA stdout 构建），那不是"暂不可读"，标
        log_not_collected 但不进入重试循环。"""
        from cloudra.infra.compute_utils import resolve_log_path
        from cloudra.services.compute_store import aget_compute_job

        input_path = ""
        job_type = "gaussian"
        state = ""
        try:
            row = await aget_compute_job(ComputeDB(), task_id)
            if row:
                input_path = row["path"] or ""
                job_type = row["jobtype"] or job_type
                state = row['state']
        except Exception:
            return [], ""
        files = [input_path] if input_path else []
        missing_log = ""
        if input_path:
            from pathlib import Path

            log_path = await asyncio.to_thread(resolve_log_path, input_path, job_type=job_type, task_id=task_id)
            if log_path and await asyncio.to_thread(Path(log_path).is_file):
                if log_path not in files:
                    files.append(log_path)
                if state == 'done' and job_type in {'gaussian', 'orca'}:
                    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts

                    endpoints = await asyncio.to_thread(read_irc_endpoint_artifacts, log_path)
                    files.extend(path for path in endpoints.values() if path not in files)
            elif log_path:
                missing_log = log_path
        return files, missing_log
```


## cloudra/runtime_v2/compute_notify.py:537 — ComputeNotifyBroker._snapshot_core_evidence

文件 SHA256: cb30c15658b3513b86e3c389c429cacddcc465146746cb23bda6175ff31e8855

```python
    async def _snapshot_core_evidence(
        self,
        project_id: str,
        task_id: int,
        session_id: str | None,
    ) -> tuple[str, bool]:
        """终态通知前登记核心文件的不可变 ArtifactService 快照。

        返回 (note, complete)：可读的登记/复用快照（同一文件重复收集按
        hash 复用，同名覆盖的新内容是新 attempt 绝不合并）；不可读源
        显式标 evidence_unavailable（complete=False，进入静默重试，
        不吞异常假装可复查）。
        """
        from pathlib import Path

        from cloudra.persistence.artifacts import ArtifactService
        from cloudra.persistence.database import ConversationDB
        from cloudra.services import session_store

        files, missing_log = await self._core_files_for(task_id)
        if not files and not missing_log:
            return "", True
        owner_session = session_id
        if not owner_session:
            coordinator = self._coordinator_for(project_id)
            owner_session = coordinator.id if coordinator is not None else None
        if not owner_session:
            return "Evidence could not be recorded: no live session is available.", False
        # ArtifactService 要求 legacy session 行存在；runtime_v2 agent 不一定有，
        # 与 turn_pipeline 同一助手 get-or-create。
        await asyncio.to_thread(
            session_store.ensure_session_record,
            ConversationDB(project_id),
            owner_session,
            owner_session,
        )

        service = ArtifactService()
        lines: list[str] = []
        complete = True
        if missing_log:
            lines.append("Native output is not available yet.")
        for path_str in files:
            path = Path(path_str)
            try:
                await asyncio.to_thread(
                    service.snapshot_file,
                    conversation_id=project_id,
                    session_id=owner_session,
                    source=path,
                    allowed_root=path.parent,
                )
            except Exception as exc:
                complete = False
                logger.warning(
                    "compute evidence snapshot failed for job %s file %s: %s",
                    task_id, path_str, exc,
                )
                lines.append(f"Evidence could not be recorded: {path.name} ({type(exc).__name__}).")
                continue
        return "; ".join(lines), complete
```


## cloudra/dag/evidence_ingest.py:83 — snapshot_evidence_file

文件 SHA256: 988785294e907faf3280d2beb67ca5acf9a4c565f8dd8cf6abc44a4a24acafe6

```python
def snapshot_evidence_file(
    file_path: str | Path,
    workspace_root: str | Path,
    conversation_id: str | None = None,
) -> FileEvidenceSnapshot:
    """对工作区内证据文件进行安全沙箱检查、sha256 签名与不可变快照复制。"""
    root = Path(workspace_root).expanduser().resolve(strict=True)
    p = Path(file_path).expanduser()

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (root / p).resolve()

    if resolved.is_symlink():
        raise ValueError(f"Symlinks are not allowed as evidence: {file_path}")

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace boundary: {file_path}") from exc

    if not resolved.exists():
        raise FileNotFoundError(f"Evidence file does not exist: {file_path}")
    if not resolved.is_file():
        raise ValueError(f"Evidence path is not a regular file: {file_path}")

    data = resolved.read_bytes()
    sha256_hex = hashlib.sha256(data).hexdigest()
    file_size = len(data)

    evidence_dir = root / ".cloudra" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    is_qm, engine, freqs, imag_freqs, energy, normal_modes = _extract_qm_log(resolved)
    sidecars = []
    irc_endpoints = None
    if engine == "orca":
        from cloudra.tools.core import orca_frames
        try:
            orca_frames.extract_irc(str(resolved))
        except ValueError:
            pass
        else:
            irc_endpoints = orca_frames.extract_irc_endpoints(str(resolved))
            if not any(endpoint.get("geometry_ref") for endpoint in irc_endpoints.values()):
                raise ValueError(
                    "ORCA IRC output has no associated endpoint geometries. Submit the original IRC log "
                    "from the compute job directory with its native endpoint/trajectory files; "
                    "do not copy or rename the log alone. The evidence snapshot archives the bundle automatically."
                )
            for endpoint in irc_endpoints.values():
                if endpoint.get("geometry_ref"):
                    sidecar = Path(endpoint["geometry_ref"]).resolve(strict=True)
                    sidecar.relative_to(root)
                    sidecars.append((sidecar, hashlib.sha256(sidecar.read_bytes()).hexdigest()))
    elif engine == "gaussian":
        from cloudra.tools.core import gaussian_frames, orca_frames

        try:
            _, irc_meta = gaussian_frames.extract_irc(str(resolved))
        except ValueError:
            pass
        else:
            archived = orca_frames._archived_irc_endpoints(str(resolved))
            # Gaussian's real outer frames live in the hashed native log;
            # the shared archive retains binding without inventing XYZ files.
            irc_endpoints = archived or {
                direction: {"geometry_ref": None, "origin": "native_log",
                            "converged": irc_meta.get(f"{direction}_converged")}
                for direction in ("forward", "backward")
            }
    metadata = {}
    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.services.ts_pipeline_store import atom_binding_for_log
    atom_binding = irc_endpoints['forward'].get('atom_binding') if irc_endpoints else None
    if atom_binding is None:
        atom_binding = atom_binding_for_log(pipeline_database(), resolved, root)
    if atom_binding is not None:
        metadata['atom_binding'] = atom_binding
    if irc_endpoints is not None:
        manifest = {"log_sha256": sha256_hex, "endpoints": {}}
        if atom_binding is not None:
            manifest["atom_binding"] = atom_binding
        for direction, endpoint in irc_endpoints.items():
            original = endpoint.get("geometry_ref")
            match = next(((p, h) for p, h in sidecars if str(p) == original), None)
            manifest["endpoints"][direction] = {
                "filename": match[0].name if match else None,
                "sha256": match[1] if match else None,
                "origin": endpoint.get("origin"), "converged": endpoint.get("converged"),
            }
        bundle_hash = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
        evidence_dir = evidence_dir / bundle_hash
        evidence_dir.mkdir(parents=True, exist_ok=True)
        metadata["irc_sidecars"] = []
        for original, digest in sidecars:
            archived = evidence_dir / original.name
            if not archived.exists():
                shutil.copy2(original, archived)
            metadata["irc_sidecars"].append({"snapshot_path": str(archived), "sha256": digest})
        manifest_path = evidence_dir / "irc_endpoints.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest))
        metadata["irc_manifest"] = {"snapshot_path": str(manifest_path),
                                    "sha256": hashlib.sha256(json.dumps(manifest).encode()).hexdigest()}
    snapshot_filename = f"{sha256_hex[:16]}_{resolved.name}"
    snapshot_path = evidence_dir / snapshot_filename
    if not snapshot_path.exists():
        snapshot_path.write_bytes(data)
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != sha256_hex:
        raise ValueError('Evidence snapshot contents differ from their recorded hash.')
    if hashlib.sha256(resolved.read_bytes()).hexdigest() != sha256_hex:
        raise ValueError('Evidence file changed during snapshot; submit the settled file again.')
    # Parse the archived bytes rather than mutable source contents.
    is_qm, engine, freqs, imag_freqs, energy, normal_modes = _extract_qm_log(snapshot_path)
    if irc_endpoints is not None:
        from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

        metadata.update(write_irc_endpoint_artifacts(snapshot_path))

    return FileEvidenceSnapshot(
        original_path=str(resolved),
        snapshot_path=str(snapshot_path),
        sha256=sha256_hex,
        file_size=file_size,
        is_qm_log=is_qm,
        engine=engine,
        frequencies=freqs,
        imaginary_frequencies=imag_freqs,
        normal_modes=normal_modes,
        final_energy_hartree=energy,
        metadata={"filename": resolved.name, **metadata},
    )
```


## cloudra/dag/file_science.py:40 — _science_cache_key

文件 SHA256: e9d13617b41d3b889285362de0b97442cee880fadf3bf08c213a9fb643c7f8a7

```python
def _science_cache_key(store, graph, target_id, *, irc_files, workspace_root, evidence_refs, endpoint_refs):
    """Version only bound immutable dependencies; mutable workflow logs stay fresh."""
    from cloudra.dag.models import GraphRef

    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    if element is None:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        return None
    elements = [element]
    if hasattr(element, 'source_node_id'):
        elements.extend(node for node in graph.nodes
                        if node.node_id in (element.source_node_id, element.target_node_id))
    refs = []
    for item in elements:
        if item is element and evidence_refs is not None:
            refs.extend(evidence_refs)
        else:
            refs.extend([*item.refs, *[stage.ref for stage in item.stages
                                     if stage.ref is not None and stage.status.value == 'supported']])
    refs.extend(GraphRef.model_validate(ref) for ref in (endpoint_refs or {}).values())
    payloads = []
    for ref in dict.fromkeys(refs):
        try:
            payload = store.resolve_evidence(ref)
        except InvalidGraphReference:
            return None
        if not isinstance(payload, dict):
            continue
        if 'snapshot_path' not in payload:
            if (payload.get('arguments') or {}).get('log_path'):
                return None
            continue
        payloads.append(payload)
    payloads.extend((irc_files or {}).values())
    versions = {}
    for payload in payloads:
        snap = FileEvidenceSnapshot.model_validate(payload)
        paths = [snap.snapshot_path, *[item['snapshot_path'] for item in snap.metadata.get('irc_sidecars', [])]]
        if snap.metadata.get('irc_manifest'):
            paths.append(snap.metadata['irc_manifest']['snapshot_path'])
        recovery_paths = {snap.metadata[key] for key in ('irc_end_a_path', 'irc_end_b_path')
                          if snap.metadata.get(key)}
        paths.extend(recovery_paths)
        for raw in paths:
            path = Path(raw)
            try:
                stat = path.lstat() if raw in recovery_paths else path.stat()
            except OSError:
                versions[str(path)] = None
            else:
                versions[str(path)] = (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                                       stat.st_mtime_ns, stat.st_ctime_ns)
    payload = [graph.model_dump(mode='json'), target_id, str(workspace_root), payloads,
               [ref.model_dump(mode='json') for ref in evidence_refs] if evidence_refs is not None else None,
               irc_files, endpoint_refs, versions]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```


## cloudra/dag/file_science.py:323 — file_scientific_checks

文件 SHA256: e9d13617b41d3b889285362de0b97442cee880fadf3bf08c213a9fb643c7f8a7

```python
def file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None, use_cache=False) -> dict[str, dict]:
    """Reuse derived prompt checks only; submit/review/delivery always verify afresh."""
    options = dict(irc_files=irc_files, workspace_root=workspace_root,
                   evidence_refs=evidence_refs, endpoint_refs=endpoint_refs)
    key = _science_cache_key(store, graph, target_id, **options) if use_cache else None
    if key is not None:
        with _SCIENCE_CACHE_LOCK:
            cached = _SCIENCE_CACHE.get(key)
            if cached is not None:
                _SCIENCE_CACHE.move_to_end(key)
                return deepcopy(cached[0])
    checks = _file_scientific_checks(store, graph, target_id, **options)
    if key is not None and _science_cache_key(store, graph, target_id, **options) == key:
        size = len(json.dumps(checks).encode())
        if size <= _SCIENCE_CACHE_BYTES:
            with _SCIENCE_CACHE_LOCK:
                _SCIENCE_CACHE[key] = deepcopy(checks), size
                _SCIENCE_CACHE.move_to_end(key)
                while len(_SCIENCE_CACHE) > 64 or sum(item[1] for item in _SCIENCE_CACHE.values()) > _SCIENCE_CACHE_BYTES:
                    _SCIENCE_CACHE.popitem(last=False)
    return checks
```


## cloudra/dag/file_science.py:346 — _file_scientific_checks

文件 SHA256: e9d13617b41d3b889285362de0b97442cee880fadf3bf08c213a9fb643c7f8a7

```python
def _file_scientific_checks(store, graph, target_id: str, *, irc_files=None, workspace_root=None, evidence_refs=None, endpoint_refs=None) -> dict[str, dict]:
    element = next((n for n in graph.nodes if n.node_id == target_id), None)
    is_edge = element is None
    if is_edge:
        element = next((e for e in graph.edges if e.edge_id == target_id), None)
    if element is None:
        raise InvalidGraphReference(f"Delivery target {target_id!r} no longer exists in the current graph.")
    if evidence_refs is not None:
        element = element.model_copy(update={'refs': list(evidence_refs), 'stages': []})
    atom_bindings = {}
    parsed = {}
    logs, problems = _logs(store, element, workspace_root, atom_bindings=atom_bindings, parsed=parsed)
    if is_edge and endpoint_refs:
        from cloudra.dag.models import GraphRef
        refs = [GraphRef.model_validate(ref) for ref in endpoint_refs.values()]
        endpoint_logs, endpoint_problems = _logs(store, element.model_copy(update={'refs': refs, 'stages': []}), workspace_root, parsed=parsed)
        logs = [path for path in logs if path not in endpoint_logs]
        problems.extend(endpoint_problems)
    if not is_edge:
        return {'geometry': _species_minimum_check(element.smiles, logs, problems, parsed=parsed).model_dump()}
    frequencies = [_qm_data(p, parsed)[3] for p in logs]
    expected = 1 if is_edge else 0
    passed = any(f is not None and len(f) == expected for f in frequencies)
    status = 'passed' if passed else 'failed' if any(f is not None for f in frequencies) else 'incomplete'
    frequency_check = ScientificCheck(status=status,
        detail=f'Native normal termination and exactly {expected} imaginary frequencies required. ' + ' '.join(problems),
        next_action='' if passed else f'Submit a normally terminated frequency log showing {expected} imaginary frequencies; repair the calculation or supply missing evidence.')
    checks = {'frequency' if is_edge else 'geometry': frequency_check}
    if is_edge:
        checks['ts_opt'] = _ts_optimization_check(logs, parsed=parsed)
        source = next((n for n in graph.nodes if n.node_id == element.source_node_id), None)
        target = next((n for n in graph.nodes if n.node_id == element.target_node_id), None)
        source_logs, _ = _logs(store, source, workspace_root, parsed=parsed) if source else ([], [])
        target_logs, _ = _logs(store, target, workspace_root, parsed=parsed) if target else ([], [])
        def endpoint_candidates(key, node, candidates):
            node_candidates = candidates
            if endpoint_refs and key in endpoint_refs:
                from cloudra.dag.models import GraphRef
                ref = GraphRef.model_validate(endpoint_refs[key])
                if ref not in element.refs:
                    return []
                candidates, errors = _logs(store, element.model_copy(update={'refs': [ref], 'stages': []}), workspace_root, parsed=parsed)
                problems.extend(errors)
                # An explicit minimum fixes the final geometry, while a
                # separate bound Opt log supplies its native IRC starting frame.
                from cloudra.tools.core.irc_path import same_geometry
                minima = [_final_geometry(path) for path in candidates if _qm_data(path, parsed)[3] == []]
                candidates = list(dict.fromkeys([*candidates, *[path for path in node_candidates
                    if any(same_geometry(_final_geometry(path), minimum) for minimum in minima)]]))
            verified = []
            for path in candidates:
                try:
                    data = _qm_data(path, parsed)
                    if (node and node.smiles
                            and (data[3] == [] or _optimization_converged(path, data[1]) is True)
                            and any(_geometry_species(path, identity, diagnostics=problems)
                                    for identity in species_smiles(node.smiles))):
                        verified.append(path)
                except (ValueError, RuntimeError) as exc:
                    problems.append(str(exc))
            return verified
        source_logs = endpoint_candidates('endpoint_b', source, source_logs)
        target_logs = endpoint_candidates('endpoint_a', target, target_logs)
        charge = next((binding['charge'] for binding in atom_bindings.values() if 'charge' in binding), 0)
        if source_logs and source and source.smiles:
            from rdkit import Chem
            molecule = Chem.MolFromSmiles(chemical_smiles(source.smiles))
            if molecule is not None:
                charge = Chem.GetFormalCharge(molecule)
        details = list(problems)
        recovery = []
        irc_passed = False
        for path in logs:
            try:
                engine = _qm_data(path, parsed)[1]
                if engine == 'orca':
                    orca_frames.extract_irc(path)
                elif engine == 'gaussian':
                    gaussian_frames.extract_irc(path)
                else:
                    continue
            except ValueError:
                continue
            try:
                irc_passed, reason = verify_short_irc_direction(path, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details.extend(reason)
                if not irc_passed:
                    hint = irc_endpoint_recovery_hint(path)
                    if hint:
                        recovery.append(hint)
            except Exception as exc:
                details.append(f'IRC direction proof could not be evaluated: {exc}')
            if irc_passed:
                details = reason
                break
        if not irc_passed and irc_files and irc_files.get('irc_forward_file') and irc_files.get('irc_reverse_file'):
            forward = FileEvidenceSnapshot.model_validate(irc_files['irc_forward_file']).snapshot_path
            reverse = FileEvidenceSnapshot.model_validate(irc_files['irc_reverse_file']).snapshot_path
            if forward in logs and reverse in logs:
                irc_passed, reason = verify_short_irc_pair(forward, reverse, logs, target_logs, source_logs,
                    charge=charge, atom_bindings=atom_bindings, product_smiles=target.smiles if target else None,
                    reactant_smiles=source.smiles if source else None)
                details = reason if irc_passed else [*details, *reason]
        checks['short_irc'] = ScientificCheck(status='passed' if irc_passed else 'incomplete',
            detail=' '.join(details) or ('Native IRC outer-frame optimization to the declared verified minima passed.' if irc_passed else 'No usable bound bidirectional IRC evidence.'),
            next_action='' if irc_passed else 'Submit same-TS bidirectional IRC and native Opt/Freq logs connecting each outer frame to its declared minimum; geometric interval checks are advisory. Separated products need each declared species minimum. Full IRC convergence is not required.'
                + (' ' + ' '.join(dict.fromkeys(recovery)) if recovery else ''))
    return {stage: check.model_dump() for stage, check in checks.items()}
```


## cloudra/tools/core/irc_evidence.py:194 — irc_endpoint_geometries

文件 SHA256: 70beca90938b61881fbabee3ed3eabdc5cef9028fdd434465f67b9d2a64d645c

```python
def irc_endpoint_geometries(path) -> Optional[tuple]:
    """双侧 IRC 端点几何 ((symbols, positions) × 2)，ts_guess strict 口径。

    引擎非 gaussian/orca 或任一侧几何不可得时返回 None。"""
    p = Path(path)
    engine = qm_engine.detect_qm_engine(str(p))
    if engine == "gaussian":
        return gaussian_irc_endpoints_from_frames(irc_frames_for(p))
    if engine == "orca":
        return orca_irc_endpoint_geometries(p)
    return None
```


## cloudra/tools/core/irc_evidence.py:207 — irc_endpoint_recovery_hint

文件 SHA256: 70beca90938b61881fbabee3ed3eabdc5cef9028fdd434465f67b9d2a64d645c

```python
def irc_endpoint_recovery_hint(path) -> str:
    """Point to already exported native frames without mutating scientific evidence."""
    from cloudra.tools.core.irc_endpoint_artifacts import read_irc_endpoint_artifacts

    paths = read_irc_endpoint_artifacts(path)
    if not paths:
        return ''
    return (f'Canonical outer frames for IRC {path}: '
            + '; '.join(f'{key}={value}' for key, value in paths.items())
            + '. Use these XYZ files directly for unconstrained endpoint Opt, then Freq at each '
              'converged Opt geometry. A/B label native sides, not reactant/product identities; '
              'verify the optimized species. Recompute an Opt whose native starting geometry '
              'matches neither outer frame and its following Freq; new metadata cannot repair that calculation.')
```


## cloudra/tools/core/irc_evidence.py:483 — _endpoint_optimization_proof

文件 SHA256: 70beca90938b61881fbabee3ed3eabdc5cef9028fdd434465f67b9d2a64d645c

```python
def _endpoint_optimization_proof(ends, ts_geometry, source_logs, target_logs, *,
        charge=0, atom_binding=None, reactant_smiles=None, product_smiles=None):
    """Both real IRC sides must terminate in the declared verified minima via Opt."""
    from cloudra.tools.core.irc_path import align_atom_order

    details = []
    source = _optimized_minima(source_logs, smiles=reactant_smiles, side='SOURCE/reactant',
        charge=charge, details=details)
    target = _optimized_minima(target_logs, smiles=product_smiles, side='TARGET/product',
        charge=charge, details=details)
    for role, candidates in (('SOURCE/reactant', source), ('TARGET/product', target)):
        for start, _minimum, path in candidates:
            if not any(same_geometry(start, end) for end in ends):
                details.append(f'{role} Opt {path}: native starting geometry matches neither actual IRC '
                               'outer frame. Recompute this Opt from the exported canonical outer frame, '
                               'then rerun its Freq at the converged geometry; keep the original logs as unmatched source evidence.')
    for name, source_end, target_end in (('direct', ends[0], ends[1]), ('swapped', ends[1], ends[0])):
        for source_start, source_minimum, source_log in source:
            if not same_geometry(source_start, source_end):
                continue
            for target_start, target_minimum, target_log in target:
                if not same_geometry(target_start, target_end):
                    continue
                if atom_binding:
                    # Native Opt rows retain the correspondence of their actual IRC input.
                    # Reorder by the input match, never by similarity of the relaxed minimum.
                    mapping = atom_binding.get('atom_map', [])
                    count = len(ts_geometry[0])
                    if (len(mapping) != count or any(type(index) is not int for index in mapping)
                            or sorted(mapping) != list(range(1, count + 1))):
                        continue
                    source_order = align_atom_order(*source_end, *source_start)
                    target_order = align_atom_order(*target_end, *target_start)
                    if source_order is None or target_order is None:
                        continue
                    source_bound = (source_end[0], [source_minimum[1][index] for index in source_order[0]])
                    target_bound = (target_end[0], [target_minimum[1][index] for index in target_order[0]])
                    target_bound = ([target_bound[0][index - 1] for index in mapping],
                                    [target_bound[1][index - 1] for index in mapping])
                    if (not _ordered_graph_matches(source_bound, atom_binding['reactant_mol'], charge)
                            or not _ordered_graph_matches(target_bound, atom_binding['product_mol'], charge)):
                        details.append('Optimized IRC endpoints differ from the bound complete atom identities.')
                        continue
                result = [f'{name} pairing: both actual IRC outer frames were independently optimized '
                    f'to the correct zero-imaginary minima ({source_log}; {target_log}).']
                try:
                    interval = prove_irc_endpoint_direction(*ts_geometry, *ends, source_minimum, target_minimum,
                        [], charge, atom_orders=bound_atom_orders(ts_geometry, source_minimum, target_minimum, atom_binding))
                    result.extend('[advisory] ' + item for item in interval.get('details', []))
                    if not (interval['is_decidable'] and interval['is_match']):
                        result.append('[warning] Endpoint optimization establishes direction, but the geometric interval '
                            'check failed or is undecidable; inspect the trajectory for suspicious geometry.')
                except Exception as exc:
                    result.append(f'[warning] Endpoint optimization establishes direction, but the geometric interval '
                                  f'could not be evaluated ({exc}); inspect the trajectory.')
                return True, result
    return False, ['The actual IRC outer frames are not connected to both declared zero-imaginary minima '
                   'by converged optimization logs; geometric interval agreement alone is not direction proof.', *details]
```


## cloudra/tools/core/irc_evidence.py:543 — verify_short_irc_direction

文件 SHA256: 70beca90938b61881fbabee3ed3eabdc5cef9028fdd434465f67b9d2a64d645c

```python
def verify_short_irc_direction(
    irc_log,
    ts_logs: Sequence,
    endpoint_a_logs: Sequence,
    endpoint_b_logs: Sequence,
    *,
    charge: int = 0,
    atom_bindings=None,
    reactant_smiles: str | list[str] | None = None,
    product_smiles: str | list[str] | None = None,
) -> tuple[bool, list[str]]:
    """同一 TS 双向 IRC 的真实外帧经 Opt/Freq 到正确极小值即方向通过。

    材料：IRC 双侧端点与同一 TS 的单虚频日志；endpoint_a_logs /
    endpoint_b_logs 分别提供产物/反应物的 Opt/Freq 原生日志。首帧须匹配
    真实 IRC 外帧，收敛末帧须匹配零虚频几何，两侧可 direct/swapped 配对。

    返回 (passed, details)：passed=False 时 details 结构化写明缺哪份材料
    或证明为何不成立（缺 TS/端点材料 ⇒ 引导先补对应阶段的绑定证据）。
    """
    details: list[str] = []
    ends = irc_endpoint_geometries(irc_log)
    if ends is None:
        return False, [
            f"the IRC log {irc_log} does not yield usable endpoint geometries on "
            "both sides (Gaussian: outermost coordinated frames on the rx<0 and "
            "rx>0 sides; ORCA: endpoint files or outermost F/B trajectory frames — "
            "an unconverged direction's last frame is a legitimate partial "
            "endpoint); bind the parser output of a finished IRC job log"
        ]
    atom_binding = (atom_bindings or {}).get(str(irc_log))
    ts_geometries = [(geometry, (atom_bindings or {}).get(str(path)))
        for path in ts_logs
        for geometry in _usable_ts_geometries([path], details=details)]
    anchor = irc_start_geometry(irc_log)
    ts_geometries = [item for item in ts_geometries if same_geometry(item[0], anchor)]
    if not ts_geometries:
        details.append('IRC starting saddle is missing or differs from the submitted TS geometry; submit evidence from the same TS calculation geometry.')
    from_geometries = _usable_minimum_geometries(
        endpoint_b_logs, side="endpoint_b (SOURCE/reactant side)",
        details=details,
    )
    to_geometries = _usable_minimum_geometries(
        endpoint_a_logs, side="endpoint_a (TARGET/product side)",
        details=details,
    )
    if not ts_geometries:
        details.append(
            "missing TS material: bind the step's ts_opt/frequency stage evidence "
            "first (a normally terminated first-order saddle log with a final geometry)"
        )
    if not from_geometries:
        details.append(
            "missing endpoint_b material (SOURCE/reactant side): bind endpoint_b "
            "evidence or the source species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not to_geometries:
        details.append(
            "missing endpoint_a material (TARGET/product side): bind endpoint_a "
            "evidence or the target species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not (ts_geometries and from_geometries):
        return False, details
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for ts_geometry, ts_binding in ts_geometries:
            passed, proof_details = _endpoint_optimization_proof(
                ends, ts_geometry, endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None,
            )
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for ts_geometry, ts_binding in ts_geometries:
            verdict = verify_separated_product_direction(ends, ts_geometry, from_geometries,
                product_smiles, to_geometries, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict["is_match"]:
                return True, verdict["details"]
            details.extend(verdict["details"])
    hint = irc_endpoint_recovery_hint(irc_log)
    if hint:
        details.append(hint)
    return False, list(dict.fromkeys(details))
```


## cloudra/tools/core/irc_evidence.py:633 — verify_short_irc_pair

文件 SHA256: 70beca90938b61881fbabee3ed3eabdc5cef9028fdd434465f67b9d2a64d645c

```python
def verify_short_irc_pair(forward_log, reverse_log, ts_logs, endpoint_a_logs, endpoint_b_logs, *,
        atom_bindings=None, charge=0, reactant_smiles: str | list[str] | None = None,
        product_smiles: str | list[str] | None = None):
    """Combine native directional logs using the same endpoint-optimization proof."""
    def outer_geometry(path, direction):
        engine = qm_engine.detect_qm_engine(str(path))
        if engine == 'orca':
            orca_frames.extract_irc(str(path))
            endpoints = orca_frames.extract_irc_endpoints(str(path))
            for side in (direction, 'backward' if direction == 'forward' else 'forward'):
                xyz = orca_frames.read_endpoint_geometry(endpoints[side])
                if xyz:
                    return parse_xyz(xyz)
        elif engine == 'gaussian':
            frames = [f for f in irc_frames_for(path) if f.xyz.strip() and f.reaction_coordinate]
            preferred = [f for f in frames if (f.reaction_coordinate > 0) == (direction == 'forward')]
            candidates = preferred or frames
            if candidates:
                return parse_xyz(max(candidates, key=lambda f: abs(f.reaction_coordinate)).xyz)
        return None

    details = []
    try:
        forward = outer_geometry(forward_log, 'forward')
        reverse = outer_geometry(reverse_log, 'backward')
    except (ValueError, OSError) as exc:
        return False, [f'Directional IRC evidence could not be read: {exc}']
    if forward is None or reverse is None:
        return False, ['Both submitted directional logs must supply an outer endpoint geometry.']
    atom_binding = (atom_bindings or {}).get(str(forward_log))
    if atom_binding != (atom_bindings or {}).get(str(reverse_log)):
        atom_binding = None
    ts = [(geometry, (atom_bindings or {}).get(str(path))) for path in ts_logs
          for geometry in _usable_ts_geometries([path], details=details)]
    starts = [irc_start_geometry(path) for path in (forward_log, reverse_log)]
    ts = [item for item in ts if all(same_geometry(item[0], start) for start in starts)]
    source = _usable_minimum_geometries(endpoint_b_logs, side='SOURCE', details=details)
    target = _usable_minimum_geometries(endpoint_a_logs, side='TARGET', details=details)
    if not (ts and source):
        return False, [*details, 'Bind the TS and frequency-verified source/target minimum logs.']
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for geometry, ts_binding in ts:
            passed, proof_details = _endpoint_optimization_proof((forward, reverse), geometry,
                endpoint_b_logs, endpoint_a_logs, charge=charge,
                reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for geometry, ts_binding in ts:
            verdict = verify_separated_product_direction((forward, reverse), geometry, source,
                product_smiles, target, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict['is_match']:
                return True, verdict['details']
            details.extend(verdict['details'])
    return False, ['The paired IRC endpoint optimization proof is incomplete.', *details]
```


## cloudra/tools/core/irc_path.py:37 — same_geometry

文件 SHA256: 4b25f7bd0f132d1fa37b4ba2e0b4c1c9d42a7860ef0471159a1b99f2639731b5

```python
def same_geometry(reference, mobile) -> bool:
    """Same coordinates up to atom order and proper rigid rotation.

    Reuse the existing six-decimal XYZ rounding bound; this is identity of a
    calculation geometry, not a conformer or chemical similarity criterion.
    """
    import numpy as np

    if reference is None or mobile is None:
        return False
    ref_symbols, mob_symbols = reference[0], mobile[0]
    if len(ref_symbols) == 0 or sorted(ref_symbols) != sorted(mob_symbols):
        return False
    ref = np.asarray(reference[1], dtype=float)
    mob = np.asarray(mobile[1], dtype=float)
    ref = ref - ref.mean(axis=0)
    mob = mob - mob.mean(axis=0)
    tolerance = np.sqrt(3) * 10 ** -6

    def proper_rotation(left, right):
        u, _, vt = np.linalg.svd(left.T @ right)
        if np.linalg.det(u @ vt) < 0:
            u[:, -1] *= -1
        return u @ vt

    def matches(perm):
        ordered = mob[perm]
        residual = np.linalg.norm(ordered @ proper_rotation(ordered, ref) - ref, axis=1)
        return bool(np.max(residual) <= tolerance)

    alignment = align_atom_order(*reference, *mobile)
    if alignment is not None and matches(alignment[0]):
        return True

    # Distance-fingerprint ties can choose an improper symmetry, or mix several
    # symmetries. Keep the lineage-aware interval alignment above unchanged, but
    # search alternative strict-identity correspondences here. Two independent
    # centered vectors determine a proper rotation: at most n * (n - 1) anchor
    # pairs, rather than factorial permutations of equivalent atoms.
    d_ref, d_mob = dist_matrix(ref), dist_matrix(mob)
    fp_ref, fp_mob = np.sort(d_ref, axis=1), np.sort(d_mob, axis=1)
    compatible = np.array(mob_symbols)[:, None] == np.array(ref_symbols)[None, :]
    for i in range(len(ref_symbols)):
        # If each atom moves by at most tolerance, a pair distance changes by
        # at most twice that bound. This only prunes correspondence candidates;
        # the original proper-rotation residual remains the acceptance test.
        compatible[:, i] &= np.max(np.abs(fp_mob - fp_ref[i]), axis=1) <= 2 * tolerance
    if not np.all(np.any(compatible, axis=0)):
        return False

    first = int(np.argmax(np.linalg.norm(ref, axis=1)))
    cross = np.linalg.norm(np.cross(ref[first], ref), axis=1)
    second = int(np.argmax(cross))
    for mob_first in np.flatnonzero(compatible[:, first]):
        # Collinear geometries need only one axis; rotation about it is free.
        seconds = np.flatnonzero(compatible[:, second]) if cross[second] > 0 else [None]
        for mob_second in seconds:
            ref_anchors, mob_anchors = [first], [mob_first]
            if mob_second is not None:
                if mob_first == mob_second or abs(
                    d_ref[first, second] - d_mob[mob_first, mob_second]
                ) > 2 * tolerance:
                    continue
                ref_anchors.append(second)
                mob_anchors.append(mob_second)
            rotated = mob @ proper_rotation(mob[mob_anchors], ref[ref_anchors])
            cost = np.linalg.norm(rotated[:, None, :] - ref[None, :, :], axis=2)
            cost[~compatible] = 1e9
            perm = np.argmin(cost, axis=0).tolist()
            if len(set(perm)) != len(perm):
                perm = _hungarian(cost)
            if perm is not None and matches(perm):
                return True
    return False
```


## cloudra/tools/Chemtool/qm_input_writer.py:62 — QmInputWriter_input_schema

文件 SHA256: 010f9df1a69197aae441550531f8823986fcd1205fe2bb0c47c530bbee0cbef6

```python
class QmInputWriter_input_schema(QmCalculation, QmInputSettings, input_schema):
    engine: Literal["gaussian", "orca"] = Field(
        description="Target QM program. 'gaussian': write a .gjf (submit with job_type='gaussian'); "
                    "'orca': write a .inp (submit with job_type='orca'). "
                    "task_type and known basis aliases map onto each program's input syntax; "
                    "method and additional keywords must use that program's native spelling.",
    )
    source_type: Literal["smiles", "xyz_file", "mol_file"] = Field(
        description="Molecular-structure source type. "
                    "'smiles': generate 3D coordinates from a SMILES string; "
                    "'xyz_file': read coordinates from a .xyz file; "
                    "'mol_file': read coordinates from a .mol file."
    )
    source_value: str = Field(
        description="Molecular-structure source value. "
                    "When source_type='smiles', a SMILES string (e.g. 'CC(=O)O'); "
                    "when source_type='xyz_file' or 'mol_file', the file's path — "
                    "absolute as-is, or relative to the Agent working directory."
    )
    external_program: Optional[str] = Field(
        default=None,
        description="Explicit external MLIP route: declare method='ExtOpt' for ORCA or 'external' "
                    "for Gaussian, and basis_set=''. ORCA: absolute path of the "
                    "ProgExt executable — emits '! ExtOpt <tasks>' plus a %method ProgExt block, "
                    "e.g. '/opt/conda/envs/chemai/bin/mace'; the file must exist, be executable, "
                    "and live outside the working directory/data dir. Gaussian: engine value of the "
                    "external=\"...\" route keyword, e.g. 'mace' — a single [a-z0-9_.-] token, no "
                    "spaces or program arguments (they would bypass method-policy parsing)."
    )
    external_params: Optional[str] = Field(
        default=None,
        description="ORCA only, requires external_program: Ext_Params string handed to the external "
                    "program, e.g. '--model /abs/model --device cpu --dtype float64'. For Gaussian, "
                    "fold program arguments into external_program instead."
    )
    task_type: list[dict] = Field(
        default=[{"opt": None}],
        description='''List of dicts whose keys are job types and values are their parameters.
                    Common aliases: opt/freq/irc/single_point ('sp' is equivalent); other native task keys are preserved.
                    Gaussian example: [{"opt":"TS,readfc"},{"freq":None}]. ORCA opt='ts' maps to OptTS;
                    Gaussian-specific suboptions are preserved with warnings, not silently translated.
                    Use native keywords and orca_blocks for ORCA controls. Gaussian scan is rigid;
                    relaxed scans use opt=modredundant and end_setting, or ts_guess scan_prepare.'''
    )
    frequency_mode: Literal["auto", "analytic", "numeric"] = Field(
        default="auto",
        description="Frequency evaluation mode. ORCA: 'numeric' with task_type=[{'freq':None}] "
                    "emits NumFreq (required for external potentials); 'analytic'/'auto' emit Freq. "
                    "Warns when no frequency task is requested; explicit native evaluation options take precedence.",
    )

    orca_blocks: Optional[str] = Field(
        default=None,
        description="ORCA-only: raw % block lines inserted between the `!` line and the coordinate "
                    "block, e.g. '%geom MaxIter 200 end'. Scans use ts_guess mode='scan_prepare'. "
                    "Native atom indices are 0-based and refer to the exact XYZ order including explicit H. "
                    "For a SMILES source, use the generated build's "
                    "prepared_structure.json atom_identities, not SMILES heavy-atom positions. "
                    "For Gaussian this text is preserved in the trailing section with a warning."
    )
    title: str = Field(
        default="Gaussian job generated by Cloudra",
        description="Job title (Gaussian title line; ORCA has no title card — emitted as a comment)."
    )
    end_setting: str = Field(
        default="",
        description="Extra settings appended at the end of the file, e.g. mixed basis or scan setup. "
                    "Example: B 1 34 S 15 0.02"
    )
    output_path: str = Field(
        description="Path of the Gaussian .gjf or ORCA .inp file (including filename): absolute as-is, "
                    "or relative to the Agent working directory."
    )
    artifact_dir: Optional[str] = Field(
        default=None,
        description="Directory for the SMILES-source build artifacts (per-component structures, "
                    "optimization trajectories, prepared_structure.json). Default: "
                    "'<output_path parent>/structure_build/<stem>/' next to the generated input file. "
                    "Relative paths resolve against the Agent working directory."
    )
    chk_name: Optional[str] = Field(
        default=None,
        description="Gaussian checkpoint path. Omit to generate an absolute '<output stem>.chk' "
                    "next to output_path. Explicit paths are absolute as-is or relative to the Agent "
                    "working directory, like output_path; their parent directories are created before writing."
    )
    rwf_name: Optional[str] = Field(
        default=None,
        description="Gaussian scratch file path, often large. Absolute as-is or relative to the Agent "
                    "working directory; its parent directory is created before writing the input."
    )
    fchk_name: Optional[str] = Field(
        default=None,
        description="Gaussian formatted-checkpoint path. Absolute as-is or relative to the Agent "
                    "working directory; its parent directory is created before writing the input."
    )

    @model_validator(mode='after')
    def explicit_external_route(self):
        if self.external_program:
            required = 'extopt' if self.engine == 'orca' else 'external'
            if self.method.casefold() != required or self.basis_set:
                raise ValueError(f"external_program requires method='{required}' and basis_set='' for {self.engine}")
        return self
```


## cloudra/tools/Chemtool/qm_input_writer.py:638 — QmInputWriter.tool_call

文件 SHA256: 010f9df1a69197aae441550531f8823986fcd1205fe2bb0c47c530bbee0cbef6

```python
    async def tool_call(self, user_input: QmInputWriter_input_schema, session: Session) -> QmInputWriter_output_schema:
        if not _RDKIT_AVAILABLE:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="RDKit is not installed; cannot generate the input file. "
                        "Install it with: pip install 'cloudra[chem]', then retry."
            )
        if user_input.engine == "orca":
            try:
                self._orca_memory_mb(user_input.mem)
            except ValueError as exc:
                return QmInputWriter_output_schema(
                    is_success=False,
                    message=f"qm_input_writer refused: {exc}",
                    unapplied_options=[str(exc)],
                )
        # 外部 MLIP 路由的参数校验（fail-loud，不静默吞掉配错的字段）
        if user_input.external_params and not user_input.external_program:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params requires external_program: the Ext_Params string is only "
                        "meaningful together with a ProgExt executable. Set external_program, then retry.",
            )
        if user_input.external_params and user_input.engine == "gaussian":
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="external_params is ORCA-only; for the Gaussian external route the engine "
                        "value goes into external_program (e.g. external_program='mace').",
            )
        # 外部程序本身的安全校验：ORCA 可执行路径必须在 agent 可写范围之外，
        # Gaussian 引擎值必须能被 method_policy 词法解析（防白名单绕过）。
        if user_input.external_program:
            ext_error = await asyncio.to_thread(self._validate_external_program, user_input)
            if ext_error:
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=f"qm_input_writer refused: {ext_error}",
                )
        if 'task_type' not in user_input.model_fields_set:
            native_tasks, unknown_tasks = declared_native_tasks(user_input.model_dump(exclude={'task_type'}))
            if native_tasks or unknown_tasks:
                user_input = user_input.model_copy(update={'task_type': []})
        # Validate request semantics before SMILES embedding or coordinate
        # optimization, both of which can take minutes for an invalid job.
        advice = validate_writer_request(user_input.model_dump())
        conflicts = [entry for entry in advice if entry['severity'] == 'error']
        option_warnings = [entry for entry in advice if entry['severity'] == 'warning']
        if user_input.engine == 'orca':
            per_core = self._orca_memory_mb(user_input.mem) / user_input.nproc
            if per_core != int(per_core):
                option_warnings.append(dict(code='resource_memory_precision', field='mem', severity='warning',
                    message=f'ORCA maxcore uses integer MB per process; {per_core:g} MB per process is rendered as {int(per_core)} MB without increasing the requested total memory.'))
        if conflicts:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message="qm_input_writer refused: " + " | ".join(
                    f"[{c['code']}] {c['field']}: {c['message']}" for c in conflicts
                ),
                unapplied_options=[c["message"] for c in conflicts],
                warnings=option_warnings,
            )
        # 成功写出时在 interpreted_intent 里显式记录 scan 的刚性/松弛语义
        scan_semantics = None
        for task in user_input.task_type:
            if any(str(key).lower() == "scan" for key in task):
                scan_semantics = "rigid" if user_input.engine == "gaussian" else "relaxed"
                break
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径
        # 保持既有权限语义。SMILES 源不经过路径解析（绝不把 SMILES 当路径）。
        if user_input.source_type in ("xyz_file", "mol_file"):
            user_input.source_value = await asyncio.to_thread(resolve_tool_path, self, user_input.source_value)
        user_input.output_path = await asyncio.to_thread(resolve_tool_path, self, user_input.output_path)
        if user_input.engine == 'gaussian':
            for field in ('chk_name', 'rwf_name', 'fchk_name'):
                value = getattr(user_input, field)
                if value is not None:
                    setattr(user_input, field, await asyncio.to_thread(resolve_tool_path, self, value))
        if user_input.artifact_dir:
            user_input.artifact_dir = await asyncio.to_thread(resolve_tool_path, self, user_input.artifact_dir)
        else:
            base = os.path.dirname(user_input.output_path)
            stem = os.path.splitext(os.path.basename(user_input.output_path))[0]
            # 与 smiles_to_mol / conformer_search 同一命名规则：<父目录>/structure_build/<stem>/
            user_input.artifact_dir = build_artifact_dir(base or ".", stem)
        try:
            # 结构构建是重活（Embed/优化），离开事件循环线程
            mol, seed_note = await asyncio.to_thread(
                self._get_molecule, user_input, user_input.artifact_dir
            )
            content = await asyncio.to_thread(self.render_input, user_input, mol)
            if user_input.engine == "orca":
                engine_label = "ORCA"
                generation_path = "orca:simple+orca_blocks"
            else:
                engine_label = "Gaussian"
                generation_path = "gaussian:route"

            # 不信 writer 自述：从生成文本重新 inspect，任务集合不一致即失败。
            inspected = inspect_input(content, engine=user_input.engine)
            interpreted = inspected.model_dump(mode="json")
            if scan_semantics is not None:
                interpreted["scan_semantics"] = scan_semantics
            if inspected.certainty == 'unknown':
                option_warnings.append(dict(code='unclassified_native_intent', field='keywords', severity='warning',
                    message='The native task could not be classified; the original declaration is preserved. Inspect the engine input before interpreting results.'))
            written_calculation = self._written_calculation(user_input)
            render_errors = self.validate_rendered_input(user_input, content, charge=total_charge(mol))
            if render_errors:
                task_differences = sorted(inspected.tasks ^ intent_from_writer(user_input.model_dump()).tasks)
                return QmInputWriter_output_schema(is_success=False,
                    message='qm_input_writer internal mismatch: ' + ' | '.join(render_errors),
                    interpreted_intent=interpreted, unapplied_options=[*task_differences, *render_errors], warnings=option_warnings)

            limitation = seed_note
            if "ts_opt" in inspected.tasks and inspected.constraints:
                limitation += (
                    " NOTE: this input keeps constraints during a TS optimization; "
                    "the result may only be claimed as a CONSTRAINED saddle point, "
                    "not a full-space transition state."
                )

            parent_dir = os.path.dirname(user_input.output_path)
            if parent_dir:
                try:
                    await asyncio.to_thread(os.makedirs, parent_dir, exist_ok=True)
                except FileExistsError:
                    # exist_ok=True 仍会在叶子已存在且不是目录时炸 Errno 17——
                    # 必须翻译成有指引的报错，不把裸 errno 抛给调用方
                    return QmInputWriter_output_schema(
                        is_success=False,
                        input_path="",
                        message=(
                            f"Cannot create the output directory {parent_dir}: a non-directory "
                            "file already exists at that path. Choose a different output_path, "
                            "or remove the conflicting file, then retry."
                        ),
                    )
            input_path = user_input.output_path
            if user_input.engine == 'gaussian':
                await asyncio.to_thread(self._prepare_gaussian_file_parents, user_input)

            # 同路径重复生成：内容逐字节相同 → 幂等复用；不同 → fail-loud 给指引，
            # 绝不静默覆盖一份来源不明的既有文件。
            if await asyncio.to_thread(os.path.isfile, input_path):
                existing = await asyncio.to_thread(Path(input_path).read_bytes)
                if existing == content.encode("utf-8"):
                    return QmInputWriter_output_schema(
                        is_success=True,
                        input_path=input_path,
                        message=(
                            f"{engine_label} input file already exists with identical content; "
                            f"reused it as-is.{limitation}"
                        ),
                        interpreted_intent=interpreted,
                        calculation=written_calculation,
                        warnings=option_warnings,
                        unapplied_options=[],
                        generation_path=generation_path,
                    )
                return QmInputWriter_output_schema(
                    is_success=False,
                    input_path="",
                    message=(
                        f"Refused to overwrite {input_path}: a file already exists there with "
                        "different content. Choose a different output_path, or delete the "
                        "existing file first, then retry."
                    ),
                )

            await asyncio.to_thread(atomic_write_text, input_path, content)

            return QmInputWriter_output_schema(
                is_success=True,
                input_path=input_path,
                message=f"{engine_label} input file generated successfully.{limitation}",
                interpreted_intent=interpreted,
                calculation=written_calculation,
                warnings=option_warnings,
                unapplied_options=[],
                generation_path=generation_path,
            )
        except StructureBuildRefused as e:
            details = " | ".join(e.diagnostics) if e.diagnostics else e.message
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=(
                    f"qm_input_writer refused to write the file: the SMILES source could not be "
                    f"turned into a usable structure (build status: {e.status}). {e.message}"
                    + (f" Diagnostics: {details}" if details and details != e.message else "")
                    + f" Build artifacts: {e.artifact_path}"
                ),
            )
        except FileNotFoundError as e:
            missing = e.filename or user_input.source_value
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Coordinate source file not found: {missing}. "
                        "Check the path, or generate the structure first with smiles_to_mol / format_converter."
            )
        except FileExistsError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Output path conflict: {e.filename or user_input.output_path} already exists "
                        "and cannot be created as a directory. Choose a different output_path, "
                        "or remove the conflicting file, then retry."
            )
        except ValueError as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Invalid input for qm_input_writer: {str(e)}. "
                        "Correct the reported field or coordinate source, then retry."
            )
        except Exception as e:
            return QmInputWriter_output_schema(
                is_success=False,
                input_path="",
                message=f"Failed to generate the {user_input.engine.upper()} input file: {str(e)}. "
                        "Verify the coordinate source and output path, then retry."
            )
```


## cloudra/tools/core/ts_process.py:2497 — _write_endpoint_input

文件 SHA256: 5d92cbd59138507089a304e3814750b598c0950c690e62b0ac57f9830bb32d2f

```python
def _write_endpoint_input(record: TsProcessRecord, job_dir: str,
                          role: Literal["reactant", "product"],
                          task: Literal["opt", "frequency"]) -> tuple[str, str]:
    """Write endpoint Opt from a declared species seed or native IRC outer frame.

    Record the actual source when writing; a Freq inherits its accepted Opt
    provenance and uses that converged geometry. Roles and IRC A/B are distinct.
    """
    from cloudra.tools.Chemtool.qm_input_writer import QmInputWriter, QmInputWriter_input_schema

    calculation = stage_calculation(record, f'{role}_{task}')
    if calculation is None:
        return f'Explicit {_calculation_field(f"{role}_{task}")} required', ''
    endpoint = getattr(record.input.verification, role + '_endpoint')
    provenance = None
    normalized_source = None
    if task == 'opt' and endpoint.seed is not None:
        path = _workspace_input_path(record, endpoint.seed.xyz_path)
        source = str(path)
        for reference in endpoint.seed.evidence_refs:
            artifact = _workspace_input_path(record, reference)
            if not artifact.is_file():
                return 'Endpoint replacement source/evidence missing', ''
        if not path.is_file():
            return 'Endpoint replacement source/evidence missing', ''
        try:
            atoms = _endpoint_seed_atoms(record, role, endpoint.seed)
        except (OSError, ValueError) as exc:
            return str(exc), ''
        normalized_source = '\n'.join([str(len(atoms)), 'Endpoint seed in TS working atom order',
            *[symbol + ' ' + ' '.join(repr(float(value)) for value in point) for symbol, point in atoms]]) + '\n'
        provenance = dict(kind='species_reference', label=role)
    elif task == "opt":
        irc_step = next(
            (step for step in reversed(record.job_steps) if step.purpose == "irc"), None,
        )
        if irc_step is None or irc_step.state != "done":
            return "a completed IRC job is required before optimizing its outer frames", ""
        irc_log = _refinement_log_path(record, irc_step)
        if not os.path.isfile(irc_log):
            return f"the IRC job log is missing at {irc_log}", ""
        from cloudra.tools.Chemtool.ts_guess import TsGuess

        checks: list[str] = []
        try:
            info = TsGuess._extract_irc_endpoints(
                irc_log, checks, engine=_step_calculation(record, irc_step).engine,
                output_dir=os.path.join(record.run_dir, VERDICT_STAGE_DIR), require_two_sides=True,
            )
        except Exception as exc:
            return f"IRC outer-frame extraction failed: {exc}", ""
        if info is None:
            return "IRC has no usable outer geometry on both sides: " + "; ".join(checks), ""
        for side in ('A', 'B'):
            source = info['path_' + side.lower()]
            if not source or not os.path.isfile(source):
                return f"IRC side {side} outer frame is missing", ""
        side = _irc_side_for_role(record, info, role)
        source = info['path_' + side.lower()]
        import hashlib
        provenance = dict(kind='irc_outer_frame', label=side,
            irc_job_id=irc_step.external_source['source_job_id'] if irc_step.external_source else irc_step.job_id,
            irc_log_sha256=hashlib.sha256(Path(irc_log).read_bytes()).hexdigest())
    else:
        opt_step = next(
            (step for step in reversed(record.job_steps) if step.purpose == f"{role}_opt"),
            None,
        )
        if opt_step is None:
            return f"{role} has no optimization job; refusing frequency on a raw seed", ""
        xyz, error = _endpoint_opt_frame(record, opt_step)
        if error:
            return f"{role} {error}", ""
        if opt_step.endpoint_source is None:
            return f'{role} accepted optimization has no endpoint source provenance', ''
        provenance = opt_step.endpoint_source.model_dump()
        source = os.path.join(job_dir, "optimized.xyz")
        atomic_write_text(source, xyz.rstrip() + "\n")

    source_copy=os.path.join(job_dir,f'{role}_source.xyz')
    _write_immutable_input(source_copy, normalized_source if normalized_source is not None else Path(source).read_text())
    source=source_copy
    import hashlib
    if task == 'opt':
        provenance.update(source_path=source_copy, sha256=hashlib.sha256(Path(source_copy).read_bytes()).hexdigest())
    _write_immutable_input(os.path.join(job_dir, 'endpoint_source.json'),
        EndpointSource.model_validate(provenance).model_dump_json())
    declaration = record.input.reaction
    origin_label = (
        'IRC side ' + provenance['label']
        if provenance['kind'] == 'irc_outer_frame' else 'explicit species seed'
    )
    calc_copy, task_type = _stage_writer_tasks(calculation,
        [{'opt': None}] if task == 'opt' else [{'freq': None}])
    name = f"{role}_{task}.{'inp' if calculation.engine == 'orca' else 'gjf'}"
    input_path = os.path.join(job_dir, name)
    request = QmInputWriter_input_schema(
        **calc_copy.model_dump(mode='json'),
        nproc=record.compute_cpus,
        mem=f"{record.compute_memory_mb}MB",
        source_type="xyz_file", source_value=source,
        task_type=task_type,
        charge=declaration.charge, multiplicity=declaration.multiplicity,
        electronic_character=declaration.electronic_character,
        title=f"Endpoint {role} {task} from {origin_label}; identity unverified | declared_species: {getattr(declaration, role + '_smiles')}",
        output_path=input_path,
    )
    conflicts = _writer_request_errors(record, f'{role}_{task}', request)
    if conflicts:
        return f"{role} {task} input refused: " + " | ".join(
            f"[{item['code']}] {item['message']}" for item in conflicts
        ), ""
    frame = read_molecule(source, charge=declaration.charge)
    reference = path_endpoints(record.structures)[0 if role == 'reactant' else 1]
    if [a.GetSymbol() for a in reference.GetAtoms()] != [a.GetSymbol() for a in frame.GetAtoms()]:
        return f'{role} endpoint frame differs from the owned atom identities', ''
    molecule = with_positions(reference, frame.GetConformer().GetPositions())
    content = QmInputWriter.render_input(request, molecule)
    error = _writer_render_error(record, f'{role}_{task}', request, content)
    if error:
        return error, ''
    _write_immutable_input(input_path, content)
    return "", input_path
```
