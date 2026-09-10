"""拒答分类（refusal.py）与 runner 拒答 outcome 接线的测试。

判分哲学（impossible.md 定稿段）：拒答是跨档一等 outcome，统计只做
precision/recall，不评价拒答理由——这里的测试也只锁定"行为分类"语义。
"""

import sqlite3

import pytest

from cloudra.benchmark import gen_easy_tasks
from cloudra.benchmark.refusal import (
    RunOutcome,
    classify_outcome,
    refusal_stats,
    should_refuse,
)
from cloudra.benchmark.runner import BenchmarkDB, BenchmarkRunner
from cloudra.benchmark.schema import (
    ExpectedOutcome,
    GoldMechanismGraph,
    GoldSpec,
    ImpossibleCaseRubric,
    MechanismNode,
    NodeRole,
    PromptSpec,
    RubricSpec,
    SystemSpec,
    TaskSpec,
    Tier,
)
from cloudra.runtime_v2.schemas import OrchestrationMode

# --- classify_outcome：结构化行为分类（只读交付物，不解析散文） ---


def test_classify_delivered_graph_is_answered_even_with_refusal_words():
    """交付了可解析的图就是作答——即便文本里带"我不信这些数"之类的措辞。"""
    assert classify_outcome(graph_found=True, refusal_declared=False) is RunOutcome.ANSWERED
    # 拒绝声明与图同时存在时图优先（交付了图即作答）
    assert classify_outcome(graph_found=True, refusal_declared=True) is RunOutcome.ANSWERED


def test_classify_structured_refusal_declaration_is_refused():
    """无图 + 合法结构化拒答声明 → refused。"""
    assert classify_outcome(graph_found=False, refusal_declared=True) is RunOutcome.REFUSED


@pytest.mark.parametrize(
    "graph_found,refusal_declared",
    [
        (False, False),   # 无图无声明（含只写散文拒答、崩溃、超时）
        (False, False),
    ],
)
def test_classify_no_delivery_is_failed(graph_found, refusal_declared):
    assert classify_outcome(
        graph_found=graph_found, refusal_declared=refusal_declared
    ) is RunOutcome.FAILED


def test_classify_ignores_prose_refusal(tmp_path):
    """散文里的拒答措辞不参与判定：不落结构化声明即 failed（fail-loud）。"""
    sandbox = tmp_path / "s"
    sandbox.mkdir()
    (sandbox / "notes.txt").write_text(
        "I must refuse to report a single-reference number for this system."
    )
    from cloudra.benchmark.barrier_evidence import load_refusal_declaration

    assert load_refusal_declaration(sandbox) is None
    assert classify_outcome(graph_found=False, refusal_declared=False) is RunOutcome.FAILED


def test_refusal_declaration_loader_requires_named_file_and_true_flag(tmp_path):
    """声明只在交付的 mechanism_graph.json 里、且 refused=true 才算数。"""
    from cloudra.benchmark.barrier_evidence import load_refusal_declaration

    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "mechanism_graph.json").write_text(
        '{"refusal": {"refused": true, "reason": "strong multireference"}}'
    )
    declaration = load_refusal_declaration(ok)
    assert declaration is not None and declaration.refused is True
    assert "multireference" in declaration.reason

    false_flag = tmp_path / "false_flag"
    false_flag.mkdir()
    (false_flag / "mechanism_graph.json").write_text(
        '{"refusal": {"refused": false, "reason": "nope"}}'
    )
    assert load_refusal_declaration(false_flag) is None

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "refusal.json").write_text('{"refused": true, "reason": "x"}')
    assert load_refusal_declaration(elsewhere) is None


# --- should_refuse ground truth ---


def _refusal_task() -> TaskSpec:
    return TaskSpec(
        task_id="IM1",
        tier=Tier.IMPOSSIBLE,
        prompt=PromptSpec(query="do it", orchestration_mode=OrchestrationMode.STANDARD),
        system=SystemSpec(reactants=["C"]),
        gold=GoldSpec(
            mechanism_graph=GoldMechanismGraph(
                nodes=[MechanismNode(id="r1", role=NodeRole.REACTANT, smiles=["C"])]
            )
        ),
        rubric=RubricSpec(
            expected_outcome=ExpectedOutcome.CORRECT_REFUSAL,
            impossible_case=ImpossibleCaseRubric(),
        ),
    )


def test_should_refuse_truth_values():
    assert should_refuse(_refusal_task()) is True
    easy = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[0]
    assert should_refuse(easy) is False


# --- refusal_stats 混淆矩阵数学 ---


def test_stats_perfect_classifier():
    st = refusal_stats([(True, True), (True, True), (False, False), (False, False)])
    assert (st.tp, st.fp, st.fn, st.tn) == (2, 0, 0, 2)
    assert st.precision == 1.0 and st.recall == 1.0 and st.f1 == 1.0


def test_stats_refuse_everything_gets_precision_diluted():
    """"什么都拒"的 agent：recall 满分，但 easy/normal/hard 上的 FP 拉低 precision。"""
    st = refusal_stats([(True, True)] + [(False, True)] * 9)
    assert st.recall == 1.0
    assert st.precision == pytest.approx(0.1)


def test_stats_refuse_nothing_has_zero_recall():
    st = refusal_stats([(True, False), (False, False)])
    assert (st.tp, st.fp, st.fn, st.tn) == (0, 0, 1, 1)
    assert st.precision is None  # 无拒答 → precision 无定义
    assert st.recall == 0.0
    assert st.f1 is None


def test_stats_no_positive_tasks_recall_undefined():
    """单档批次（如只跑 easy）：没有"应当拒答"题，recall 无定义。"""
    st = refusal_stats([(False, False), (False, True)])
    assert st.recall is None
    assert st.precision == 0.0


# --- runner 接线：交付物 → outcome → DB ---


def test_runner_records_refused_outcome(tmp_path):
    """结构化拒答声明（无图）→ refused 落库。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]

    def backend(task, sandbox):
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "mechanism_graph.json").write_text(
            '{"refusal": {"refused": true, "reason": "strong multireference, '
            'single-reference numbers would be meaningless"}}'
        )

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    res = runner.run_task(tasks[0])
    assert res.outcome == RunOutcome.REFUSED.value
    with sqlite3.connect(runner.db.db_path) as c:
        row = c.execute("SELECT outcome FROM runs WHERE task_id = ?", (tasks[0].task_id,)).fetchone()
    assert row[0] == "refused"


def test_runner_noop_backend_is_failed_not_refused(tmp_path):
    """dry-run（no-op backend）无交付也无拒答声明：记 failed，不污染拒答统计。"""
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]
    runner = BenchmarkRunner(tmp_path / "bench")
    res = runner.run_task(tasks[0])
    assert res.outcome == RunOutcome.FAILED.value


def test_runner_delivered_graph_is_answered(tmp_path):
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]

    def backend(task, sandbox):
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "mechanism_graph.json").write_text(
            '{"nodes": [{"id": "r1", "role": "reactant", "smiles": ["C=CC=C"]}], "edges": []}'
        )
        # 交付了图即作答（分类不看任何文本）

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    res = runner.run_task(tasks[0])
    assert res.outcome == RunOutcome.ANSWERED.value


def test_runner_crash_is_failed(tmp_path):
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]

    def backend(task, sandbox):
        raise RuntimeError("boom")

    runner = BenchmarkRunner(tmp_path / "bench", backend=backend)
    res = runner.run_all(tasks)[0]
    assert res.outcome == RunOutcome.FAILED.value


def test_benchmark_db_migrates_old_runs_table(tmp_path):
    """旧库（无 outcome 列）打开时迁一把：旧行 outcome 按 'failed'（未知）记。"""
    db_path = tmp_path / "bench" / "benchmark.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as c:
        c.execute(
            """CREATE TABLE runs (
                task_id TEXT, sandbox TEXT,
                integrity_passed INTEGER, graph_score REAL,
                selfconsistency_passed INTEGER, accuracy_score REAL,
                final_score REAL, notes TEXT, ts INTEGER
            )"""
        )
        c.execute("INSERT INTO runs VALUES ('X1','s',0,0.0,0,0.0,0.0,'[]',1)")

    db = BenchmarkDB(db_path)
    with sqlite3.connect(db_path) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(runs)")}
        assert "outcome" in cols
        assert c.execute("SELECT outcome FROM runs WHERE task_id = 'X1'").fetchone()[0] == "failed"
    # 迁移后正常写入新行
    from cloudra.benchmark.runner import RunResult

    db.record(RunResult(task_id="X2", sandbox="s", outcome="refused"))
    with sqlite3.connect(db_path) as c:
        assert c.execute("SELECT outcome FROM runs WHERE task_id = 'X2'").fetchone()[0] == "refused"
