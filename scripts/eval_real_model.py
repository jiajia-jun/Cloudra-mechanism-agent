"""可选的真实模型行为评测 —— 手工运行入口（评审 5.8 后半条）。不进 pytest / CI。

fake 自检（零 key，验证评测链路与检查面）：
    uv run python scripts/eval_real_model.py --provider fake --scenarios plain_qa \
        --out var/real_model_eval/fake-smoke.json

真实评测（显式开启；产生真实 API 调用与费用）：
    uv run python scripts/eval_real_model.py --provider real --confirm-real-api \
        --scenarios plain_qa,read_token --out var/real_model_eval/real-$(date +%F).json

结果 JSON 记录 model / endpoint（脱敏）/ prompt revision / tool catalog revision /
随机性参数，用于 prompt/model/protocol 版本之间的**趋势对比**；不设任何科学评分
阈值（阈值需用户确认）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:  # 直跑脚本时也能 import cloudra / tests
    sys.path.insert(0, str(REPO_ROOT))

from tests.real_model_eval import (  # noqa: E402
    RunOptions,
    real_run_precondition,
    run_all,
    summarize_lines,
    write_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可选真实模型行为评测（手工运行，不进 CI）")
    parser.add_argument("--provider", choices=("fake", "real"), default="fake")
    parser.add_argument(
        "--confirm-real-api",
        action="store_true",
        help="真实路径的显式开启（会产生真实 API 调用与费用；缺少它时直接拒绝）",
    )
    parser.add_argument("--scenarios", default="", help="逗号分隔的场景名（默认全部）")
    parser.add_argument("--out", default="", help="结果 JSON 路径（默认 var/real_model_eval/<provider>-<run_id>.json）")
    parser.add_argument("--work-dir", default="", help="场景工作目录（默认 var/real_model_eval）")
    parser.add_argument("--model", default="", help="覆盖模型名（默认取 config 槽位）")
    parser.add_argument("--base-url", default="", help="覆盖 endpoint（默认取 config 槽位）")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-llm-calls", type=int, default=12, help="单场景 LLM 调用预算（防无界烧 key）")
    parser.add_argument("--timeout", type=float, default=180.0, help="单场景超时（秒）")
    parser.add_argument(
        "--no-prompt-provider",
        action="store_true",
        help="不装真实 prompt 前缀（仅调试用；默认与 api_v2 生产装配一致）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.provider == "real":
        reason = real_run_precondition(opt_in=args.confirm_real_api)
        if reason:
            print(f"[拒绝] {reason}", file=sys.stderr)
            return 2
    scenario_names = [s.strip() for s in args.scenarios.split(",") if s.strip()] or None
    defaults = RunOptions()
    options = RunOptions(
        provider_kind=args.provider,
        work_dir=Path(args.work_dir) if args.work_dir else defaults.work_dir,
        timeout_s=args.timeout,
        max_llm_calls=args.max_llm_calls,
        model=args.model or None,
        base_url=args.base_url or None,
        temperature=args.temperature,
        prompt_provider=not args.no_prompt_provider,
        scenario_names=scenario_names,
    )
    document = asyncio.run(run_all(options))
    out_path = (
        Path(args.out)
        if args.out
        else options.work_dir / f"{args.provider}-{document['run_id']}.json"
    )
    written = write_results(document, out_path)
    for line in summarize_lines(document):
        print(line)
    print(f"\nresult json: {written}")
    return 0 if document["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
