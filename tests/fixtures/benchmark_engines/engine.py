"""受控引擎替身：benchmark 完整链路测试的传输测试材料。

测试把替身可执行入口放进仅测试进程继承的 PATH（monkeypatch.setenv）；替身
记录 argv/cwd/输入 sha256（追加到 ``$CLOUDRA_ENGINE_RECORD`` 的 JSONL），并按
``$CLOUDRA_ENGINE_CTL`` 控制目录里的控制文件决定正常退出、失败退出或等待
释放。日志内容来自 ``tests/fixtures/gaussian`` / ``tests/fixtures/orca`` /
``tests/fixtures/xtb`` 的现有真实日志 fixture。

明确标注：这些 fixture 不是科学计算结果——替身的"成功"只能证明 harness
路径可用，不能证明任何化学结论；真实引擎能力验证见
docs/superpowers/plans/2026-09-10-benchmark-sandbox-tool-availability.md
的"三层验证"第 3 层。

控制文件语义（``<ctl>`` 目录内）：
- ``fail``       本次运行失败退出（引擎各自带失败日志/退出码）。
- ``fail_once``  失败一次并自动消费（删除该控制文件）；复跑成功。
- ``wait``       阻塞直到出现 ``release`` 控制文件（超时上限
                 ``CLOUDRA_ENGINE_WAIT_TIMEOUT`` 秒，默认 300）。
- ``release``    释放被 ``wait`` 阻塞的运行。
- ``write_out``  ORCA：额外把真实 fixture 日志写到 ``<stem>.out``
                 （默认 stdout-only，模拟 macOS ORCA 6 行为）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

FIXTURE_DIR = Path(__file__).resolve().parents[1]

_GAUSSIAN_OK_LOG = FIXTURE_DIR / "gaussian" / "water_opt_freq_g16.out"
_GAUSSIAN_TS_LOG = FIXTURE_DIR / "gaussian" / "hcn_ts_irc_g16.log"
_ORCA_OK_LOG = FIXTURE_DIR / "orca" / "dvb_opt_orca42.out"
_XTB_OK_LOG = FIXTURE_DIR / "xtb" / "water_sp_xtb.out"

ENGINE_KINDS = ("gaussian", "gaussian_ts", "orca", "xtb")

# 替身可执行文件名必须匹配 infra.compute_utils._REQUIRED_BINS 的查找名单
# （check_job_type / calculator.sh 按这些名字在 PATH 上找引擎）。
_BIN_NAME = {"gaussian": "g16", "gaussian_ts": "g16", "orca": "orca", "xtb": "xtb"}


def engine_script(kind: str) -> str:
    """生成对应引擎替身的 bash 源码（放进仅测试进程继承的 PATH）。"""
    if kind not in ENGINE_KINDS:
        raise ValueError(f"unknown engine kind: {kind!r}")

    if kind in ("gaussian", "gaussian_ts"):
        fixture = _GAUSSIAN_TS_LOG if kind == "gaussian_ts" else _GAUSSIAN_OK_LOG
        body = f'''
    LOG="${{INPUT%.gjf}}.log"
    if [ -n "$FAIL" ]; then
        echo "mock gaussian failed" >&2
        exit 1
    fi
    cp "{fixture}" "$LOG"
'''
    elif kind == "orca":
        body = f'''
    if [ -n "$FAIL" ]; then
        echo "ORCA finished by error termination in SCF" >&1
        exit 1
    fi
    if [ -f "$CTL/write_out" ]; then
        cp "{_ORCA_OK_LOG}" "${{INPUT%.inp}}.out"
    fi
    echo "ORCA TERMINATED NORMALLY"
'''
    else:  # xtb
        body = f'''
    OUTPUT="${{INPUT%.*}}.out"
    if [ -n "$FAIL" ]; then
        echo "FAILED TO CONVERGE GEOMETRY OPTIMIZATION IN 500 CYCLES" >&2
        echo "abnormal termination of xtb" >&2
        exit 1
    fi
    cp "{_XTB_OK_LOG}" "$OUTPUT"
'''

    return f'''#!/bin/bash
# 受控引擎替身（{kind}）——见 tests/fixtures/benchmark_engines/engine.py
set -u
INPUT="$1"
CTL="${{CLOUDRA_ENGINE_CTL:-}}"
REC="${{CLOUDRA_ENGINE_RECORD:-}}"
FAIL=""

if [ -n "$CTL" ] && [ -f "$CTL/fail_once" ]; then
    rm -f "$CTL/fail_once"
    FAIL=1
elif [ -n "$CTL" ] && [ -f "$CTL/fail" ]; then
    FAIL=1
fi

if [ -n "$REC" ]; then
    python3 -c '
import hashlib, json, os, sys, time
args = sys.argv[1:]
inp = args[0] if args else ""
try:
    sha = hashlib.sha256(open(inp, "rb").read()).hexdigest()
except OSError:
    sha = None
rec = {{"kind": "{kind}", "argv": args, "cwd": os.getcwd(),
       "input": inp, "input_sha256": sha, "t": time.time()}}
with open(os.environ["CLOUDRA_ENGINE_RECORD"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\\n")
' "$@"
fi

if [ -n "$CTL" ] && [ -f "$CTL/wait" ]; then
    timeout=${{CLOUDRA_ENGINE_WAIT_TIMEOUT:-300}}
    waited=0
    while [ ! -f "$CTL/release" ]; do
        sleep 0.05
        waited=$((waited + 1))
        if [ $((waited / 20)) -ge "$timeout" ]; then
            echo "engine stub wait timeout" >&2
            exit 124
        fi
    done
fi
{body}
exit 0
'''


class EngineHarness:
    """测试侧操作句柄：读运行记录、设控制文件、释放等待。"""

    def __init__(self, monkeypatch, bindir: Path, kind: str, ctl: Path, record: Path) -> None:
        self.monkeypatch = monkeypatch
        self.bindir = Path(bindir)
        self.kind = kind
        self.ctl = Path(ctl)
        self.record = Path(record)
        self.ctl.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CLOUDRA_ENGINE_CTL", str(self.ctl))
        monkeypatch.setenv("CLOUDRA_ENGINE_RECORD", str(self.record))

    def set_control(self, name: str) -> None:
        (self.ctl / name).write_text("", encoding="utf-8")

    def clear_control(self, name: str) -> None:
        (self.ctl / name).unlink(missing_ok=True)

    def release(self) -> None:
        self.set_control("release")

    def runs(self) -> list[dict[str, Any]]:
        if not self.record.exists():
            return []
        out = []
        for line in self.record.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out


def install_engine(
    monkeypatch,
    bindir: Path,
    kind: str,
    *,
    ctl: Optional[Path] = None,
    record: Optional[Path] = None,
) -> EngineHarness:
    """把引擎替身放进测试进程继承的 PATH，并返回操作句柄。"""
    bindir = Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    bin_name = _BIN_NAME[kind]
    (bindir / bin_name).write_text(engine_script(kind), encoding="utf-8")
    (bindir / bin_name).chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(bindir) + os.pathsep + os.environ.get("PATH", ""),
    )
    harness = EngineHarness(
        monkeypatch,
        bindir,
        kind,
        ctl or bindir / ".engine_ctl",
        record or bindir / "engine_runs.jsonl",
    )
    return harness
