"""
Base runner for ChemBench comparison benchmarks.

Provides the shared orchestration logic used by all comparison runners:
- load benchmark
- filter questions by keyword / limit
- invoke the underlying agent (OpenCode, Cloudra CLI, etc.)
- extract and score answers
- persist results via BenchmarkReporter
"""

from __future__ import annotations

import math
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from benchmarks.chembench.adapter import question_to_query
from benchmarks.chembench.evaluator import extract_answer, score_result
from benchmarks.chembench.report import BenchmarkReporter, QuestionResult
from benchmarks.chembench.utils import get_field


@dataclass
class BaseRunnerConfig:
    """Shared configuration for all comparison runners."""

    data_dir: str | Path
    timeout_per_question: float = 300.0
    limit: Optional[int] = None
    subset_keywords: list[str] = field(default_factory=list)
    verbose: bool = True
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    max_retries: int = 2


class BaseRunner(ABC):
    """
    Abstract base for running a ChemBench benchmark through a single agent backend.

    Subclasses only need to implement `_invoke(prompt)` to call their specific
    backend (e.g. `opencode run`, `cloudra run --yolo`).
    """

    name: str = "base"

    def __init__(self, config: BaseRunnerConfig, namespace: str):
        self.config = config
        self.namespace = namespace
        self._reporter = BenchmarkReporter(config.run_id, namespace=namespace)

    def run(self, benchmark) -> None:
        """Run all filtered questions through the backend and persist results."""
        all_tasks = [task for tq in benchmark.topics.values() for task in tq.tasks]
        questions = list(self._filter_questions(all_tasks))
        total = len(questions)

        if self.config.verbose:
            self._log(f"共 {total} 题，run_id={self.config.run_id}，输出目录: {self._reporter.output_dir}")

        for idx, q in enumerate(questions):
            result = self._run_question(idx, total, q)
            self._reporter.record(result)

        summary = self._reporter.finalize(config_snapshot=self._config_snapshot())
        if self.config.verbose:
            self._print_summary(summary)
        return summary

    def _run_question(self, idx: int, total: int, question: Any) -> QuestionResult:
        """Run a single question, time it, extract the answer, and score it."""
        q_uuid = get_field(question, "uuid", f"q{idx:04d}")
        q_name = get_field(question, "name", q_uuid)
        query = question_to_query(question)

        if self.config.verbose:
            self._log(f"[{idx+1}/{total}] {q_name} ({q_uuid[:16]}...)")

        t0 = time.monotonic()
        timed_out = False
        raw_output = ""
        attempt = 0
        max_retries = max(0, self.config.max_retries)

        while attempt <= max_retries:
            attempt += 1
            single_t0 = time.monotonic()
            try:
                raw_output = self._invoke(query)
            except TimeoutError:
                timed_out = True
                self._log(f"  [超时] {q_name} (attempt {attempt})", warn=True)
                raw_output = ""
            except Exception as exc:
                self._log(f"  [异常] {q_name}: {exc} (attempt {attempt})", warn=True)
                raw_output = ""

            elapsed = time.monotonic() - t0
            extracted = extract_answer(raw_output)

            # Retry if we got nothing useful and still have retries left.
            if extracted is None and attempt <= max_retries and (elapsed + 5) < self.config.timeout_per_question:
                self._log(f"  [重试] {q_name}: 未提取到答案 (attempt {attempt})", warn=True)
                continue
            break

        elapsed = time.monotonic() - t0
        metrics = score_result(extracted, question)
        correct_flag = "✓" if metrics.get("all_correct") else "✗"

        if self.config.verbose:
            self._log(
                f"  {correct_flag} answer={extracted!r}  "
                f"({elapsed:.1f}s{'  TIMEOUT' if timed_out else ''})"
            )

        return QuestionResult(
            uuid=q_uuid,
            name=q_name,
            conversation_id="",  # CLI runners do not expose conversation IDs
            query=query,
            raw_output=raw_output,
            extracted_answer=extracted,
            preferred_score=get_field(question, "preferred_score", ""),
            targets=get_field(question, "targets", []),
            keywords=get_field(question, "keywords", []),
            metrics=metrics,
            elapsed_seconds=round(elapsed, 2),
            timed_out=timed_out,
        )

    @abstractmethod
    def _invoke(self, prompt: str) -> str:
        """Invoke the agent backend with the given prompt and return raw text."""
        raise NotImplementedError

    def _config_snapshot(self) -> dict:
        """Override to include backend-specific metadata in the summary."""
        return {
            "runner": self.name,
            "namespace": self.namespace,
            "timeout_per_question": self.config.timeout_per_question,
            "limit": self.config.limit,
            "subset_keywords": self.config.subset_keywords,
        }

    def _filter_questions(self, questions: list) -> Iterator[Any]:
        """Filter questions by subset keywords and limit."""
        kw_filter = [k.lower() for k in self.config.subset_keywords]
        count = 0
        for q in questions:
            if kw_filter:
                q_kws = [k.lower() for k in get_field(q, "keywords", [])]
                if not any(k in q_kws for k in kw_filter):
                    continue
            yield q
            count += 1
            if self.config.limit and count >= self.config.limit:
                break

    def _log(self, msg: str, warn: bool = False) -> None:
        color = "\033[93m" if warn else "\033[96m"
        reset = "\033[0m"
        print(f"{color}[{self.name}]{reset} {msg}", flush=True)

    def _print_summary(self, summary) -> None:
        print(f"\n{'='*50}")
        print(f"{self.name} 评测汇总")
        print(f"  run_id  : {summary.run_id}")
        print(f"  总题数  : {summary.total}")
        print(f"  已作答  : {summary.answered}")
        print(f"  超时    : {summary.timed_out}")
        print(f"  总正确率: {summary.accuracy:.1%}")
        print(f"  MC 正确率: {summary.mc_accuracy:.1%}")
        if not math.isnan(summary.mae_mean):
            print(f"  数值题 MAE 均值: {summary.mae_mean:.4f}")
        print(f"{'='*50}\n")
