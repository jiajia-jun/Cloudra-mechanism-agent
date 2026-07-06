"""
ChemBenchRunner — 核心驱动模块。

架构说明
--------
每道 ChemBench 题目作为独立的 Cloudra 对话（Conversation）运行完整的
Coordinator → ReAct → (可选 Follower / Tool) → 最终答案 流程。

与原 run_chembench.py 的关键差异
---------------------------------
1. 不再绕过 Cloudra 系统直接调 LiteLLM；
   每题通过 ``run_task_async`` 走完整 Agent 管道。
2. 后台线程（checking_task / check_compute / approval_handler）
   只初始化一次，不随每题重启。
3. approval_handler 在 YOLO 模式下由 ``yolo_guard`` 自动裁定，
   不阻塞 CLI（``CLOUDRA_YOLO_MODE=true``）。
4. 结果写入 ``data_dir/benchmarks/chembench/<run_id>/``，
   并通过 ``conversation_id`` 关联到 Cloudra 对话系统，
   可通过 ``/conversations/{id}`` API 复现任意一题的推理过程。
5. 每题有独立超时（默认 300 s），超时视为无效答案而非崩溃。

并发策略
--------
默认 concurrency=1（顺序执行）保证结果可复现。
通过 ``--concurrency N`` 可启用 asyncio.Semaphore 限制的并发，
但并发 > 1 时多组 daemon 线程会同时轮询同一 SQLite，
WAL 模式足以支撑，实测 concurrency ≤ 4 无问题。
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

# Cloudra 核心模块
from cloudra.agent import Coordinator
from cloudra.config import get_config
from cloudra.conversation_class import Conversation
from cloudra.database import ConversationDB
from cloudra.main import (
    Color,
    _wait_for_background_tasks,
    approval_handler,
    check_compute,
    checking_task,
)
from cloudra.reAct import Coordinator_reAct

# Benchmark 子模块
from benchmarks.chembench.adapter import question_to_query
from benchmarks.chembench.evaluator import extract_answer, score_result
from benchmarks.chembench.report import BenchmarkReporter, QuestionResult


# ── 配置 ──────────────────────────────────────────────────────────────────────

@dataclass
class RunnerConfig:
    """ChemBench 运行配置，优先从 cloudra.config 读取，可被 CLI 参数覆盖。"""

    # 每题最大等待时间（秒）
    timeout_per_question: float = 300.0

    # 并发数（1 = 顺序执行）
    concurrency: int = 1

    # 只评测前 N 题（None = 全部）
    limit: Optional[int] = None

    # 只评测含指定关键词的题目（空列表 = 全部）
    subset_keywords: list[str] = field(default_factory=list)

    # 是否打印每题进度到 stdout
    verbose: bool = True

    # 手动指定 run_id（默认自动生成）
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")


# ── Runner ────────────────────────────────────────────────────────────────────

class _ConversationInfra:
    """为单个 conversation 启动后台 daemon 线程，并提供 stop_event 用于结束它们。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        """启动 checking_task / check_compute / approval_handler 三个后台线程。"""
        for target, name in (
            (checking_task, "chembench-checker"),
            (check_compute, "chembench-compute"),
            (approval_handler, "chembench-approval"),
        ):
            t = threading.Thread(
                target=target,
                args=(self.db_path, self.stop_event),
                daemon=True,
                name=name,
            )
            t.start()
            self.threads.append(t)

    def stop(self) -> None:
        """通知后台线程退出，并等待它们结束（最多 2 秒）。"""
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=2.0)


class ChemBenchRunner:
    """
    驱动 ChemBench 评测的核心类。

    使用方式：
        runner = ChemBenchRunner(config)
        summary = asyncio.run(runner.run(benchmark))
    """

    def __init__(self, config: RunnerConfig):
        self.config    = config
        self._reporter = BenchmarkReporter(config.run_id)

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        旧版入口兼容性方法。当前实现已把数据库/后台线程下放到每道题目，
        因此 setup() 不再需要做全局初始化。
        """
        pass

    def _start_conversation_infra(self, db_path: str) -> _ConversationInfra:
        """为单个 conversation 启动独立的后台线程。"""
        infra = _ConversationInfra(db_path)
        infra.start()
        return infra

    # ── 主流程 ────────────────────────────────────────────────────────────────

    async def run(self, benchmark) -> None:
        """
        遍历 benchmark 中的所有题目，逐题（或并发）运行 Cloudra 完整管道。

        Args:
            benchmark: chembench.benchmark.ChemBenchmark 对象，
                       其 .questions 属性为 question 列表。

        Returns:
            BenchmarkRun 汇总对象（同时写入 summary.json）。
        """
        all_tasks = [task for tq in benchmark.topics.values() for task in tq.tasks]
        questions = list(self._filter_questions(all_tasks))
        total     = len(questions)

        if self.config.verbose:
            _log(f"共 {total} 题，run_id={self.config.run_id}，"
                 f"输出目录: {self._reporter.output_dir}")

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def bounded_run(idx: int, q: Any) -> None:
            async with semaphore:
                result = await self._run_question(idx, total, q)
                self._reporter.record(result)

        await asyncio.gather(*[bounded_run(i, q) for i, q in enumerate(questions)])

        summary = self._reporter.finalize(config_snapshot=self._config_snapshot())
        if self.config.verbose:
            _print_summary(summary)
        return summary

    # ── 单题执行 ─────────────────────────────────────────────────────────────

    async def _run_question(self, idx: int, total: int, question: Any) -> QuestionResult:
        """在独立 Conversation 中运行一道题的完整 Cloudra 管道。"""
        q_uuid = _get_field(question, "uuid", f"q{idx:04d}")
        q_name = _get_field(question, "name", q_uuid)
        query  = question_to_query(question)

        if self.config.verbose:
            _log(f"[{idx+1}/{total}] {q_name} ({q_uuid[:16]}...)")

        conversation = Conversation(None)
        conversation.touch()

        # 每道题拥有独立的 conversation DB，彻底隔离并发写锁。
        conv_db = ConversationDB(conversation.id)
        conv_db.init()
        infra = self._start_conversation_infra(conv_db.path)

        t0 = time.monotonic()
        timed_out  = False
        raw_output = ""

        try:
            coordinator = Coordinator(
                query=query,
                conversation_id=conversation.id,
            )
            context = await coordinator.get_context()
            if not context or context[-1].get("content") != query:
                await coordinator.update_context({"role": "user", "content": query})

            react = Coordinator_reAct(coordinator)

            conversation.set_state("running")

            async def _run_with_events() -> str:
                """运行 ReAct 主循环，并在外层捕获限流进行指数退避重试，不污染核心代码。"""
                import time
                base_delay = 5.0
                
                async def safe_react_run() -> str:
                    for attempt in range(8):
                        try:
                            return await react.run()
                        except Exception as e:
                            err_str = str(e).lower()
                            if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                                sleep_time = base_delay * (1.5 ** attempt)
                                _log(f"  [API 节流] 拦截到 429 异常，暂停 {sleep_time:.1f} 秒后恢复推理 (第 {attempt+1} 次重试)", warn=True)
                                await asyncio.sleep(sleep_time)
                                continue
                            raise
                    return await react.run()

                result = await safe_react_run()
                while True:
                    await _wait_for_background_tasks(conv_db.path, conversation.id)
                    has_pending = await coordinator.context_manager.has_pending_events() \
                        if coordinator.context_manager else False
                    if not has_pending:
                        break
                    result = await safe_react_run()
                return result

            raw_output_reason = await asyncio.wait_for(
                _run_with_events(),
                timeout=self.config.timeout_per_question,
            )

            final_context = await coordinator.get_context()
            assistant_texts = [
                msg.get("content", "")
                for msg in final_context
                if msg.get("role") == "assistant" and isinstance(msg.get("content"), str)
            ]
            raw_output = "\n".join(assistant_texts) + "\n" + str(raw_output_reason)


        except asyncio.TimeoutError:
            timed_out = True
            _log(f"  [超时] {q_name}", warn=True)
        except Exception as exc:
            _log(f"  [异常] {q_name}: {exc}", warn=True)
        finally:
            infra.stop()
            if conversation.state != "archived":
                conversation.set_state("sleeping")

        elapsed        = time.monotonic() - t0
        extracted      = extract_answer(raw_output)
        metrics        = score_result(extracted, question)
        correct_flag   = "✓" if metrics.get("all_correct") else "✗"

        if self.config.verbose:
            _log(f"  {correct_flag} answer={extracted!r}  "
                 f"({elapsed:.1f}s{'  TIMEOUT' if timed_out else ''})")

        return QuestionResult(
            uuid             = q_uuid,
            name             = q_name,
            conversation_id  = conversation.id,
            query            = query,
            raw_output       = raw_output,
            extracted_answer = extracted,
            preferred_score  = _get_field(question, "preferred_score", ""),
            targets          = _get_field(question, "targets", []),
            keywords         = _get_field(question, "keywords", []),
            metrics          = metrics,
            elapsed_seconds  = round(elapsed, 2),
            timed_out        = timed_out,
        )

    # ── 题目过滤 ─────────────────────────────────────────────────────────────

    def _filter_questions(self, questions: list) -> Iterator[Any]:
        """按 subset_keywords 和 limit 过滤题目列表。"""
        kw_filter = [k.lower() for k in self.config.subset_keywords]
        count = 0
        for q in questions:
            if kw_filter:
                q_kws = [k.lower() for k in _get_field(q, "keywords", [])]
                if not any(k in q_kws for k in kw_filter):
                    continue
            yield q
            count += 1
            if self.config.limit and count >= self.config.limit:
                break

    def _config_snapshot(self) -> dict:
        cfg = get_config()
        return {
            "coordinator_model": cfg.coordinator.model,
            "coordinator_url":   cfg.coordinator.url,
            "follower_model":    cfg.follower.model,
            "yolo_mode":         os.environ.get("CLOUDRA_YOLO_MODE", "false"),
            "timeout_per_question": self.config.timeout_per_question,
            "concurrency":       self.config.concurrency,
            "limit":             self.config.limit,
            "subset_keywords":   self.config.subset_keywords,
        }


from benchmarks.chembench.utils import get_field


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_field(obj: Any, field: str, default: Any) -> Any:
    return get_field(obj, field, default)


def _log(msg: str, warn: bool = False) -> None:
    color = Color.YELLOW if warn else Color.CYAN
    print(f"{color}[ChemBench]{Color.END} {msg}", flush=True)


def _print_summary(summary) -> None:
    print(f"\n{Color.BLUE}{Color.BOLD}{'='*50}{Color.END}")
    print(f"{Color.BOLD}ChemBench 评测汇总{Color.END}")
    print(f"  run_id  : {summary.run_id}")
    print(f"  总题数  : {summary.total}")
    print(f"  已作答  : {summary.answered}")
    print(f"  超时    : {summary.timed_out}")
    print(f"  总正确率: {summary.accuracy:.1%}")
    print(f"  MC 正确率: {summary.mc_accuracy:.1%}")
    if not __import__('math').isnan(summary.mae_mean):
        print(f"  数值题 MAE 均值: {summary.mae_mean:.4f}")
    print(f"  输出目录: {_reporter_dir(summary.run_id)}")
    print(f"{Color.BLUE}{Color.BOLD}{'='*50}{Color.END}\n")


def _reporter_dir(run_id: str) -> Path:
    from benchmarks.chembench.report import _run_dir
    return _run_dir(run_id)
