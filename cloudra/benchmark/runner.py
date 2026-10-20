"""Independent benchmark runner.

Runs benchmark tasks in isolated per-task sandboxes under a *separate* data
directory (not the conversation data_dir), then scores each run through the
three-layer forensic pipeline (integrity -> self-consistency -> accuracy) and
persists results to a dedicated benchmark SQLite database. The runner never
touches the live conversation store.

Persistence is append-only and batch-scoped, because benchmark data is
precious: every scored run is a new row in ``runs`` (reruns never delete
history), every CLI/Web run carries a ``batch_id`` with a provenance snapshot
in ``batches.config`` (backend, per-task orchestration modes, model names,
plugins — never API keys), and sandboxes live under
``sandboxes/<task_id>/<batch_id>/`` so a rerun never wipes a previous run's
deliverables. Cleanup of old data is always an explicit user action.

This is the orchestration skeleton: `run_task` prepares the sandbox, invokes
the (pluggable) agent backend, then scores. The agent backend is injected so
the runner stays decoupled from runtime_v2 wiring; a default no-op backend is
provided for dry-run / pipeline testing.

Scoring reads **only deliverables** (the delivered mechanism graph JSON and the
`smiles:`-annotated logs in the sandbox) — never the LLM's prose.

Composite（权重是本模块的模块级常量）::

    final = W_GRAPH·graph + W_SELFCONSISTENCY·(selfconsistency ? 1 : 0)
            + W_ACCURACY·accuracy

- 自洽回捞（2026-09-25 用户裁决）：gold 边被交付步覆盖但该交付步自洽不合格
  → 该 gold 边在 graph_similarity 里赢下的覆盖贡献倒扣（违规交付边剔出
  交付图后重算 GED；同一 gold 边另有自洽合格的覆盖步则不受影响）；不在
  gold 子图里的额外交付边自洽不合格只落自洽层零分，不倒扣图分——gold 边
  出错与其他边出错严重程度不同；
- 图不可解析、或没有任何 accessible 物种节点绑到证据 →
  final = -rubric.integrity.no_evidence_penalty（零证据倒扣；交付图所有节点
  都声明 accessible=false 属合法交付，不触发本条）；
- accuracy 双来源核对 fail-loud（无据/不一致/缺声明）→ final = W_GRAPH·graph
  （自洽与 accuracy 分量清零，notes 写明）；
- 后端崩溃 → 0.0 行（基建失败不是 agent 的锅，不倒扣）。

绑定质量不做全局乘数：integrity 的逐节点绑定质量图直接并入图分
（graph_similarity：未绑定的 accessible 节点按代价 1.0 记账，质子化变体
部分扣）。

Hard-tier tasks with a ``gold.selectivity.favored_channel`` anchor put the
qualitative selectivity score in the accuracy slot (barrier spread is recorded,
not scored). Accuracy is scored per gold edge (see `accuracy.py`). Tier 不再
路由：impossible 档走同一套 composite（I 题的正确交付 = 同构图 + 不可达
元素标 accessible=false）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

from cloudra.benchmark.accuracy import (
    AccuracyReport,
    score_accuracy,
    score_qualitative_selectivity,
)
from cloudra.benchmark.barrier_evidence import BarrierEvidence, collect_barrier_evidence
from cloudra.benchmark.graph_similarity import (
    GedConfig,
    GedResult,
    mechanism_similarity,
    species_substitution_cost,
)
from cloudra.benchmark.integrity import IntegrityReport, audit_integrity
from cloudra.benchmark.schema import GoldMechanismGraph, MechanismEdge, NodeRole, TaskSpec
from cloudra.benchmark.selfconsistency import SelfConsistencyReport, audit_self_consistency

# composite 权重（2026-09-25 用户裁决）：final = 0.1·图 + 0.3·自洽 + 0.6·accuracy。
# 机理不对时 accuracy 层也会惩罚，图份额不该高；自洽层保持全有或全无（布尔）。
# accuracy 双来源核对 fail-loud 时自洽/accuracy 分量清零、只保留图分
# （final = W_GRAPH·graph）；图不可解析或没有任何 accessible 物种节点绑到
# 证据时倒扣 -rubric.integrity.no_evidence_penalty。
W_GRAPH = 0.1
W_SELFCONSISTENCY = 0.3
W_ACCURACY = 0.6

# Agent backend signature: given (task, sandbox_dir) it runs the agent to
# completion.  It returns nothing: every scoring input is a deliverable on
# disk (交付物是唯一事实来源), so the backend cannot feed the scorer.
AgentBackend = Callable[[TaskSpec, Path], None]


class BenchmarkStopped(RuntimeError):
    """The batch requested a cooperative stop; this task must not be scored."""


@dataclass
class RunResult:
    task_id: str
    sandbox: str
    graph_score: float = 0.0
    selfconsistency_passed: bool = False
    accuracy_score: float = 0.0
    final_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    # 批次归属（Web 控制面；CLI 每次调用也是一个批次）。空串 = 旧的未挂批记录。
    batch_id: str = ""
    # 行级消融臂标识（task.prompt.orchestration_mode）；旧行迁移为 ''。
    orchestration_mode: str = ""

    def to_row(self) -> tuple:
        return (
            self.task_id,
            self.sandbox,
            self.graph_score,
            int(self.selfconsistency_passed),
            self.accuracy_score,
            self.final_score,
            json.dumps(self.notes, ensure_ascii=False),
            int(time.time()),
            self.batch_id,
            self.orchestration_mode,
        )


_RUNS_DDL = """CREATE TABLE IF NOT EXISTS runs (
    task_id TEXT, sandbox TEXT, graph_score REAL,
    selfconsistency_passed INTEGER, accuracy_score REAL,
    final_score REAL, notes TEXT, ts INTEGER,
    batch_id TEXT, orchestration_mode TEXT
)"""

_BATCHES_DDL = """CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY, status TEXT, config TEXT,
    started_at INTEGER, finished_at INTEGER
)"""

# runs 表列序（与 RunResult.to_row 对齐）：迁移重建以它为准。
_RUNS_COLS = (
    "task_id", "sandbox", "graph_score", "selfconsistency_passed",
    "accuracy_score", "final_score", "notes", "ts",
    "batch_id", "orchestration_mode",
)


def task_project_settings(task: TaskSpec) -> dict:
    """CLI/Web task settings shared by every agent created in the project."""
    return {
        "benchmark_task_id": task.task_id,
        "orchestration_mode": task.prompt.orchestration_mode.value,
        "method_policy": task.method_policy.model_dump(mode="json"),
        "defaults": {"yolo": True, "unattended": True, "clean_context": True},
    }


def provenance_config(backend: str, tasks: list[TaskSpec]) -> dict:
    """批次溯源快照（CLI 与 Web 批次共用）：消融臂事后区分靠它。

    只记模型提供方/模型名，绝不记 API key。
    """
    from cloudra.infra.config import get_config

    cfg = get_config()
    return {
        "backend": backend,
        "orchestration_modes": {t.task_id: t.prompt.orchestration_mode.value for t in tasks},
        "models": {
            "coordinator": {"provider": cfg.coordinator.provider, "model": cfg.coordinator.model},
            "follower": {"provider": cfg.follower.provider, "model": cfg.follower.model},
        },
        "plugins": list(cfg.plugins),
    }


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
            # 旧库列集与新 DDL 不一致时整表按新列序重建：旧行全部保留、只迁移
            # 新旧交集列（被删的 outcome/integrity_passed 等旧列值丢弃，旧库
            # 没有的新列落 NULL——读取侧按 None/空串兜底）。不走 ALTER ADD
            # COLUMN：那会把新列追加到末尾，与 to_row 的位置序不一致。新库
            # 列集一致，幂等不再触发。
            cols = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
            if cols != set(_RUNS_COLS):
                c.execute("ALTER TABLE runs RENAME TO runs_old")
                c.execute(_RUNS_DDL)
                keep = [name for name in _RUNS_COLS if name in cols]
                c.execute(
                    f"INSERT INTO runs ({', '.join(keep)}) "
                    f"SELECT {', '.join(keep)} FROM runs_old"
                )
                c.execute("DROP TABLE runs_old")

    def record(self, result: RunResult) -> None:
        # append-only：benchmark 数据珍贵，历史行永不由框架删除；"每题最新"
        # 只是查询语义（按 ts 取），不落为破坏性写。
        with self._lock, closing(self._connect()) as c, c:
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", result.to_row()
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
                "SELECT task_id, sandbox, graph_score, selfconsistency_passed, "
                "accuracy_score, final_score, notes, ts, orchestration_mode "
                "FROM runs WHERE batch_id = ? ORDER BY task_id, ts",
                (batch_id,),
            ).fetchall()
        out = []
        for task_id, sandbox, graph, selfc, acc, final, notes, ts, orch in rows:
            parsed = []
            try:
                parsed = json.loads(notes or "[]")
            except Exception:
                pass
            out.append({
                "task_id": task_id,
                "sandbox": sandbox,
                "graph_score": graph,
                "selfconsistency_passed": bool(selfc),
                "accuracy_score": acc,
                "final_score": final,
                "notes": parsed,
                "ts": ts,
                "orchestration_mode": orch or "",
            })
        return out


def _default_backend(task: TaskSpec, sandbox: Path) -> None:
    """No-op backend: creates the sandbox and returns. Used for pipeline
    dry-runs; real runs inject a runtime_v2-backed backend."""
    sandbox.mkdir(parents=True, exist_ok=True)


def _covering_delivered_edge_ids(
    gold_edge: MechanismEdge,
    gold_graph: GoldMechanismGraph,
    delivered_graph: GoldMechanismGraph,
    cfg: GedConfig,
    match_threshold: float,
) -> list[str]:
    """覆盖某 gold 边的交付边 id 列表——accuracy 层 gold↔delivered 匹配的
    同口径（`_find_matching_step` 的端点物种判定：同向端点分别
    species_substitution_cost ≤ match_threshold；edge id 不参与匹配）。"""
    gold_nodes = {n.id: n for n in gold_graph.nodes}
    delivered_nodes = {n.id: n for n in delivered_graph.nodes}
    g_from, g_to = gold_nodes.get(gold_edge.from_node), gold_nodes.get(gold_edge.to_node)
    if g_from is None or g_to is None:
        return []
    out = []
    for e in delivered_graph.edges:
        d_from = delivered_nodes.get(e.from_node)
        d_to = delivered_nodes.get(e.to_node)
        if d_from is None or d_to is None:
            continue
        if species_substitution_cost(g_from.smiles, d_from.smiles, cfg) > match_threshold:
            continue
        if species_substitution_cost(g_to.smiles, d_to.smiles, cfg) > match_threshold:
            continue
        out.append(e.id)
    return out


class BenchmarkRunner:
    def __init__(
        self,
        data_dir: Path,
        backend: Optional[AgentBackend] = None,
        ged_config: Optional[GedConfig] = None,
        batch_id: str = "",
        stop_event: threading.Event | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.sandboxes = self.data_dir / "sandboxes"
        self.sandboxes.mkdir(parents=True, exist_ok=True)
        self.db = BenchmarkDB(self.data_dir / "benchmark.db")
        self.backend = backend or _default_backend
        self.ged_config = ged_config or GedConfig()
        self.batch_id = batch_id
        self.stop_event = stop_event if stop_event is not None else threading.Event()

    def sandbox_for(self, task_id: str, batch_id: str = "") -> Path:
        """题目沙箱：带批次 id 时按批分目录（``<task_id>/<batch_id>``）——
        每批新目录天然干净，上一批的交付物永久保留，复跑不再清空历史。"""
        base = self.sandboxes / task_id
        return base / batch_id if batch_id else base

    def _ged_config_for(self, task: TaskSpec) -> GedConfig:
        """Per-task GED 参数：stereo 是否计代价按 rubric.graph_similarity 的
        stereo_tier_rule，其余全用 runner 默认（per-task 数值覆盖已取消）。"""
        return replace(
            self.ged_config,
            # hard 档立体化学计代价；easy/normal 忽略立体（stereo_free）
            stereo_free=(
                task.rubric.graph_similarity.stereo_tier_rule
                == "easy_normal_stereo_free"
            ),
        )

    def score_sandbox(self, task: TaskSpec, sandbox: Path) -> RunResult:
        """按交付物评分：图（JSON）+ 日志，不读任何散文。"""
        res = RunResult(
            task_id=task.task_id,
            sandbox=str(sandbox),
            orchestration_mode=task.prompt.orchestration_mode.value,
        )
        ged_config = self._ged_config_for(task)

        integ: IntegrityReport = audit_integrity(sandbox, task.rubric.integrity, ged_config)
        res.notes.extend(integ.notes)

        # 逐节点绑定质量图并入图分：未绑定的 accessible 节点按代价 1.0 记账，
        # 质子化变体部分扣；accessible=false 节点不参与绑定、不在图里，
        # q 缺省 1.0 正好不罚（标志一致性由 graph_similarity 单独把关）。
        binding_quality = {b.node_id: b.quality for b in integ.node_bindings}
        if integ.delivered_graph is not None:
            ged: GedResult = mechanism_similarity(
                integ.delivered_graph,
                task.gold.mechanism_graph,
                ged_config,
                binding_quality=binding_quality,
            )
            res.graph_score = ged.score
        else:
            res.graph_score = 0.0
            res.notes.append("no delivered graph to compare")

        sc: SelfConsistencyReport = audit_self_consistency(
            integ.delivered_graph,
            integ.node_bindings,
            integ.evidence_files,
            sandbox,
            task.rubric.self_consistency,
            charge=task.system.charge,
            integrity_rubric=task.rubric.integrity,
            ged_config=ged_config,
        )
        res.selfconsistency_passed = sc.passed
        res.notes.extend(sc.notes)

        # 自洽回捞（2026-09-25 用户裁决）：gold 边被交付步覆盖、但覆盖它的
        # 交付步全部自洽不合格 → 该 gold 边赢下的图分覆盖贡献倒扣（违规交付
        # 边剔出交付图后重算 GED——同一 gold 边另有自洽合格的覆盖步时保留
        # 覆盖；有效不可达/accessible=false 的交付边本就被自洽豁免，不会进
        # 倒扣集）。不在 gold 子图里的额外交付边自洽不合格只落自洽层零分，
        # 不倒扣图分——gold 边出错与其他边出错严重程度不同。
        if integ.delivered_graph is not None and res.graph_score > 0.0:
            failed_edges = {
                c.element_id
                for c in sc.checks
                if c.kind == "edge" and not c.covered
            }
            if failed_edges:
                remove: set[str] = set()
                for g_edge in task.gold.mechanism_graph.edges:
                    covering = _covering_delivered_edge_ids(
                        g_edge,
                        task.gold.mechanism_graph,
                        integ.delivered_graph,
                        ged_config,
                        task.rubric.integrity.match_threshold,
                    )
                    failing = [e for e in covering if e in failed_edges]
                    if covering and len(failing) == len(covering):
                        remove.update(failing)
                        for eid in sorted(failing):
                            res.notes.append(
                                f"edge {eid}: selfconsistency failed, graph "
                                f"credit for gold edge {g_edge.id} clawed back"
                            )
                if remove:
                    pruned = GoldMechanismGraph(
                        nodes=list(integ.delivered_graph.nodes),
                        edges=[
                            e
                            for e in integ.delivered_graph.edges
                            if e.id not in remove
                        ],
                    )
                    res.graph_score = mechanism_similarity(
                        pruned,
                        task.gold.mechanism_graph,
                        ged_config,
                        binding_quality=binding_quality,
                    ).score

        barriers: BarrierEvidence = collect_barrier_evidence(sandbox)
        res.notes.extend(barriers.notes)
        # hard 档定性选择性：gold.selectivity 带 favored_channel 时替代 accuracy
        # 槽位（composite 的 accuracy 权重给选择性分；barrier spread 数值不评分）
        acc_fail_loud = False
        selectivity = task.gold.selectivity
        if selectivity is not None and selectivity.favored_channel:
            sel_score, sel_note = score_qualitative_selectivity(
                integ.delivered_graph, selectivity
            )
            res.accuracy_score = sel_score
            res.notes.append(sel_note)
        else:
            acc: AccuracyReport = score_accuracy(
                evidence=barriers,
                gold=task.gold,
                rubric=task.rubric.accuracy,
                delivered_graph=integ.delivered_graph,
                cfg=ged_config,
                match_threshold=task.rubric.integrity.match_threshold,
            )
            res.accuracy_score = acc.final_score
            res.notes.extend(acc.notes)
            acc_fail_loud = acc.fail_loud

        rub = task.rubric.integrity
        if not integ.graph_parseable:
            # 图缺失/不可解析 = 不可能有任何证据支撑 -> 零证据倒扣
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no parseable mechanism graph -> no evidence possible; penalty applied"
            )
            return res
        accessible_species = [
            n
            for n in integ.delivered_graph.nodes
            if n.accessible and n.role is not NodeRole.TRANSITION_STATE
        ]
        evidenced = {b.node_id for b in integ.node_bindings if b.quality > 0.0}
        if accessible_species and not any(
            n.id in evidenced for n in accessible_species
        ):
            # 有 accessible 物种声明但无一绑到证据 = 无证据支撑的机理声明，
            # 比没交付更糟 -> 倒扣；全部节点都声明 accessible=false 是合法
            # 交付（纯不可达声明），不触发本条
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no evidence bound to any accessible species node -> "
                "unsupported claims; penalty applied"
            )
            return res
        if acc_fail_loud:
            # fail-loud 短路：声明无据/不一致 -> 自洽与 accuracy 分量清零，
            # final 只保留图分
            res.final_score = round(W_GRAPH * res.graph_score, 4)
            res.notes.append(
                "accuracy fail-loud (unsupported or inconsistent declared "
                "barriers); final keeps the graph component only"
            )
            return res
        res.final_score = round(
            W_GRAPH * res.graph_score
            + W_SELFCONSISTENCY * (1.0 if res.selfconsistency_passed else 0.0)
            + W_ACCURACY * res.accuracy_score,
            4,
        )
        return res

    def run_task(self, task: TaskSpec) -> RunResult:
        # 沙箱按批次分目录：本批目录天然干净，不做任何删除——上一批的交付物
        # 与证据文件永久保留（benchmark 数据珍贵，清理永由用户显式执行）。
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        sandbox = self.sandbox_for(task.task_id, self.batch_id)
        sandbox.mkdir(parents=True, exist_ok=True)
        self.backend(task, sandbox)
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        result = self.score_sandbox(task, sandbox)
        if self.stop_event.is_set():
            raise BenchmarkStopped("benchmark batch stopped")
        result.batch_id = self.batch_id
        self.db.record(result)
        return result

    def _run_one_guarded(self, task: TaskSpec) -> RunResult:
        """单题异常不拖垮整批：失败题落一条 notes 带原因的零分结果行并继续。
        （后端崩溃记 0 而不是 no_evidence_penalty：基建失败不是 agent 的锅。）"""
        try:
            return self.run_task(task)
        except Exception as exc:
            stopped = isinstance(exc, BenchmarkStopped)
            if not stopped:
                print(f"[benchmark] task {task.task_id} crashed: {exc!r}")
            res = RunResult(
                task_id=task.task_id,
                sandbox=str(self.sandbox_for(task.task_id, self.batch_id)),
                batch_id=self.batch_id,
                orchestration_mode=task.prompt.orchestration_mode.value,
            )
            res.notes.append("cancelled by batch stop" if stopped else f"task crashed: {exc!r}")
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
            try:
                futures = {pool.submit(self._run_one_guarded, t): t for t in tasks}
                for fut in cf.as_completed(futures):
                    res = fut.result()
                    results[res.task_id] = res
            except BaseException:
                # Set this before the executor joins its workers: every private
                # runtime loop can then finish its own asynchronous cleanup.
                self.stop_event.set()
                raise
        return [results[t.task_id] for t in tasks]


def load_tasks(tasks_dir: Path) -> list[TaskSpec]:
    out = []
    for p in sorted(Path(tasks_dir).glob("*.json")):
        out.append(TaskSpec.model_validate(json.loads(p.read_text(encoding="utf-8"))))
    return out
