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
from cloudra.benchmark.runner import BackendResult, BenchmarkDB, BenchmarkRunner
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

# --- classify_outcome：v1 确定性启发式的行为语义 ---


def test_classify_delivered_graph_is_answered_even_with_disclaimer():
    """交付了图就是作答——附带"结果不可靠"免责声明不改分类。"""
    out = classify_outcome(
        graph_found=True,
        final_message="Delivered the graph, but I must refuse to trust these numbers.",
    )
    assert out is RunOutcome.ANSWERED


@pytest.mark.parametrize(
    "msg",
    [
        "After checking the T1 diagnostic, I must refuse to report a single-reference number.",
        "I decline to provide a barrier for this system.",
        "It would not be meaningful to report a CCSD(T) barrier here.",
        "I will not report a number for this barrier.",
        "I cannot responsibly report a value from a single-reference method.",
        "诊断显示该体系强多参考，我拒绝给出单参考能垒数值。",
        "该区域的单参考结果不可信，无法给出可信的数值。",
        "这是科学拒答：需要 CASSCF 级别处理。",
    ],
)
def test_classify_explicit_refusal(msg):
    out = classify_outcome(graph_found=False, final_message=msg)
    assert out is RunOutcome.REFUSED


@pytest.mark.parametrize(
    "msg",
    [
        "",  # 无消息
        "The system is strongly multireference; CASSCF would be needed. Here is my graph.",  # 只谈理由不拒答
        "The calculation failed to converge after  retries.",  # 借口/失败不是拒答
        " barrier is about 40 kcal/mol, roughly.",  # 硬报数
    ],
)
def test_classify_no_refusal_statement_is_failed(msg):
    out = classify_outcome(graph_found=False, final_message=msg)
    assert out is RunOutcome.FAILED


def test_classify_crashed_is_failed_even_with_refusal_text():
    out = classify_outcome(graph_found=False, final_message="I refuse to answer.", crashed=True)
    assert out is RunOutcome.FAILED


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


# --- runner 接线：BackendResult → outcome → DB ---


def test_runner_records_refused_outcome(tmp_path):
    tasks = gen_easy_tasks.parse_easy_md(gen_easy_tasks.DEFAULT_SRC)[:1]

    def backend(task, sandbox):
        sandbox.mkdir(parents=True, exist_ok=True)
        return BackendResult(
            barrier=None,
            final_message="After checking the T1 diagnostic, I must refuse to report a number.",
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
        # 即便文本里带拒答措辞，交付了图就是作答
        return BackendResult(final_message="I must refuse to trust these numbers, but here is the graph.")

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
