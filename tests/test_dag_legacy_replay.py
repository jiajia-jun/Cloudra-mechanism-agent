"""Phase 4 回归：真实 journal 酸测试（4.3）+ 已删工具 grep-gate（4.1）。

fixture tests/fixtures/dag_legacy_journal.json 由 prj_d6212be8a2934e80
（ablation-da-dag_guided, 2026-08-16）的 dag_mutations 全量 accepted 日志导出：
1284 条 mutation、process revision 1266、delivery revision 30。process op 已
瘦身（重放为 no-op，无需载荷）；delivery op 与其引用的 8 条证据行全量保留。
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "dag_legacy_journal.json"
CODE_ROOT = Path(__file__).resolve().parents[1] / "cloudra"

DELETED_TOOLS = (
    "dag_schedule_work",
    "dag_update_process_node",
    "dag_init_from_template",
)


def test_deleted_process_tools_do_not_appear_in_code():
    """4.1 grep-gate：四个已删工具名不得出现在 cloudra/ 的 *.py 代码里。"""
    offenders = []
    for path in sorted(CODE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in DELETED_TOOLS:
            if name in text:
                offenders.append(f"{path.relative_to(CODE_ROOT)}: {name}")
    assert offenders == []


def test_real_legacy_journal_replays_delivery_only(tmp_path):
    """4.3 酸测试：真实旧 journal 重放成功；process 零物化；delivery 完整；
    revisions 与 journal 尾部一致；ignored_legacy_process_op 留痕。"""
    from cloudra.dag.completion import evaluate_delivery
    from cloudra.dag.models import CoverageContract
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db = ConversationDB("acid-replay", data_dir=tmp_path).init()
    store = DagStore(db)
    store.ensure_bundle("s1")
    with db.connect() as con:
        for ev in fixture["evidence"]:
            con.execute(
                """
                INSERT OR IGNORE INTO dag_evidence(
                    evidence_id, session_id, source_type, source_name,
                    content_hash, payload, created_at
                ) VALUES (?, ?, 'tool_result', ?, ?, ?, datetime('now'))
                """,
                (
                    ev["evidence_id"],
                    ev["session_id"],
                    ev["source_name"],
                    ev["content_hash"],
                    ev["payload"],
                ),
            )
        for index, mut in enumerate(fixture["mutations"]):
            base = mut["base_revisions"]
            resulting = mut["resulting_revisions"]
            con.execute(
                """
                INSERT INTO dag_mutations(
                    mutation_id, graph_id, base_revision, resulting_revision,
                    actor_type, actor_id, session_id, rationale, base_revisions,
                    resulting_revisions, operations, accepted, created_at
                ) VALUES (?, 'dag_delivery', ?, ?, ?, ?, 's1', '', ?, ?, ?, 1,
                          '2026-08-16T00:00:00')
                """,
                (
                    f"mut_acid_{index:05d}",
                    base.get("delivery", 0),
                    resulting.get("delivery", 0),
                    mut["actor_type"],
                    mut["actor_id"],
                    json.dumps(base),
                    json.dumps(resulting),
                    json.dumps(mut["operations"]),
                ),
            )

    rebuilt = store.rebuild_materialized()

    assert rebuilt.bundle.revisions == fixture["expected_revisions"]
    assert rebuilt.process.nodes == []
    assert rebuilt.process.edges == []
    assert len(rebuilt.delivery.nodes) == 3
    assert len(rebuilt.delivery.edges) == 1

    # 旧行映射：structure_supported ⇒ [geometry: supported]
    node = next(n for n in rebuilt.delivery.nodes if n.node_id == "occ_reactants")
    assert [(s.kind.value, s.status.value) for s in node.stages] == [
        ("geometry", "supported")
    ]

    legacy_ops = sum(
        1
        for mut in fixture["mutations"]
        for op in mut["operations"]
        if op.get("graph") == "process" or op.get("op") == "add_link"
    )
    assert legacy_ops > 0
    with db.connect() as con:
        row = con.execute(
            "SELECT rationale FROM dag_mutations "
            "WHERE rationale LIKE 'ignored_legacy_process_op%'"
        ).fetchone()
    assert row is not None
    assert f"{legacy_ops} legacy process operations" in row[0]

    # 覆盖评估在新语义下正常计算（不炸；complete 与否由阶段决定）
    report = evaluate_delivery(rebuilt.delivery, CoverageContract.mechanism_default())
    assert isinstance(report.complete, bool)

    # 幂等：二次重放结果一致
    assert store.rebuild_materialized() == rebuilt
