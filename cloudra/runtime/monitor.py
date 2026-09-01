import argparse
import asyncio
import io
import os
import subprocess
import sys
from pathlib import Path

from cloudra.infra.compute_utils import (
    build_calculator_cmd,
    calc_lock_path,
    check_job_type,
    get_log_path,
    guard_lock_path,
)
from cloudra.infra.flocks import try_acquire_lock
from cloudra.infra.platform_utils import is_posix
from cloudra.persistence.database import ComputeDB
from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.services.compute_store import afinalize_compute_job, aupdate_compute_pid

_LOG_TAIL_CHARS = 8000
_REASON_MAX_CHARS = 500
# 终止标记：Gaussian "Error termination"、CP2K "PROGRAM FAILED/ABORT" 等
_FAILURE_MARKERS = ("Error termination", "PROGRAM FAILED", "ABORT", "Error:", "ERROR")
# adopt 模式等 calc 锁释放的探测间隔（秒）
_ADOPT_POLL_SECONDS = 5
# calculator 的 nice 降权幅度：CPU 打满时控制面（API/调度守护）按 CFS 权重
# 优先分到时间片，状态同步链路不被计算任务饿死。降权不需要特权。
_CALC_NICE_LEVEL = 10


def _lower_sched_priority() -> None:
    """calculator 子进程 preexec：nice 降权（exec 后仍然继承，POSIX only）。"""
    os.nice(_CALC_NICE_LEVEL)


def _log_tail_reason(log_path: Path) -> str:
    """从计算日志尾部提取可读的失败原因。

    失败信息的可观测性不能只靠 agent 手动 grep：guard 落库/写 state json 时
    把终止标记段（上下文两行）或末尾三行作为 reason 带上。
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""
    lines = [line.strip() for line in text[-_LOG_TAIL_CHARS:].splitlines() if line.strip()]
    picked: list[str] = []
    for i, line in enumerate(lines):
        if any(marker in line for marker in _FAILURE_MARKERS):
            picked.extend(lines[max(0, i - 2): i + 2])
    if not picked:
        picked = lines[-3:]
    # 保序去重（标记段的上下文行可能重叠）
    seen: set[str] = set()
    unique = [line for line in picked if not (line in seen or seen.add(line))]
    return " | ".join(unique)[:_REASON_MAX_CHARS]


async def _parse_log(log_path: Path, parse_timeout: int, job_type: str = "gaussian"):
    """尝试解析日志，返回 (data_dic, is_success) 或 (None, None) 表示失败。

    Guard 在 calculator 已退出后才调用本函数，日志应已写完；``parse_timeout``
    仅保留 CLI 兼容，实际只做少量短间隔重试（应对文件系统延迟），不会空转半小时。
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        print(f'日志文件不存在或为空：{log_path}')
        return None, None

    if job_type == "cp2k":
        # cclib 1.8.x 已移除 CP2K 解析器，这里用轻量文本解析兜底。
        return _parse_cp2k_log(log_path)

    import cclib

    max_attempts = 5
    retry_sleep = 1.0
    last_error = None
    for attempt in range(max_attempts):
        try:
            data = cclib.io.ccread(log_path)
            if data is None:
                print(f'cclib 无法识别日志格式：{log_path}')
                return None, None
            # cclib 1.8+ 会容忍缺坐标/原子序数的日志并继续返回对象，但 ccwrite
            # 会抛 'Must pass at least one of atomcoords or atomnos'；旧版 cclib
            # 在 ccread 阶段就抛 AttributeError。统一在解析后做必需字段检查，
            # 避免 CI/本地版本差异导致的行为分歧。
            if not hasattr(data, 'atomcoords') or not hasattr(data, 'atomnos'):
                print(f'日志缺少原子坐标或原子序数，视为不完整：{log_path}')
                return None, None
            is_success = data.metadata.get('success', False)
            try:
                state_str = cclib.io.ccwrite(data, outputtype="cjson")
                state_CJSON = cclib.io.cjsonreader.CJSON(io.StringIO(state_str))
                data_dic = state_CJSON.parse()
            except Exception as e:
                print(f'日志解析后转换失败：{e}')
                return None, None
            data_dic.pop('atomcoords', None)
            data_dic['is_success'] = is_success
            return data_dic, is_success
        except Exception as e:
            last_error = e
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(retry_sleep)
    print(f'日志解析失败：{last_error}')
    return None, None


def _parse_cp2k_log(log_path: Path) -> tuple[dict, bool] | None:
    """轻量解析 CP2K 输出日志（.out）。

    成功判据：日志包含 ``PROGRAM ENDED`` 且未出现 ``PROGRAM FAILED`` /
    ``ABORT`` 等终止标记；并提取最后一次 FORCE_EVAL 总能量。
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 CP2K 日志失败：{e}')
        return None
    if not text.strip():
        return None

    normal = "PROGRAM ENDED" in text
    aborted = any(
        marker in text
        for marker in ("PROGRAM FAILED", "ABORT", "PROGRAM TERMINATED")
    )
    is_success = normal and not aborted

    energy = None
    for line in reversed(text.splitlines()):
        if "ENERGY| Total FORCE_EVAL" in line and "energy [a.u.]" in line:
            tokens = line.split()
            if tokens:
                try:
                    energy = float(tokens[-1])
                except ValueError:
                    pass
            break

    data_dic: dict = {
        "is_success": is_success,
        "total_energy_hartree": energy,
    }
    if energy is not None:
        data_dic["scf_energy_hartree"] = energy
        data_dic["scf_energy_ev"] = energy * 27.211386245988
    return data_dic, is_success


async def _register_pid(db: ComputeDB, taskid: int, column: str, pid: int):
    """登记 guard/calc PID。仅作观测取证（agent 可自行 ps 排查），不参与存活判定。"""
    try:
        await aupdate_compute_pid(db, taskid, column, pid)
    except Exception as e:
        print(f'[guard] 登记 {column} 失败（已忽略）: {e}')


async def _finalize(
    db: ComputeDB,
    taskid: int,
    log_path: Path,
    workdir: str,
    parse_timeout: int,
    job_type: str,
    returncode: int | None,
):
    """calculator 退出后的统一收尾：解析日志 → 写 state json → CAS 落库 → 入箱。

    终态通知由 API 进程的 ComputeNotifyBroker 轮询 compute_jobs 表补投，
    guard 不再发进程间事件。
    """
    data_dic, is_success = await _parse_log(log_path, parse_timeout, job_type=job_type)
    if data_dic is None:
        reason = _log_tail_reason(log_path)
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
        fail_reason = (
            f"calculator 退出码 {returncode}；" if returncode else ""
        ) + (_log_tail_reason(log_path) or "未在日志尾部找到明确错误段")
        data_dic["error"] = fail_reason

    json_nm = f'state_{taskid}.json'
    json_path = os.path.join(workdir, json_nm)
    try:
        atomic_write_json(json_path, data_dic, indent=4)
    except Exception as e:
        print(f'写入 json 失败：{e}')
        await _mark_failed(db, taskid, f"写入 state json 失败：{e}")
        return

    try:
        # CAS：同步路径 run_now 或其他收尾方已写终态时不覆盖
        await afinalize_compute_job(db, taskid, state, last_error=fail_reason or None)
        print(f'[guard] 数据库状态已更新: task_id={taskid}, state={state}')
    except Exception as e:
        print(f'[guard] 更新数据库失败：{e}')
        return

    # D5/D11：dag 模式下计算作业终态入 CallReview 收件箱（带作业终态，
    # 不是 submit 调用的成败）；standard 模式内部跳过。
    try:
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(taskid, state)
    except Exception as e:
        print(f'[guard] enqueue compute review 失败（已忽略）: {e}')


async def run_guard(
    taskid: int,
    path: str,
    conv_id: str,
    parse_timeout: int,
    db_path: str,
    job_type: str = "gaussian",
):
    """
    Guard：calculator 的父进程。

    0. 对 guard-<id>.lock 持排他 flock（进程死内核放锁）——OS 级防重 + 存活证据。
    1. 经 calc_lock_wrapper 启动 calculator 并 wait()（事件驱动，不再轮询 mtime）。
    2. calculator 退出后，在 parse_timeout 窗口内尝试解析日志。
    3. 解析成功则写 state.json、更新数据库、注入事件；失败则标记 failed。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ComputeDB.from_path(db_path)

    guard_fd = try_acquire_lock(guard_lock_path(workdir, taskid))
    if guard_fd is None:
        print(f'[guard] task {taskid} 已有 guard 持锁在管，退出（OS 级防重）')
        return
    try:
        await _register_pid(db, taskid, "guard_pid", os.getpid())

        ok, msg = check_job_type(job_type, workdir)
        if not ok:
            print(f'[guard] 环境检查失败：{msg}')
            await _mark_failed(db, taskid, msg)
            return

        ok, calculator_cmd, msg = build_calculator_cmd(path, job_type=job_type)
        if not ok:
            print(f'[guard] 无法构建 calculator 命令：{msg}')
            await _mark_failed(db, taskid, msg)
            return

        # 启动 calculator；start_new_session 保证 guard 意外退出时 calculator 不被连带杀死。
        # Windows 不支持 start_new_session，仅 POSIX 传入。
        from cloudra.infra.compute_utils import (
            allocate_gaussian_scratch,
            cleanup_gaussian_scratch,
        )

        calc_env = os.environ.copy()
        scratch_dir = None
        if job_type == "gaussian":
            scratch_dir = allocate_gaussian_scratch(taskid, workdir)
            calc_env["GAUSS_SCRDIR"] = str(scratch_dir)
            print(f'[guard] Gaussian scratch: {scratch_dir}')

        # calculator 必须经锁 wrapper 拉起：calc-<id>.lock 跨 exec 继承，
        # calculator 全家存续期间锁有效——这是对账判定"计算是否还在跑"的唯一权威。
        wrapped_cmd = [
            sys.executable,
            "-m",
            "cloudra.runtime.calc_lock_wrapper",
            calc_lock_path(workdir, taskid),
            "--",
            *calculator_cmd,
        ]
        calc_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "cwd": workdir,
            "env": calc_env,
        }
        if is_posix():
            calc_kwargs["start_new_session"] = True
            calc_kwargs["preexec_fn"] = _lower_sched_priority
        returncode: int | None = None
        try:
            calc_proc = await asyncio.create_subprocess_exec(*wrapped_cmd, **calc_kwargs)
            await _register_pid(db, taskid, "calc_pid", calc_proc.pid)
            print(f'[guard] calculator 启动 (PID {calc_proc.pid})，等待其结束...')
            returncode = await calc_proc.wait()
            print(f'[guard] calculator 退出，退出码：{returncode}')
        finally:
            # 必须在 g16 退出后再清；运行中删除会制造 FileIO / 假“输入被删”。
            cleanup_gaussian_scratch(scratch_dir)

        await _finalize(db, taskid, log_path, workdir, parse_timeout, job_type, returncode)
    finally:
        os.close(guard_fd)


async def run_adopt(
    taskid: int,
    path: str,
    conv_id: str,
    parse_timeout: int,
    db_path: str,
    job_type: str = "gaussian",
):
    """对账接管：guard 已死但作业仍 running 时由调度器拉起。

    不启动新计算：阻塞等 calc 锁释放（内核保证进程死锁必放，无死等），
    然后走与正常 guard 完全相同的解析/落库/通知路径。calc 锁未被持有
    （guard 死在 spawn 前或 calc 已结束）时立即进入解析——日志缺失或
    不可解析则置 failed。全程零 PID 探测。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ComputeDB.from_path(db_path)

    guard_fd = try_acquire_lock(guard_lock_path(workdir, taskid))
    if guard_fd is None:
        print(f'[guard adopt] task {taskid} 已有 guard 持锁在管，退出')
        return
    try:
        await _register_pid(db, taskid, "guard_pid", os.getpid())
        calc_lock = calc_lock_path(workdir, taskid)
        while True:
            calc_fd = try_acquire_lock(calc_lock)
            if calc_fd is not None:
                os.close(calc_fd)
                break
            print(f'[guard adopt] calc 锁仍被持有，calculator 还在跑；{_ADOPT_POLL_SECONDS}s 后再探...')
            await asyncio.sleep(_ADOPT_POLL_SECONDS)
        await _finalize(db, taskid, log_path, workdir, parse_timeout, job_type, None)
    finally:
        os.close(guard_fd)


async def _mark_failed(
    db: ComputeDB,
    taskid: int,
    message: str,
):
    """将任务标记为 failed，错误信息同时落 last_error（query_compute_job 直接可读）。"""
    print(f'Error: {message}')
    try:
        await afinalize_compute_job(db, taskid, 'failed', last_error=message[:500])
    except Exception as e:
        print(f'[guard] 标记 failed 失败：{e}')
        return
    # D5/D11：失败终态同样入 CallReview 收件箱（rev_compute_<id> 去重）
    try:
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(taskid, 'failed')
    except Exception as e:
        print(f'[guard] enqueue compute review 失败（已忽略）: {e}')
    # 早期失败（环境检查等）的终态通知由 ComputeNotifyBroker 轮询补投，
    # guard 不再发进程间事件。


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--path', type=str, required=True)
    parser.add_argument('--conv_id', type=str, required=True)
    parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    parser.add_argument('--job_type', type=str, default='gaussian')
    parser.add_argument('--adopt', action='store_true',
                        help='对账接管模式：不启动新计算，等 calc 锁释放后收尾')
    args = parser.parse_args()

    runner = run_adopt if args.adopt else run_guard
    asyncio.run(runner(
        taskid=args.task_id,
        path=args.path,
        conv_id=args.conv_id,
        parse_timeout=max(60, args.timeout),
        db_path=args.db_path,
        job_type=args.job_type,
    ))
