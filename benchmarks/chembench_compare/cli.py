"""
Unified CLI for ChemBench CLI-vs-CLI comparison benchmarks.

Both backends are invoked through their respective CLIs:
  - OpenCode: `opencode run`
  - Cloudra:  `cloudra run --new --yolo`

Subcommands:
  run       Run a ChemBench benchmark through a selected CLI backend.
  compare   Compare two existing benchmark runs.

Usage examples:
  chembench-compare run --runner opencode --limit 10 --run-id opencode_v1
  chembench-compare run --runner cloudra-cli --limit 10 --run-id cloudra_cli_v1
  chembench-compare compare --baseline opencode_v1 --treatment cloudra_cli_v1
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
from cloudra.config import get_config
from rich.console import Console
from rich.panel import Panel

console = Console()

_DEFAULT_DATA_DIR = str(
    (Path(__file__).resolve().parent.parent / "data" / "chembench-repo" / "data").resolve()
)


@click.group(context_settings={"max_content_width": 100})
def cli():
    """ChemBench CLI-vs-CLI comparison benchmark CLI."""
    pass


@cli.command(name="run")
@click.option(
    "--runner", "-r",
    type=click.Choice(["opencode", "cloudra-cli"], case_sensitive=False),
    required=True,
    help="后端 runner：opencode 或 cloudra-cli",
)
@click.option(
    "--data-dir", "-d",
    default=_DEFAULT_DATA_DIR, show_default=True,
    help="ChemBench 本地数据目录",
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
    "--run-id",
    default=None,
    help="自定义 run_id",
)
@click.option(
    "--opencode-model",
    default=None,
    help="OpenCode 模型名（仅 opencode runner 有效）",
)
@click.option(
    "--quiet", "-q",
    is_flag=True, default=False,
    help="静默模式，不打印逐题进度",
)
@click.option(
    "--max-retries",
    type=int, default=2, show_default=True,
    help="答案提取失败或调用异常时的最大重试次数",
)
def run_cmd(
    runner: str,
    data_dir: str,
    limit: int | None,
    subset: tuple,
    timeout: float,
    run_id: str | None,
    opencode_model: str | None,
    quiet: bool,
    max_retries: int,
):
    """使用指定 CLI 后端 runner 评测 ChemBench。"""
    from benchmarks.chembench_compare.runners import NAMESPACE_MAP
    from benchmarks.chembench_compare.runners.base import BaseRunnerConfig

    if not Path(data_dir).exists():
        console.print(
            Panel(
                f"[bold red]错误[/bold red]: 数据目录不存在：{data_dir}",
                title="数据集未找到",
                border_style="red",
            )
        )
        sys.exit(1)

    try:
        from chembench.task import TaskRegistry
    except ImportError:
        console.print(
            "[bold red]错误[/bold red]: 未找到 chembench 包。\n"
            "请先安装：[bold]pip install chembench[/bold]"
        )
        sys.exit(1)

    console.print(f"[cyan]正在从本地目录加载 ChemBench 数据集：{data_dir}[/cyan]")
    benchmark = TaskRegistry.from_directory(data_dir)
    total_tasks = sum(len(tq.tasks) for tq in benchmark.topics.values())
    console.print(f"[green]已加载 {len(benchmark.topics)} 个 topic，共 {total_tasks} 道题[/green]")

    namespace = NAMESPACE_MAP[runner]
    runner_key = runner.lower()

    if runner_key == "opencode":
        from benchmarks.chembench_compare.runners.opencode import OpenCodeRunner
        config = BaseRunnerConfig(
            data_dir=data_dir,
            timeout_per_question=timeout,
            limit=limit,
            subset_keywords=list(subset),
            verbose=not quiet,
            run_id=run_id or f"opencode_{__import__('uuid').uuid4().hex[:8]}",
            max_retries=max_retries,
        )
        instance = OpenCodeRunner(config, namespace, opencode_model=opencode_model)

    elif runner_key == "cloudra-cli":
        from benchmarks.chembench_compare.runners.cloudra_cli import CloudraCliRunner
        config = BaseRunnerConfig(
            data_dir=data_dir,
            timeout_per_question=timeout,
            limit=limit,
            subset_keywords=list(subset),
            verbose=not quiet,
            run_id=run_id or f"cloudra_cli_{__import__('uuid').uuid4().hex[:8]}",
            max_retries=max_retries,
        )
        instance = CloudraCliRunner(config, namespace)

    else:
        console.print(f"[bold red]错误[/bold red]: 未知 runner：{runner}")
        sys.exit(1)

    instance.run(benchmark)


@cli.command(name="compare")
@click.option(
    "--baseline", "-b",
    required=True,
    help="Baseline 运行的 run_id 或目录路径",
)
@click.option(
    "--treatment", "-t",
    required=True,
    help="Treatment 运行的 run_id 或目录路径",
)
@click.option(
    "--baseline-mode",
    type=click.Choice(["opencode", "cloudra-cli"], case_sensitive=False),
    default="opencode",
    show_default=True,
    help="Baseline 结果来源",
)
@click.option(
    "--treatment-mode",
    type=click.Choice(["opencode", "cloudra-cli"], case_sensitive=False),
    default="cloudra-cli",
    show_default=True,
    help="Treatment 结果来源",
)
@click.option(
    "--baseline-label",
    default="Baseline",
    help="Baseline 在报告中显示的名称",
)
@click.option(
    "--treatment-label",
    default="Treatment",
    help="Treatment 在报告中显示的名称",
)
@click.option(
    "--output", "-O",
    default=None,
    help="对比报告输出目录（默认自动生成）",
)
def compare_cmd(
    baseline: str,
    treatment: str,
    baseline_mode: str,
    treatment_mode: str,
    baseline_label: str,
    treatment_label: str,
    output: str | None,
):
    """合并两个 ChemBench CLI 运行结果，生成对比报告。"""
    from benchmarks.chembench_compare.compare import compare_runs, write_report
    from benchmarks.chembench_compare.runners import NAMESPACE_MAP

    baseline_namespace = NAMESPACE_MAP[baseline_mode]
    treatment_namespace = NAMESPACE_MAP[treatment_mode]

    baseline_dir = _resolve_run_dir(baseline, baseline_namespace)
    treatment_dir = _resolve_run_dir(treatment, treatment_namespace)

    missing = []
    if not baseline_dir.exists():
        missing.append(f"Baseline 运行目录: {baseline_dir}")
    if not treatment_dir.exists():
        missing.append(f"Treatment 运行目录: {treatment_dir}")
    if missing:
        console.print(
            Panel(
                "[bold red]错误[/bold red]: 找不到以下运行目录:\n" + "\n".join(missing),
                title="运行目录不存在",
                border_style="red",
            )
        )
        sys.exit(1)

    if output is None:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = Path(get_config().data_dir) / "benchmarks" / "chembench-compare" / "reports" / f"compare_{ts}"
    else:
        output_dir = Path(output)

    console.print(f"[cyan]正在读取 Baseline ({baseline_mode}) 结果: {baseline_dir}[/cyan]")
    console.print(f"[cyan]正在读取 Treatment ({treatment_mode}) 结果: {treatment_dir}[/cyan]")

    report = compare_runs(baseline_dir, treatment_dir)
    report.labels = {"baseline": baseline_label, "treatment": treatment_label}
    write_report(report, output_dir, labels={"baseline": baseline_label, "treatment": treatment_label})

    console.print(f"[green]对比报告已写入: {output_dir}[/green]")
    console.print(f"  - {output_dir / 'comparison.json'}")
    console.print(f"  - {output_dir / 'comparison.md'}")
    console.print(f"  - {output_dir / 'per_question.csv'}")

    console.print("")
    console.print(
        f"[bold]总正确率[/bold]: {baseline_label} {report.baseline.accuracy:.1%} vs "
        f"{treatment_label} {report.treatment.accuracy:.1%} "
        f"([bold]{'+' if report.accuracy_delta >= 0 else ''}{report.accuracy_delta:.1%}[/bold])"
    )
    console.print(f"[bold]{treatment_label} 单独答对[/bold]: {sum(q.only_treatment for q in report.questions)} 题")
    console.print(f"[bold]{baseline_label} 单独答对[/bold]: {sum(q.only_baseline for q in report.questions)} 题")


def _resolve_run_dir(run_id_or_path: str, namespace: str) -> Path:
    """Resolve a run_id or directory path to an absolute run directory."""
    p = Path(run_id_or_path)
    if p.exists() and p.is_dir():
        return p

    data_dir = Path(get_config().data_dir)
    return data_dir / "benchmarks" / namespace / run_id_or_path


if __name__ == "__main__":
    cli()
