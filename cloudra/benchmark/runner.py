"""Independent benchmark runner.

Runs benchmark tasks in isolated per-task sandboxes under a *separate* data
directory (not the conversation data_dir), then scores each run through the
three-layer forensic pipeline (integrity -> self-consistency -> accuracy) and
persists results to a dedicated benchmark SQLite database. The runner never
touches the live conversation store.

This is the orchestration skeleton: `run_task` prepares the sandbox, invokes
the (pluggable) agent backend, then scores. The agent backend is injected so
the runner stays decoupled from runtime_v2 wiring; a default no-op backend is
provided for dry-run / pipeline testing.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cloudra.benchmark.accuracy import AccuracyReport, score_accuracy
from cloudra.benchmark.graph_similarity import GedConfig, GedResult, mechanism_similarity
from cloudra.benchmark.integrity import IntegrityReport, audit_integrity
from cloudra.benchmark.schema import TaskSpec
from cloudra.benchmark.selfconsistency import SelfConsistencyReport, audit_self_consistency

# Agent backend signature: given (task, sandbox_dir) it runs the agent and
# returns the agent-reported barrier (kcal/mol) if it reported one.
AgentBackend = Callable[[TaskSpec, Path], Optional[float]]


@dataclass
class RunResult:
    task_id: str
    sandbox: str
    integrity_passed: bool = False
    graph_score: float = 0.0
    selfconsistency_passed: bool = False
    accuracy_score: float = 0.0
    final_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_row(self) -> tuple:
        return (
            self.task_id,
            self.sandbox,
            int(self.integrity_passed),
            self.graph_score,
            int(self.selfconsistency_passed),
            self.accuracy_score,
            self.final_score,
            json.dumps(self.notes, ensure_ascii=False),
            int(time.time()),
        )


class BenchmarkDB:
    """Dedicated SQLite store for benchmark results, in its own data dir."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init(self) -> None:
        # sqlite3 的 with 块只管 commit/rollback、不管关闭，外层套 closing
        with closing(self._connect()) as c, c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    task_id TEXT, sandbox TEXT,
                    integrity_passed INTEGER, graph_score REAL,
                    selfconsistency_passed INTEGER, accuracy_score REAL,
                    final_score REAL, notes TEXT, ts INTEGER
                )"""
            )

    def record(self, result: RunResult) -> None:
        with closing(self._connect()) as c, c:
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)", result.to_row()
            )


def _default_backend(task: TaskSpec, sandbox: Path) -> Optional[float]:
    """No-op backend: creates the sandbox and returns no barrier. Used for
    pipeline dry-runs; real runs inject a runtime_v2-backed backend."""
    sandbox.mkdir(parents=True, exist_ok=True)
    return None


class BenchmarkRunner:
    def __init__(
        self,
        data_dir: Path,
        backend: Optional[AgentBackend] = None,
        ged_config: Optional[GedConfig] = None,
    ):
        self.data_dir = Path(data_dir)
        self.sandboxes = self.data_dir / "sandboxes"
        self.sandboxes.mkdir(parents=True, exist_ok=True)
        self.db = BenchmarkDB(self.data_dir / "benchmark.db")
        self.backend = backend or _default_backend
        self.ged_config = ged_config or GedConfig()

    def sandbox_for(self, task_id: str) -> Path:
        return self.sandboxes / task_id

    def _ged_config_for(self, task: TaskSpec) -> GedConfig:
        """Per-task GED 参数（rubric.graph_similarity）覆盖 runner 默认值。"""
        base = self.ged_config
        gs = task.rubric.graph_similarity
        return GedConfig(
            sigmoid_center=gs.sigmoid_center,
            sigmoid_steepness=(
                gs.sigmoid_steepness
                if gs.sigmoid_steepness is not None
                else base.sigmoid_steepness
            ),
            node_delete_cost=base.node_delete_cost,
            node_insert_cost=base.node_insert_cost,
            edge_delete_cost=base.edge_delete_cost,
            edge_insert_cost=base.edge_insert_cost,
            morgan_radius=base.morgan_radius,
            morgan_nbits=base.morgan_nbits,
        )

    def score_sandbox(self, task: TaskSpec, sandbox: Path, agent_barrier: Optional[float]) -> RunResult:
        res = RunResult(task_id=task.task_id, sandbox=str(sandbox))
        ged_config = self._ged_config_for(task)

        integ: IntegrityReport = audit_integrity(sandbox, task.rubric.integrity, ged_config)
        res.integrity_passed = integ.passed
        res.notes.extend(integ.notes)

        if integ.delivered_graph is not None:
            ged: GedResult = mechanism_similarity(
                integ.delivered_graph, task.gold.mechanism_graph, ged_config
            )
            res.graph_score = ged.score
        else:
            res.graph_score = 0.0
            res.notes.append("no delivered graph to compare")

        sc: SelfConsistencyReport = audit_self_consistency(
            integ.evidence_files, sandbox, task.rubric.self_consistency
        )
        res.selfconsistency_passed = sc.passed
        res.notes.extend(sc.notes)

        acc: AccuracyReport = score_accuracy(
            agent_barrier, task.gold.reference_computation, task.rubric.accuracy
        )
        res.accuracy_score = acc.final_score
        res.notes.extend(acc.notes)

        # composite: integrity gates everything; then a weighted blend.
        if not res.integrity_passed:
            res.final_score = 0.0
            res.notes.append("integrity failed -> final score 0")
        else:
            res.final_score = round(
                0.5 * res.graph_score
                + 0.2 * (1.0 if res.selfconsistency_passed else 0.0)
                + 0.3 * res.accuracy_score,
                4,
            )
        return res

    def run_task(self, task: TaskSpec) -> RunResult:
        sandbox = self.sandbox_for(task.task_id)
        # 复跑从干净沙箱开始：上一轮的证据文件残留会污染取证扫描
        if sandbox.exists():
            shutil.rmtree(sandbox)
        agent_barrier = self.backend(task, sandbox)
        result = self.score_sandbox(task, sandbox, agent_barrier)
        self.db.record(result)
        return result

    def run_all(self, tasks: list[TaskSpec]) -> list[RunResult]:
        return [self.run_task(t) for t in tasks]


def load_tasks(tasks_dir: Path) -> list[TaskSpec]:
    out = []
    for p in sorted(Path(tasks_dir).glob("*.json")):
        out.append(TaskSpec.model_validate(json.loads(p.read_text(encoding="utf-8"))))
    return out
