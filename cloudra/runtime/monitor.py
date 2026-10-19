import argparse
import asyncio
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from cloudra.infra.compute_utils import (
    XtbParams,
    build_calculator_cmd,
    calc_lock_path,
    check_job_type,
    get_log_path,
    guard_lock_path,
)
from cloudra.infra.flocks import try_acquire_lock
from cloudra.persistence.database import ComputeDB
from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.services.compute_store import (
    acancel_compute_job,
    afinalize_compute_job,
    aget_compute_job,
    aupdate_compute_pid,
)

_LOG_TAIL_CHARS = 8000
_REASON_MAX_CHARS = 500
# 终止标记：Gaussian "Error termination"、CP2K "PROGRAM FAILED/ABORT" 等
_FAILURE_MARKERS = ("Error termination", "PROGRAM FAILED", "ABORT", "Error:", "ERROR")
# adopt 模式等 calc 锁释放的探测间隔（秒）
_ADOPT_POLL_SECONDS = 5
# Ledger polling is control-plane latency, independent of chemical acceptance.
_CANCEL_POLL_SECONDS = 0.5
# calculator 的 nice 降权幅度：CPU 打满时控制面（API/调度守护）按 CFS 权重
# 优先分到时间片，状态同步链路不被计算任务饿死。降权不需要特权。
_CALC_NICE_LEVEL = 10


def _lower_sched_priority() -> None:
    """Best-effort calculator niceness; denial must not abort its exec."""
    try:
        os.nice(_CALC_NICE_LEVEL)
    except OSError:
        # Some restricted POSIX hosts deny setpriority even for a positive
        # increment. This runs after fork: avoid logging or other Python work.
        pass


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
    positions = [text.rfind(marker) for marker in ('ORCA finished by error termination', 'Error termination')]
    last_fatal = max(positions)
    region = text[-_LOG_TAIL_CHARS:]
    if last_fatal >= 0:
        start = text.rfind('\n', 0, last_fatal)
        for _ in range(2):
            start = text.rfind('\n', 0, max(0, start))
        region = text[max(0, start):last_fatal + 2000]
    lines = [line.strip() for line in region.splitlines() if line.strip()]
    picked: list[str] = []
    # Native termination blocks and process signals carry the failure. Transport
    # warnings can also contain Error: and otherwise consume the whole receipt.
    fatal = [i for i, line in enumerate(lines) if
             'ORCA finished by error termination' in line or 'Error termination' in line]
    if fatal:
        picked.extend(lines[i] for i in reversed(fatal))
        for marker in ('exited on signal ', 'Segmentation fault'):
            index = text.rfind(marker)
            if index >= 0:
                begin = text.rfind('\n', 0, index) + 1
                end = text.find('\n', index)
                picked.append(text[begin:end if end >= 0 else len(text)].strip())
        for i in reversed(fatal):
            picked.extend(line for line in lines[i + 1:i + 4] if
                          'Calling Command:' in line or '[file ' in line or 'aborting' in line.lower())
            if 'Error termination' in lines[i]:
                picked.extend(lines[max(0, i - 2):i])
    for i, line in enumerate(lines):
        if not fatal and any(marker in line for marker in _FAILURE_MARKERS):
            picked.extend(lines[max(0, i - 2): i + 2])
    if not picked:
        picked = lines[-3:]
    # 保序去重（标记段的上下文行可能重叠）
    seen: set[str] = set()
    unique = [line for line in picked if not (line in seen or seen.add(line))]
    return " | ".join(unique)[:_REASON_MAX_CHARS]


def _resolve_log_target(log_path: Path, fallback_log_path: Path | None) -> tuple[Path | None, bool]:
    """挑选实际解析目标：(target, used_fallback)。

    推导日志（引擎惯例路径，如 ``x.out``）有效则用之；缺失/为空时若
    calculator 的 stdout/stderr 落盘文件（``fallback_log_path``）有内容，
    回退解析它——部分引擎（如本机 ORCA 6.1.1 macOS 构建）从不落 ``.out``，
    主输出全部写 stdout。两处皆不可用时返回 (None, False)。
    """
    if log_path.exists() and log_path.stat().st_size > 0:
        return log_path, False
    if (
        fallback_log_path is not None
        and fallback_log_path.exists()
        and fallback_log_path.stat().st_size > 0
    ):
        print(
            f"推导日志不存在或为空：{log_path}；"
            f"回退解析 calculator 输出落盘：{fallback_log_path}"
        )
        return fallback_log_path, True
    print(f'日志文件不存在或为空：{log_path}')
    return None, False


async def _parse_log(
    log_path: Path,
    parse_timeout: int,
    job_type: str = "gaussian",
    fallback_log_path: Path | None = None,
    xtb_task: str | None = None,
):
    """尝试解析日志，返回 (data_dic, is_success) 或 (None, None) 表示失败。

    Guard 在 calculator 已退出后才调用本函数，日志应已写完；``parse_timeout``
    仅保留 CLI 兼容，实际只做少量短间隔重试（应对文件系统延迟），不会空转半小时。

    ``fallback_log_path`` 是 calculator 的 stdout/stderr 落盘文件：部分引擎
    不自写日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落
    ``.out``），推导的日志路径会缺失/为空——此时回退解析落盘文件，避免正常
    完成的作业被误判为"日志为空或缺失"。实际解析的日志路径会写进
    ``data_dic["log_file"]``（agent 按惯例路径找不到日志时，从 state json 取它）。

    ``xtb_task`` 是 compute_jobs 行声明的 xtb 运行级别（sp/opt/hess/ohess）：
    优化收敛第二判据只对 opt/ohess 生效，hess 任务不被"优化未收敛"误伤。
    """
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import read_task_result
        try:
            return await asyncio.to_thread(read_task_result, str(log_path))
        except (OSError, ValueError, KeyError):
            return None, False
    target, _ = await asyncio.to_thread(_resolve_log_target, log_path, fallback_log_path)
    if target is None:
        return None, None

    if job_type == "cp2k":
        # cclib 1.8.x 已移除 CP2K 解析器，这里用轻量文本解析兜底。
        data_dic, is_success = await asyncio.to_thread(_parse_cp2k_log, target)
        if data_dic is not None:
            data_dic["log_file"] = str(target)
        return data_dic, is_success

    if job_type == "xtb":
        # xtb 主输出全部走 stdout（calculator.sh 重定向到 .out），cclib 对
        # xtb 支持薄弱——纯文本判定（GH #26），与 CP2K 同款轻量路径。
        data_dic, is_success = await asyncio.to_thread(_parse_xtb_log, target, task=xtb_task)
        if data_dic is not None:
            data_dic["log_file"] = str(target)
        return data_dic, is_success

    if job_type == "orca":
        return await _parse_orca_log(target)

    if job_type == "gaussian":
        return await _parse_gaussian_log(target)

    if job_type == "vasp":
        data_dic, is_success = await asyncio.to_thread(_parse_vasp_log, target)
        if data_dic is not None:
            data_dic["log_file"] = str(target)
        return data_dic, is_success

    parsed = await _cclib_parse(target)
    if parsed is None:
        return None, None
    data_dic, _cclib_success = parsed
    # 未知引擎：cclib 只取数据，不定成败（与 Gaussian/ORCA 同口径）。
    return data_dic, False


async def _cclib_parse(target: Path) -> tuple[dict, bool] | None:
    """cclib 数据提取（短间隔重试，应对文件系统延迟）。

    返回 ``(data_dic, cclib_success)``；日志无法识别、必需字段缺失或转换失败
    返回 None。``cclib_success`` 只是 cclib 的自报 metadata.success，是否采信
    由调用方按引擎决定（ORCA 不采信，见 :func:`_parse_orca_log`）。
    """
    import cclib

    max_attempts = 5
    retry_sleep = 1.0
    last_error = None
    for attempt in range(max_attempts):
        try:
            data = await asyncio.to_thread(cclib.io.ccread, target)
            if data is None:
                print(f'cclib 无法识别日志格式：{target}')
                return None
            # cclib 1.8+ 会容忍缺坐标/原子序数的日志并继续返回对象，但 ccwrite
            # 会抛 'Must pass at least one of atomcoords or atomnos'；旧版 cclib
            # 在 ccread 阶段就抛 AttributeError。统一在解析后做必需字段检查，
            # 避免 CI/本地版本差异导致的行为分歧。
            if not hasattr(data, 'atomcoords') or not hasattr(data, 'atomnos'):
                print(f'日志缺少原子坐标或原子序数，视为不完整：{target}')
                return None
            is_success = data.metadata.get('success', False)
            try:
                state_str = await asyncio.to_thread(cclib.io.ccwrite, data, outputtype="cjson")
                state_CJSON = cclib.io.cjsonreader.CJSON(io.StringIO(state_str))
                data_dic = await asyncio.to_thread(state_CJSON.parse)
            except Exception as e:
                print(f'日志解析后转换失败：{e}')
                return None
            data_dic.pop('atomcoords', None)
            data_dic['is_success'] = is_success
            data_dic['log_file'] = str(target)
            return data_dic, is_success
        except Exception as e:
            last_error = e
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(retry_sleep)
    print(f'日志解析失败：{last_error}')
    return None


async def _parse_gaussian_log(target: Path) -> tuple[dict, bool]:
    """Gaussian 日志解析：终止标记定成败，cclib 只负责提取数据字段。"""
    from cloudra.tools.core import gaussian_frames

    try:
        text = await asyncio.to_thread(target.read_text, encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 Gaussian 日志失败：{e}')
        return {"is_success": False, "log_file": str(target)}, False
    is_success = gaussian_frames.normal_termination(text)
    parsed = await _cclib_parse(target)
    data_dic = parsed[0] if parsed is not None else {}
    opt_ok = gaussian_frames.opt_converged(text)
    if opt_ok is None and {"opt", "ts"} & gaussian_frames.detect_job_types_from_text(text):
        # cclib also records IRC corrector convergence in optdone; only an
        # independently declared optimization may use it as a fallback.
        optdone = data_dic.get("optdone")
        if optdone is not None:
            opt_ok = bool(optdone)
    data_dic["normal_termination"] = is_success
    data_dic["opt_converged"] = opt_ok
    data_dic["is_success"] = is_success
    data_dic["log_file"] = str(target)
    return data_dic, is_success


async def _parse_orca_log(target: Path) -> tuple[dict, bool]:
    """ORCA 日志解析：终止标记定成败，cclib 只负责提取数据字段。

    成功判据是日志中出现 ``ORCA TERMINATED NORMALLY``（引擎自报正常结束）；
    标记缺失（error termination、被 kill、崩溃截断）即 failed。cclib 解析失败
    不等于任务失败：外部 MLIP（ExtOpt/ProgExt）日志无 SCF 块，cclib 常抛
    "Unexpectedly encountered end of logfile" 或缺 spin multiplicity
    （GH #17/#18：正常终止的 MACE NumFreq/IRC 作业被误判 failed）。cclib
    失败时退化为文本提取的最小数据（最终能量 + is_success + log_file）。
    终止/能量的文本权威判据与 log_parser 共用 tools.core.orca_frames。

    优化收敛单独记录，不改写作业原生终态；科学验收仍要求实际收敛。
    文本收敛标记为主，cclib optdone 为辅（外部 MLIP 日志 cclib 可能解析失败）。
    """
    from cloudra.tools.core import orca_frames

    try:
        text = await asyncio.to_thread(target.read_text, encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 ORCA 日志失败：{e}')
        return {"is_success": False, "log_file": str(target)}, False
    is_success = orca_frames.normal_termination(text)

    parsed = await _cclib_parse(target)
    if parsed is not None:
        data_dic, _ = parsed
    else:
        # 最小数据：cclib 不可用时至少给出最终能量（外部 MLIP 的唯一能量行）
        data_dic = {"log_file": str(target)}
        energy = orca_frames.final_energy_hartree(text)
        if energy is not None:
            data_dic["total_energy_hartree"] = energy
            data_dic["scf_energy_hartree"] = energy
            data_dic["scf_energy_ev"] = energy * 27.211386245988

    opt_ok = orca_frames.opt_converged(text)
    if opt_ok is None and parsed is not None:
        # cclib 辅助：文本标记缺失时（如版本差异）看 optdone，仅对 opt/ts 类任务
        if {"opt", "ts"} & orca_frames.detect_job_types_from_text(text):
            optdone = data_dic.get("optdone")
            if optdone is not None:
                opt_ok = bool(optdone)
    data_dic["opt_converged"] = opt_ok
    data_dic["normal_termination"] = is_success
    data_dic["is_success"] = is_success
    return data_dic, is_success


def _parse_xtb_log(log_path: Path, *, task: str | None = None) -> tuple[dict, bool] | None:
    """轻量解析 xtb 输出日志（calculator stdout 重定向的 .out）。

    成功判据：正常终止标记 ``normal termination of xtb``（文本权威，与
    log_parser 共用 tools.core.xtb_frames 原语，GH #26）。优化收敛是独立
    的第二判据（GH #21 同款语义）：未收敛的优化仍打印 normal termination，
    ``FAILED TO CONVERGE`` 标记即判 failed——但只对 opt/ohess 任务生效；
    hess/sp 任务不做几何优化，不适用该判据（``task=None`` 的旧行保持历史
    行为）。能量按文本位置取最后的能量行。
    """
    from cloudra.tools.core import xtb_frames

    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 xtb 日志失败：{e}')
        return None
    if not text.strip():
        return None

    is_success = xtb_frames.normal_termination(text)
    opt_ok = xtb_frames.opt_converged(text)
    energy = xtb_frames.final_energy_hartree(text)

    data_dic: dict = {
        "is_success": is_success,
        "opt_converged": opt_ok,
    }
    if energy is not None:
        data_dic["total_energy_hartree"] = energy
        data_dic["scf_energy_hartree"] = energy
        data_dic["scf_energy_ev"] = energy * 27.211386245988
    opt_relevant = task in (None, "opt", "ohess")
    if is_success and opt_ok is False and opt_relevant:
        is_success = False
        data_dic["is_success"] = False
        data_dic["error"] = "xtb 几何优化未收敛（达到最大优化步数），结果不可信"
    return data_dic, is_success


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


def _parse_vasp_log(log_path: Path) -> tuple[dict, bool] | None:
    """轻量解析 VASP OUTCAR / 重定向 .out。

    成功判据：出现 ``General timing and accounting informations for this job:``
    （正常退出才打印），且没有 fatal error。能量取最后一次 ``free  energy   TOTEN``。
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 VASP 日志失败：{e}')
        return None
    if not text.strip():
        return None

    normal = "General timing and accounting informations for this job:" in text
    aborted = any(
        marker in text
        for marker in ("ZBRENT: fatal error", "fatal error in bracketing", "VERY SERIOUS PROBLEMS")
    )
    is_success = normal and not aborted

    energy_ev = None
    for line in reversed(text.splitlines()):
        if "free  energy   TOTEN" in line and "=" in line:
            raw = line.split("=", 1)[1].replace("eV", "").strip()
            try:
                energy_ev = float(raw.split()[0] if raw.split() else raw)
            except ValueError:
                pass
            break

    data_dic: dict = {"is_success": is_success}
    if energy_ev is not None:
        data_dic["scf_energy_ev"] = energy_ev
        hartree = energy_ev / 27.211386245988
        data_dic["scf_energy_hartree"] = hartree
        data_dic["total_energy_hartree"] = hartree
    return data_dic, is_success


async def _register_pid(db: ComputeDB, taskid: int, column: str, pid: int):
    """登记 guard/calc PID。仅作观测取证（agent 可自行 ps 排查），不参与存活判定。"""
    try:
        await aupdate_compute_pid(db, taskid, column, pid)
    except Exception as e:
        print(f'[guard] 登记 {column} 失败（已忽略）: {e}')


def _calc_output_log_path(workdir: str, taskid: int) -> Path:
    """calculator 的 stdout/stderr 落盘路径（.cloudra/calc-<id>.out.log）。

    引擎未必自写日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、
    从不落 .out），guard 必须保留其输出才能解析；同时 stderr 有了失败取证。
    """
    run_dir = Path(workdir) / ".cloudra"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / f"calc-{taskid}.out.log"


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
    1. 经 calc_lock_wrapper 启动独占进程组；只消费账本显式取消请求。
    2. calculator 退出后，在 parse_timeout 窗口内尝试解析日志。
    3. 解析成功则写 state.json、更新数据库、注入事件；失败则标记 failed。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ComputeDB.from_path(db_path)

    guard_lock = await asyncio.to_thread(guard_lock_path, workdir, taskid)
    guard_fd = await asyncio.to_thread(try_acquire_lock, guard_lock)
    if guard_fd is None:
        print(f'[guard] task {taskid} 已有 guard 持锁在管，退出（OS 级防重）')
        return
    try:
        await _register_pid(db, taskid, "guard_pid", os.getpid())
        calc_lock = await asyncio.to_thread(calc_lock_path, workdir, taskid)
        row = await aget_compute_job(db, taskid)
        if row is None or row["state"] != "running":
            # No calculator was spawned by this owner. A prior calculator may
            # still hold the lock, so only acknowledge cancellation when free.
            calc_fd = await asyncio.to_thread(try_acquire_lock, calc_lock)
            if calc_fd is not None:
                try:
                    if row is not None and row["state"] == "cancel_requested":
                        await acancel_compute_job(db, taskid)
                finally:
                    os.close(calc_fd)
            return
        from cloudra.services.ts_pipeline_store import verify_stage_input
        try:
            await asyncio.to_thread(verify_stage_input, db, taskid)
        except (OSError, ValueError) as exc:
            await _mark_failed(db, taskid, str(exc))
            return

        # xtb 任务参数的唯一事实来源是 compute_jobs 行（submit 时校验入库）；
        # guard 据此拼 calculator 命令，charge/mult/task/solvent/cpus 全部透传。
        xtb_params: XtbParams | None = None
        if job_type == "xtb":
            row = await aget_compute_job(db, taskid)
            xtb_params = XtbParams.from_row(row)

        ok, msg = await asyncio.to_thread(check_job_type, job_type, workdir)
        if not ok:
            print(f'[guard] 环境检查失败：{msg}')
            await _mark_failed(db, taskid, msg)
            return

        ok, calculator_cmd, msg = await asyncio.to_thread(build_calculator_cmd,
            path, job_type=job_type, xtb_params=xtb_params
        )
        if not ok:
            print(f'[guard] 无法构建 calculator 命令：{msg}')
            await _mark_failed(db, taskid, msg)
            return

        # 启动 calculator；start_new_session 保证 guard 意外退出时 calculator 不被连带杀死。
        from cloudra.infra.compute_utils import (
            allocate_gaussian_scratch,
            cleanup_gaussian_scratch,
        )

        calc_env = os.environ.copy()
        scratch_dir = None
        if job_type == "gaussian":
            scratch_dir = await asyncio.to_thread(allocate_gaussian_scratch, taskid, workdir)
            calc_env["GAUSS_SCRDIR"] = str(scratch_dir)
            print(f'[guard] Gaussian scratch: {scratch_dir}')

        # calculator 必须经锁 wrapper 拉起：calc-<id>.lock 跨 exec 继承，
        # calculator 全家存续期间锁有效——这是对账判定"计算是否还在跑"的唯一权威。
        wrapped_cmd = [
            sys.executable,
            "-m",
            "cloudra.runtime.calc_lock_wrapper",
            calc_lock,
            "--",
            *calculator_cmd,
        ]
        # calculator stdout/stderr 落盘而非 DEVNULL：引擎未必自写日志文件
        # （本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
        # 丢弃即丢主输出；落盘同时保留 stderr 供失败取证。
        # O_TRUNC：同一 task 重试时新 guard 必须从头写，避免新旧输出混叠
        # （cclib 读到多个 TERMINATION 标记会解析混乱）。
        output_log = await asyncio.to_thread(_calc_output_log_path, workdir, taskid)
        calc_log_fd = await asyncio.to_thread(os.open,
            output_log,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o644,
        )
        calc_kwargs = {
            "stdout": calc_log_fd,
            "stderr": calc_log_fd,
            "stdin": subprocess.DEVNULL,
            "cwd": workdir,
            "env": calc_env,
            "start_new_session": True,
            "preexec_fn": _lower_sched_priority,
        }
        returncode: int | None = None
        try:
            # Recheck after setup awaits: an accepted pre-launch request must
            # not start a new calculation. A request during spawn is consumed
            # immediately after obtaining the fresh owned process handle.
            row = await aget_compute_job(db, taskid)
            if row is None or row["state"] != "running":
                calc_fd = await asyncio.to_thread(try_acquire_lock, calc_lock)
                if calc_fd is not None:
                    try:
                        if row is not None and row["state"] == "cancel_requested":
                            await acancel_compute_job(db, taskid)
                            await asyncio.to_thread(cleanup_gaussian_scratch, scratch_dir)
                    finally:
                        os.close(calc_fd)
                return
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(*wrapped_cmd, **calc_kwargs))
            # Cancelling the guard must neither interrupt spawn nor signal its
            # calculator; a later adopt guard can await the inherited flock.
            try:
                calc_proc = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                await asyncio.shield(spawn)
                raise
            await _register_pid(db, taskid, "calc_pid", calc_proc.pid)
            print(f'[guard] calculator 启动 (PID {calc_proc.pid})，等待其结束...')
            cancel_sent = False
            while calc_proc.returncode is None:
                row = await aget_compute_job(db, taskid)
                if row is None:
                    raise RuntimeError(f"compute job {taskid} disappeared while calculator runs")
                if row["state"] == "cancel_requested" and not cancel_sent:
                    # Only the freshly created session belongs to this owner.
                    # Never infer a group from a persisted PID, an exception,
                    # scheduler shutdown, or Agent task cancellation.
                    if calc_proc.returncode is None:
                        try:
                            os.killpg(calc_proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    cancel_sent = True
                try:
                    returncode = await asyncio.wait_for(calc_proc.wait(), _CANCEL_POLL_SECONDS)
                except TimeoutError:
                    continue
            returncode = await calc_proc.wait()
            print(f'[guard] calculator 退出，退出码：{returncode}')
        finally:
            os.close(calc_log_fd)

        # Reaping the parent does not prove that all engine links exited.
        # Hold the released calc flock through terminal CAS and scratch cleanup.
        while (calc_fd := await asyncio.to_thread(try_acquire_lock, calc_lock)) is None:
            await asyncio.sleep(_CANCEL_POLL_SECONDS)
        try:
            row = await aget_compute_job(db, taskid)
            if row is None:
                raise RuntimeError(f"compute job {taskid} disappeared before finalization")
            if row["state"] == "running":
                await _finalize(
                    db, taskid, log_path, workdir, parse_timeout, job_type, returncode,
                    fallback_log_path=output_log,
                    xtb_task=xtb_params.task if xtb_params else None,
                )
            # Cancellation can win while logs are being parsed. The running-only
            # finalization CAS suppresses success; this owner must still ack it.
            row = await aget_compute_job(db, taskid)
            if row is not None and row["state"] == "cancel_requested":
                await acancel_compute_job(db, taskid)
                row = await aget_compute_job(db, taskid)
            if row is not None and row["state"] in {"done", "failed", "cancelled"}:
                await asyncio.to_thread(cleanup_gaussian_scratch, scratch_dir)
        finally:
            os.close(calc_fd)
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

    guard_lock = await asyncio.to_thread(guard_lock_path, workdir, taskid)
    guard_fd = await asyncio.to_thread(try_acquire_lock, guard_lock)
    if guard_fd is None:
        print(f'[guard adopt] task {taskid} 已有 guard 持锁在管，退出')
        return
    try:
        await _register_pid(db, taskid, "guard_pid", os.getpid())
        calc_lock = await asyncio.to_thread(calc_lock_path, workdir, taskid)
        while True:
            calc_fd = await asyncio.to_thread(try_acquire_lock, calc_lock)
            if calc_fd is not None:
                break
            print(f'[guard adopt] calc 锁仍被持有，calculator 还在跑；{_ADOPT_POLL_SECONDS}s 后再探...')
            await asyncio.sleep(_ADOPT_POLL_SECONDS)
        try:
            row = await aget_compute_job(db, taskid)
            if row is None:
                raise RuntimeError(f"compute job {taskid} disappeared before adopt finalization")
            if row["state"] == "cancel_requested":
                await acancel_compute_job(db, taskid)
                return
            if row["state"] != "running":
                return
            xtb_task = XtbParams.from_row(row).task if job_type == "xtb" else None
            output_log = await asyncio.to_thread(_calc_output_log_path, workdir, taskid)
            await _finalize(
                db, taskid, log_path, workdir, parse_timeout, job_type, None,
                fallback_log_path=output_log, xtb_task=xtb_task,
            )
            row = await aget_compute_job(db, taskid)
            if row is not None and row["state"] == "cancel_requested":
                await acancel_compute_job(db, taskid)
        finally:
            os.close(calc_fd)
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
        wrote = await afinalize_compute_job(db, taskid, 'failed', last_error=message[:500])
    except Exception as e:
        print(f'[guard] 标记 failed 失败：{e}')
        return
    if not wrote:
        print(f'[guard] ledger already terminal; skip failed review task_id={taskid}')
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
