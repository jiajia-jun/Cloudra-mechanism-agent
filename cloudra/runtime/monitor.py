import argparse
import asyncio
import io
import os
import subprocess
import time
from pathlib import Path

from cloudra.infra.compute_utils import build_calculator_cmd, check_job_type, get_log_path
from cloudra.infra.platform_utils import is_posix
from cloudra.persistence.database import ConversationDB
from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.runtime.compute_notify import (
    build_compute_finish_content,
    emit_compute_task_finished,
    resolve_submission_info,
)

_LOG_TAIL_CHARS = 8000
_REASON_MAX_CHARS = 500
# 终止标记：Gaussian "Error termination"、CP2K "PROGRAM FAILED/ABORT" 等
_FAILURE_MARKERS = ("Error termination", "PROGRAM FAILED", "ABORT", "Error:", "ERROR")


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

    1. 启动 calculator 子进程并 wait()（事件驱动，不再轮询 mtime）。
    2. calculator 退出后，在 parse_timeout 窗口内尝试解析日志。
    3. 解析成功则写 state.json、更新数据库、注入事件；失败则标记 failed。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ConversationDB.from_path(db_path)

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

    calc_kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": workdir,
        "env": calc_env,
    }
    if is_posix():
        calc_kwargs["start_new_session"] = True
    try:
        calc_proc = await asyncio.create_subprocess_exec(*calculator_cmd, **calc_kwargs)
        print(f'[guard] calculator 启动 (PID {calc_proc.pid})，等待其结束...')
        returncode = await calc_proc.wait()
        print(f'[guard] calculator 退出，退出码：{returncode}')
    finally:
        # 必须在 g16 退出后再清；运行中删除会制造 FileIO / 假“输入被删”。
        cleanup_gaussian_scratch(scratch_dir)

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
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?",
                (state, time.time(), fail_reason or None, taskid)
            )
            await con.commit()
        print(f'[guard] 数据库状态已更新: task_id={taskid}, state={state}')
    except Exception as e:
        print(f'[guard] 更新数据库失败：{e}')
        return

    # D5/D11：dag 模式下计算作业终态入 CallReview 收件箱（带作业终态，
    # 不是 submit 调用的成败）；standard 模式内部跳过。
    try:
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(db, taskid, state)
    except Exception as e:
        print(f'[guard] enqueue compute review 失败（已忽略）: {e}')

    info = await resolve_submission_info(db, taskid)
    event_content = build_compute_finish_content(
        task_id=taskid,
        state=state,
        input_path=str(info.get("path") or ""),
        log_path=str(log_path),
        json_path=json_path,
        fail_reason=fail_reason,
    )
    emit_compute_task_finished(
        conv_id,
        task_id=taskid,
        state=state,
        content=event_content,
        session_id=info.get("session_id"),
        notify_coordinator=True,
    )
    print(f'[guard] compute task_finished emitted: task_id={taskid}, state={state}')


async def _mark_failed(db: ConversationDB, taskid: int, message: str):
    """将任务标记为 failed，错误信息同时落 last_error（query_compute_job 直接可读）。"""
    print(f'Error: {message}')
    try:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?",
                ('failed', time.time(), message[:500], taskid)
            )
            await con.commit()
    except Exception as e:
        print(f'[guard] 标记 failed 失败：{e}')
        return
    # D5/D11：失败终态同样入 CallReview 收件箱（rev_compute_<id> 去重）
    try:
        from cloudra.dag.controller import enqueue_compute_review

        await enqueue_compute_review(db, taskid, 'failed')
    except Exception as e:
        print(f'[guard] enqueue compute review 失败（已忽略）: {e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--path', type=str, required=True)
    parser.add_argument('--conv_id', type=str, required=True)
    parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    parser.add_argument('--job_type', type=str, default='gaussian')
    args = parser.parse_args()

    asyncio.run(run_guard(
        taskid=args.task_id,
        path=args.path,
        conv_id=args.conv_id,
        parse_timeout=max(60, args.timeout),
        db_path=args.db_path,
        job_type=args.job_type,
    ))
