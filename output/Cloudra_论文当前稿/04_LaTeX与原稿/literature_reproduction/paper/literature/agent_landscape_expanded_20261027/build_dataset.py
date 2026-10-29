"""Reproduce the October 27 extension from the retained 70-system sample."""

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "agent_landscape_expanded_20261026"
GROUPS = (
    "extended_materials_surfaces", "finite_molecules_complexes",
    "soft_biomolecular", "cross_domain",
)
LABELS = dict(zip(GROUPS, ("材料/表面", "有限分子/配合物", "软物质/生物分子", "跨类展示")))
TASKS = "TEOFRD"


def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def category_counts(rows):
    counts = Counter(r["physical_target"] for r in rows)
    return {g: counts[g] for g in GROUPS}


def main():
    baseline = json.loads((BASE / "systems.json").read_text())
    rows = {r["id"]: dict(r) for r in baseline}
    screening, searches, amendments = [], [], []
    for stream in ("materials", "molecular", "root"):
        research = json.loads((HERE / "research" / f"{stream}_completion.json").read_text())
        for r in research["records"]:
            assert r["id"] not in rows, f"Duplicate id: {r['id']}"
            rows[r["id"]] = r
        for update in research.get("updates", []):
            rows[update["id"]].update(update["changes"])
            amendments.append(update)
        screening.extend(dict(r, search_stream=stream) for r in research["screening"])
        searches.extend(dict(r, search_stream=stream) for r in research["search_log"])

    # These successors explicitly share a family with retained predecessors.
    for system_id, family in {"chatmat": "MatAgent (Lv)", "mdagent2_runtime": "MDAgent"}.items():
        old = rows[system_id]["family"]
        rows[system_id]["family"] = family
        amendments.append({"id": system_id, "changes": {"family": family},
                           "reason": f"Canonical family label, previously {old}; prevents failed family merging."})

    rows = sorted(rows.values(), key=lambda r: (r["first_public_date"], r["name"]))
    for r in rows:
        assert r["include_main"] and r["physical_target"] in GROUPS
        assert date(2023, 1, 1) <= date.fromisoformat(r["first_public_date"]) <= date(2026, 10, 27)
        assert len(r["demonstrated_tasks"]) == len(set(r["demonstrated_tasks"]))
        assert set(r["demonstrated_tasks"]) == set(r["task_evidence"])
        assert set(r["demonstrated_tasks"]) <= set(TASKS)
        for task in r["demonstrated_tasks"]:
            source = r["sources"][r["task_evidence"][task]["source_index"]]
            assert source["url"].startswith("https://") and source["locator"] and source["evidence_paraphrase"]

    groups = category_counts(rows)
    families = defaultdict(list)
    for r in rows:
        families[r["family"]].append(r)
    collapsed = Counter()
    for members in families.values():
        kinds = {r["physical_target"] for r in members}
        collapsed[next(iter(kinds)) if len(kinds) == 1 else "cross_domain"] += 1
    official_only = {"protomia", "chelatron", "matmcp"}
    paper_rows = [r for r in rows if r["id"] not in official_only]
    stricter_rows = [r for r in paper_rows if r["id"] != "mlp_copilot"]
    counts = {
        "sample_n": len(rows), "baseline_n": len(baseline), "added_n": len(rows) - len(baseline),
        "physical_target_counts": groups,
        "physical_target_percentages": {g: round(100 * groups[g] / len(rows), 1) for g in GROUPS},
        "positive_task_counts": {t: sum(t in r["demonstrated_tasks"] for r in rows) for t in TASKS},
        "family_collapsed_n": len(families),
        "family_collapsed_target_counts": {g: collapsed[g] for g in GROUPS},
        "family_merge_groups": {f: [r["id"] for r in rr] for f, rr in families.items() if len(rr) > 1},
        "without_official_only": {"n": len(paper_rows), "excluded_ids": sorted(official_only), "target_counts": category_counts(paper_rows)},
        "without_official_only_and_planning_copilot": {"n": len(stricter_rows), "target_counts": category_counts(stricter_rows)},
        "latest_screening_record_n": len(screening), "latest_search_log_entries": len(searches),
        "previous_search_log_entries": len(json.loads((BASE / "search_log.json").read_text())),
        "search_cutoff": "2026-10-27", "counts_are_non_exhaustive": True,
        "boundary_conditions_are_not_physical_target": True, "cross_domain_counted_once": True,
    }
    write_json("systems.json", rows)
    write_json("counts.json", counts)
    write_json("amendments.json", amendments)
    write_json("screening.json", {"records_outside_main_or_resolved": screening,
                                 "previous_screening": "../agent_landscape_expanded_20261026/screening.json"})
    write_json("search_log.json", searches)
    columns = ["id", "name", "first_public_date", "date_basis", "physical_target", "demonstrated_target",
               "boundary_conditions", "tasks", "family", "sample_origin", "primary_url", "locator", "evidence", "all_sources", "limitations"]
    with (HERE / "source_index.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            s = r["sources"][0]
            writer.writerow({**{k: r[k] for k in columns if k in r}, "tasks": " ".join(r["demonstrated_tasks"]),
                             "primary_url": s["url"], "locator": s["locator"], "evidence": s["evidence_paraphrase"],
                             "all_sources": " | ".join(f"{v['url']} [{v['locator']}]" for v in r["sources"])})
    lines = ["# 化学 AI Agent 系统文献样本：85 个系统", "", "检索截止 2026-10-27。★ 为本轮新增；其余保留此前70项。完整限制见 source_index.csv。",
             "", "T 建模；E 静态能量/性质；O 优化；F 振动/热化学；R 路径/TS；D 动力学。标记只代表核读到的正面证据。", "",
             "| 化学 AI Agent 系统 | 定位到的公开日期 | 实际对象 | 任务 | 原始来源及位置 |", "|---|---|---|---|---|"]
    baseline_ids = {r["id"] for r in baseline}
    for r in rows:
        s = r["sources"][0]
        name = r["name"] + (" ★" if r["id"] not in baseline_ids else "")
        lines.append(f"| {name} | {r['first_public_date']} | {LABELS[r['physical_target']]} | {''.join(r['demonstrated_tasks'])} | [{s['locator']}]({s['url']}) |")
    (HERE / "catalogue_zh.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
