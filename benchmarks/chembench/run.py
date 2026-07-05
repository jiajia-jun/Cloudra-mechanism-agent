"""
ChemBench CLI 入口。

用法示例
--------
# 全量跑，YOLO 模式（使用默认本地数据目录）
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run

# 指定本地数据目录
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \\
    --data-dir benchmarks/data/chembench-repo/data

# 限制 10 题快速测试
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run --limit 10

# 只跑有机化学子集，指定 run_id
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \\
    --subset organic-chemistry \\
    --run-id paper_v1

# 并发 3，每题超时 5 分钟
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \\
    --concurrency 3 \\
    --timeout 300

此 CLI 刻意保持"薄"：仅解析参数、构造 RunnerConfig、启动 Runner。
全部业务逻辑在 runner.py / evaluator.py / adapter.py / report.py 中。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 将项目根目录（CLOUDRA）强制注入到 sys.path，支持在任意目录下直接执行该脚本
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


# 默认本地数据目录（git clone 后的路径）
_DEFAULT_DATA_DIR = str(
    (Path(__file__).parent.parent / "data" / "chembench-repo" / "data").resolve()
)


@click.command(context_settings={"max_content_width": 100})
@click.option(
    "--data-dir", "-d",
    default=_DEFAULT_DATA_DIR, show_default=True,
    help="ChemBench 本地数据目录（含按 topic 分组的 JSON 文件）",
)
@click.option(
    "--limit", "-n",
    type=int, default=None,
    help="只评测前 N 题（默认全部）",
)
@click.option(
    "--subset", "-s",
    multiple=True,
    metavar="KEYWORD",
    help="只评测含指定关键词的题目，可重复指定多个",
)
@click.option(
    "--timeout", "-t",
    type=float, default=300.0, show_default=True,
    help="每题最大等待时间（秒）",
)
@click.option(
    "--concurrency", "-c",
    type=int, default=1, show_default=True,
    help="并发数（>1 时多题同时跑，建议 ≤ 4）",
)
@click.option(
    "--run-id",
    default=None,
    help="自定义 run_id（默认自动生成）",
)
@click.option(
    "--quiet", "-q",
    is_flag=True, default=False,
    help="静默模式，不打印逐题进度",
)
def main(data_dir, limit, subset, timeout, concurrency, run_id, quiet):
    """
    使用 Cloudra 完整 Agent 管道评测 ChemBench。

    \b
    前置条件：
      - pip install chembench  （或 requirements.txt 已安装）
      - 设置 CLOUDRA_YOLO_MODE=true  （跳过交互式审批）
      - cloudra 配置文件正确（coordinator/follower model、key、url）
    """
    # ── YOLO 模式检查 ────────────────────────────────────────────────────────
    yolo = os.environ.get("CLOUDRA_YOLO_MODE", "").lower() in ("1", "true", "yes", "on")
    if not yolo:
        console.print(
            Panel(
                "[bold yellow]警告[/bold yellow]: CLOUDRA_YOLO_MODE 未启用。\n"
                "批量评测时 approval_handler 会通过 CLI input() 等待人工审批，\n"
                "这会导致进程阻塞。\n\n"
                "建议运行前执行：[bold]export CLOUDRA_YOLO_MODE=true[/bold]",
                title="YOLO 模式未启用",
                border_style="yellow",
            )
        )
        if not click.confirm("确认继续（不推荐）？", default=False):
            sys.exit(0)

    # ── 数据目录检查 ─────────────────────────────────────────────────────────
    if data_dir.lower() != "hf" and not Path(data_dir).exists():
        console.print(
            Panel(
                f"[bold red]错误[/bold red]: 数据目录不存在：{data_dir}\n\n"
                "请先下载 ChemBench 数据集：\n"
                "[bold]git clone --depth=1 https://github.com/lamalab-org/chembench.git "
                "benchmarks/data/chembench-repo[/bold]\n\n"
                "然后用 --data-dir 指定 data 子目录，例如：\n"
                "[bold]--data-dir benchmarks/data/chembench-repo/data[/bold]",
                title="数据集未找到",
                border_style="red",
            )
        )
        sys.exit(1)

    # ── 导入 ChemBench ───────────────────────────────────────────────────────
    try:
        from chembench.task import TaskRegistry
    except ImportError:
        console.print(
            "[bold red]错误[/bold red]: 未找到 chembench 包。\n"
            "请先安装：[bold]pip install chembench[/bold]"
        )
        sys.exit(1)

    # ── 构造配置 ─────────────────────────────────────────────────────────────
    from benchmarks.chembench.runner import RunnerConfig, ChemBenchRunner

    config = RunnerConfig(
        timeout_per_question = timeout,
        concurrency          = concurrency,
        limit                = limit,
        subset_keywords      = list(subset),
        verbose              = not quiet,
    )
    if run_id:
        config.run_id = run_id

    # ── 加载 benchmark ───────────────────────────────────────────────────────
    if data_dir.lower() == "hf":
        console.print("[cyan]正在从 HuggingFace (镜像站) 加载全量 ChemBench 数据集...[/cyan]")
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        benchmark = TaskRegistry.from_huggingface("jablonkagroup/ChemBench")
    else:
        console.print(f"[cyan]正在从本地目录加载 ChemBench 数据集：{data_dir}[/cyan]")
        benchmark = TaskRegistry.from_directory(data_dir)
        
    total_tasks = sum(len(tq.tasks) if hasattr(tq, 'tasks') else len(tq) for tq in benchmark.topics.values())
    console.print(f"[green]已加载 {len(benchmark.topics)} 个 topic，共 {total_tasks} 道题[/green]")

    # ── 启动 ─────────────────────────────────────────────────────────────────
    runner = ChemBenchRunner(config)
    runner.setup()

    asyncio.run(runner.run(benchmark))


if __name__ == "__main__":
    main()
