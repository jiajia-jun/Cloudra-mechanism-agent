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

Scoring reads **only deliverables** (the delivered mechanism graph JSON, the
`smiles:`-annotated logs in the sandbox, and the optional structured refusal
declaration) — never the LLM's prose. Every run is classified into a
behaviour outcome (answered/refused/failed, see `refusal.py`): a parseable
delivered graph is an answer, an explicit structured refusal declaration is a
refusal, anything else is failed. Refusal is a first-class, tier-agnostic
outcome, and the impossible tier's main metric is the cross-tier refusal
precision/recall, not a per-tier refusal rate.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cloudra.benchmark.accuracy import AccuracyReport, score_accuracy
from cloudra.benchmark.barrier_evidence import (
    BarrierEvidence,
    collect_barrier_evidence,
    load_refusal_declaration,
)
from cloudra.benchmark.graph_similarity import GedConfig, GedResult, mechanism_similarity
from cloudra.benchmark.integrity import IntegrityReport, audit_integrity
from cloudra.benchmark.refusal import RunOutcome, classify_outcome
from cloudra.benchmark.schema import TaskSpec
from cloudra.benchmark.selfconsistency import SelfConsistencyReport, audit_self_consistency

# Agent backend signature: given (task, sandbox_dir) it runs the agent to
# completion.  It returns nothing: every scoring input is a deliverable on
# disk (交付物是唯一事实来源), so the backend cannot feed the scorer.
AgentBackend = Callable[[TaskSpec, Path], None]


@dataclass
class RunResult:
    task_id: str
    sandbox: str
    integrity_passed: bool = False
    graph_score: float = 0.0
    selfconsistency_passed: bool = False
    accuracy_score: float = 0.0
    final_score: float = 0.0
    # 拒答分类（answered/refused/failed，见 refusal.RunOutcome）；与得分正交：
    # 拒答题 final_score 照常按零交付算（其他档拒答自然零分），outcome 只服务
    # 跨档拒答 precision/recall 统计。
    outcome: str = RunOutcome.FAILED.value
    notes: list[str] = field(default_factory=list)
    # 批次归属（Web 控制面；CLI 单批跑时为空串）。
    batch_id: str = ""

    def to_row(self) -> tuple:
        return (
            self.task_id,
            self.sandbox,
            int(self.integrity_passed),
            self.graph_score,
            int(self.selfconsistency_passed),
            self.accuracy_score,
            self.final_score,
            self.outcome,
            json.dumps(self.notes, ensure_ascii=False),
            int(time.time()),
            self.batch_id,
        )


_RUNS_DDL = """CREATE TABLE IF NOT EXISTS runs (
    task_id TEXT, sandbox TEXT,
    integrity_passed INTEGER, graph_score REAL,
    selfconsistency_passed INTEGER, accuracy_score REAL,
    final_score REAL, outcome TEXT, notes TEXT, ts INTEGER,
    batch_id TEXT
)"""

_BATCHES_DDL = """CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY, status TEXT, config TEXT,
    started_at INTEGER, finished_at INTEGER
)"""

# runs 表的既有列序（batch_id 之前的部分）：旧库缺新列时整表按新列序重建。
_RUNS_LEGACY_COLS = (
    "task_id", "sandbox", "integrity_passed", "graph_score",
    "selfconsistency_passed", "accuracy_score", "final_score",
    "outcome", "notes", "ts",
)


class BenchmarkDB:
    """Dedicated SQLite store for benchmark results, in its own data dir."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 并行跑题时多个 worker 线程共写同一库；sqlite 的 busy 等待是概率性
        # 兜底， determinism 靠这把进程内锁。
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init(self) -> None:
        # sqlite3 的 with 块只管 commit/rollback、不管关闭，外层套 closing
        with closing(self._connect()) as c, c:
            c.execute(_RUNS_DDL)
            c.execute(_BATCHES_DDL)
            # outcome / batch_id 列是后加的：旧库按新列序整表重建（ALTER ADD
            # COLUMN 会把新列追加到末尾，与 to_row 的位置序不一致）。旧行没有
            # 拒答分类信息，按 'failed'（未知）记——refused 统计只看
            # outcome='refused'，不受影响；batch_id 按空串记。
            cols = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
            if "outcome" not in cols or "batch_id" not in cols:
                c.execute("ALTER TABLE runs RENAME TO runs_old")
                c.execute(_RUNS_DDL)
                insert_cols = [name for name in _RUNS_LEGACY_COLS if name in cols]
                select_exprs = list(insert_cols)
                if "outcome" not in cols:
                    # 旧行没有拒答分类信息：按 'failed'（未知）记
                    insert_cols.append("outcome")
                    select_exprs.append("'failed'")
                # batch_id 缺省时旧行保持 NULL（不挂任何批次）
                c.execute(
                    f"INSERT INTO runs ({', '.join(insert_cols)}) "
                    f"SELECT {', '.join(select_exprs)} FROM runs_old"
                )
                c.execute("DROP TABLE runs_old")

    def record(self, result: RunResult) -> None:
        # latest-result-per-task：复跑先删该题旧行再插入，runs 表每题恒一行
        with self._lock, closing(self._connect()) as c, c:
            c.execute("DELETE FROM runs WHERE task_id = ?", (result.task_id,))
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", result.to_row()
            )

    def record_batch(self, batch_id: str, status: str, config: dict) -> None:
        """批次 upsert（Web 控制面）：config 是启动参数快照。"""
        with self._lock, closing(self._connect()) as c, c:
            c.execute(
                """INSERT INTO batches (batch_id, status, config, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET status=excluded.status""",
                (batch_id, status, json.dumps(config, ensure_ascii=False), int(time.time()), None),
            )

    def finish_batch(self, batch_id: str, status: str) -> None:
        with self._lock, closing(self._connect()) as c, c:
            c.execute(
                "UPDATE batches SET status = ?, finished_at = ? WHERE batch_id = ?",
                (status, int(time.time()), batch_id),
            )

    def list_batches(self, limit: int = 20) -> list[dict]:
        with self._lock, closing(self._connect()) as c:
            rows = c.execute(
                "SELECT batch_id, status, config, started_at, finished_at "
                "FROM batches ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for batch_id, status, config, started_at, finished_at in rows:
            cfg = {}
            try:
                cfg = json.loads(config or "{}")
            except Exception:
                pass
            out.append({
                "batch_id": batch_id,
                "status": status,
                "config": cfg,
                "started_at": started_at,
                "finished_at": finished_at,
            })
        return out

    def list_runs_for(self, batch_id: str) -> list[dict]:
        with self._lock, closing(self._connect()) as c:
            rows = c.execute(
                "SELECT task_id, sandbox, integrity_passed, graph_score, "
                "selfconsistency_passed, accuracy_score, final_score, outcome, "
                "notes, ts FROM runs WHERE batch_id = ? ORDER BY task_id",
                (batch_id,),
            ).fetchall()
        out = []
        for task_id, sandbox, integrity, graph, selfc, acc, final, outcome, notes, ts in rows:
            parsed = []
            try:
                parsed = json.loads(notes or "[]")
            except Exception:
                pass
            out.append({
                "task_id": task_id,
                "sandbox": sandbox,
                "integrity_passed": bool(integrity),
                "graph_score": graph,
                "selfconsistency_passed": bool(selfc),
                "accuracy_score": acc,
                "final_score": final,
                "outcome": outcome,
                "notes": parsed,
                "ts": ts,
            })
        return out


def _default_backend(task: TaskSpec, sandbox: Path) -> None:
    """No-op backend: creates the sandbox and returns. Used for pipeline
    dry-runs; real runs inject a runtime_v2-backed backend."""
    sandbox.mkdir(parents=True, exist_ok=True)


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
            # hard 档立体化学计代价；easy/normal 忽略立体（stereo_free）
            stereo_free=gs.stereo_tier_rule == "easy_normal_stereo_free",
            subgraph_scoring=gs.subgraph_scoring,
            node_delete_cost=base.node_delete_cost,
            node_insert_cost=base.node_insert_cost,
            edge_delete_cost=base.edge_delete_cost,
            edge_insert_cost=base.edge_insert_cost,
            morgan_radius=base.morgan_radius,
            morgan_nbits=base.morgan_nbits,
        )

    def score_sandbox(self, task: TaskSpec, sandbox: Path) -> RunResult:
        """按交付物评分：图（JSON）+ 日志 + 结构化拒答声明，不读任何散文。"""
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

        barriers: BarrierEvidence = collect_barrier_evidence(sandbox)
        res.notes.extend(barriers.notes)
        acc: AccuracyReport = score_accuracy(
            evidence=barriers,
            gold=task.gold.reference_computation,
            rubric=task.rubric.accuracy,
        )
        res.accuracy_score = acc.final_score
        res.notes.extend(acc.notes)

        # composite: integrity 不再一票否决，证据质量是分级因子——
        # 证据完整且机理正确得满分；缺证据按 binding_quality 比例扣（缺一个
        # 不判零）；完全没证据（图缺失/不可解析/零绑定）倒扣 no_evidence_penalty
        # 分：无证据支撑的机理声明比没交付更糟。
        blend = (
            0.5 * res.graph_score
            + 0.2 * (1.0 if res.selfconsistency_passed else 0.0)
            + 0.3 * res.accuracy_score
        )
        rub = task.rubric.integrity
        if not (rub.require_graph_json and rub.require_evidence_files):
            res.final_score = round(blend, 4)
        elif not integ.graph_parseable:
            res.final_score = -rub.no_evidence_penalty
            res.notes.append("no parseable mechanism graph -> no evidence possible; penalty applied")
        elif integ.binding_quality <= 0.0:
            res.final_score = -rub.no_evidence_penalty
            res.notes.append("no evidence bound to any graph node -> unsupported claims; penalty applied")
        else:
            res.final_score = round(blend * integ.binding_quality, 4)
            if integ.binding_quality < 1.0:
                res.notes.append(
                    f"binding quality {integ.binding_quality:.2f} applied as composite multiplier"
                )

        # 行为分类只认可解析的交付图（损坏或只带拒答声明的文件不算作答）与
        # 显式结构化拒答声明；散文一律不参与判定。
        delivered_graph = integ.delivered_graph
        res.outcome = classify_outcome(
            graph_found=delivered_graph is not None and bool(delivered_graph.nodes),
            refusal_declared=load_refusal_declaration(sandbox) is not None,
        ).value
        return res

    def run_task(self, task: TaskSpec) -> RunResult:
        sandbox = self.sandbox_for(task.task_id)
        # 复跑从干净沙箱开始：上一轮的证据文件残留会污染取证扫描。
        # 沙箱路径可能是上一轮后端留下的 symlink 或普通文件（rmtree 会抛 OSError）。
        if sandbox.is_symlink() or sandbox.is_file():
            sandbox.unlink()
        elif sandbox.exists():
            shutil.rmtree(sandbox)
        self.backend(task, sandbox)
        result = self.score_sandbox(task, sandbox)
        self.db.record(result)
        return result

    def _run_one_guarded(self, task: TaskSpec) -> RunResult:
        """单题异常不拖垮整批：失败题落一条 notes 带原因的零分结果行并继续。
        （后端崩溃记 0 而不是 no_evidence_penalty：基建失败不是 agent 的锅。）"""
        try:
            return self.run_task(task)
        except Exception as exc:
            print(f"[benchmark] task {task.task_id} crashed: {exc!r}")
            res = RunResult(
                task_id=task.task_id,
                sandbox=str(self.sandbox_for(task.task_id)),
                outcome=RunOutcome.FAILED.value,
            )
            res.notes.append(f"task crashed: {exc!r}")
            self.db.record(res)
            return res

    def run_all(self, tasks: list[TaskSpec], concurrency: int = 1) -> list[RunResult]:
        """串行（concurrency=1，默认）或受控并行。并行用线程池：单题都是
        IO 密集（LLM 请求 / 计算子进程），每题一个线程、线程内独立事件循环；
        沙箱按题隔离，benchmark.db 写入由 BenchmarkDB 内部锁串行化。"""
        if concurrency <= 1:
            return [self._run_one_guarded(t) for t in tasks]
        import concurrent.futures as cf

        results: dict[str, RunResult] = {}
        with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._run_one_guarded, t): t for t in tasks}
            for fut in cf.as_completed(futures):
                res = fut.result()
                results[res.task_id] = res
        return [results[t.task_id] for t in tasks]


def load_tasks(tasks_dir: Path) -> list[TaskSpec]:
    out = []
    for p in sorted(Path(tasks_dir).glob("*.json")):
        out.append(TaskSpec.model_validate(json.loads(p.read_text(encoding="utf-8"))))
    return out
