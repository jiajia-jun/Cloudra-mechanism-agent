#!/usr/bin/env python3
"""CI 门禁：JS 宿主依赖装好了，宿主用例就必须真跑，不允许整片 skip。

背景：默认调用协议是 `invocation_protocol=javascript`，宿主用例（每个都 spawn 真实
node 跑 QuickJS-WASM）是这条协议唯一的回归门禁。它们按环境探测 skip——本地开发机
上合理，但 CI 的 `js-host` job 已经把依赖装好，此时再 skip 就说明"探测逻辑与环境
脱节"，门禁变成假的：绿得毫无意义。

判定全部走结构化路径（不解析散文）：
  1. 直接探测前提：node 主版本 >= 22 且 `js_host/node_modules/quickjs-emscripten`
     存在，缺任一项直接失败并打印安装命令；
  2. 读 pytest 的 JUnit XML（`--junitxml`，机器可读），凡是宿主/可选依赖原因的
     skip 一律算失败；其它环境缺口（例如本机 pip wheel 构建不可用）照旧容忍。

用法：python scripts/check_js_host_gate.py [junit.xml]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST_DIR = ROOT / "cloudra" / "runtime_v2" / "js_host"
DEFAULT_XML = Path("/tmp/js-host-junit.xml")

# 这些原因出现在 skip 里就说明上面的依赖白装了，属门禁失效
FATAL_SKIP_TOKENS = (
    "JS host",
    "quickjs-emscripten",
    "node >= 22",
    "RDKit",
)


def node_major() -> int | None:
    node = shutil.which("node")
    if node is None:
        return None
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    head = out.lstrip("v").split(".")[0]
    return int(head) if head.isdigit() else None


def main(argv: list[str]) -> int:
    xml_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_XML
    problems: list[str] = []

    major = node_major()
    if major is None or major < 22:
        problems.append(
            f"node >= 22 required for the JS host (found {major!r}); "
            "install it with actions/setup-node"
        )
    if not (HOST_DIR / "node_modules" / "quickjs-emscripten" / "package.json").is_file():
        problems.append(
            "js_host/node_modules/quickjs-emscripten missing; "
            "run: npm ci --prefix cloudra/runtime_v2/js_host"
        )

    if not xml_path.is_file():
        problems.append(f"JUnit XML not found: {xml_path} (run pytest with --junitxml)")
        report(xml_path, 0, 0, 0, problems)
        return 1

    tree = ET.parse(xml_path)
    total = skipped = failures = 0
    for case in tree.iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failures += 1
        node = case.find("skipped")
        if node is None:
            continue
        skipped += 1
        message = node.get("message") or ""
        for token in FATAL_SKIP_TOKENS:
            if token in message:
                problems.append(
                    f"{case.get('classname')}::{case.get('name')} skipped for a "
                    f"dependency this job installs: {message!r}"
                )
                break

    report(xml_path, total, skipped, failures, problems)
    return 1 if problems else 0


def report(xml_path: Path, total: int, skipped: int, failures: int, problems: list[str]) -> None:
    print(f"junit: {xml_path} tests={total} skipped={skipped} failures={failures}")
    if problems:
        print("JS host gate FAILED:")
        for item in problems:
            print(f"  - {item}")
    else:
        print("JS host gate OK: host dependencies present, no host-related skips")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
