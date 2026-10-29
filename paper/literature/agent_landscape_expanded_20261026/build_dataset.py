"""Merge the retained baseline and separately inspected expansion records."""

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "agent_landscape_20261026"
GROUPS = ("extended_materials_surfaces", "finite_molecules_complexes", "soft_biomolecular", "cross_domain")
TASKS = "TEOFRD"


def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    baseline = json.loads((BASE / "systems.json").read_text())
    rows = [dict(r, sample_origin="retained_baseline") for r in baseline]
    screening = []
    searches = []
    for stem in ("materials", "molecular", "md_soft", "root"):
        research = json.loads((HERE / "research" / f"{stem}.json").read_text())
        rows.extend(dict(r, sample_origin=f"expanded_{stem}") for r in research["records"])
        screening.extend(dict(r, screened_by=stem) for r in research["screening"])
        searches.extend(dict(r, search_stream=stem) for r in research["search_log"])
    rows.sort(key=lambda r: (r["first_public_date"], r["name"]))
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "Duplicate system id"
    for r in rows:
        assert r["include_main"] and r["physical_target"] in GROUPS
        assert date(2023, 1, 1) <= date.fromisoformat(r["first_public_date"]) <= date(2026, 10, 26)
        assert len(r["demonstrated_tasks"]) == len(set(r["demonstrated_tasks"]))
        assert set(r["demonstrated_tasks"]) <= set(TASKS)
        for t in r["demonstrated_tasks"]:
            source = r["sources"][r["task_evidence"][t]["source_index"]]
            assert source["url"].startswith("https://") and source["locator"] and source["evidence_paraphrase"]
    groups = Counter(r["physical_target"] for r in rows)
    families = defaultdict(list)
    for r in rows:
        families[r["family"]].append(r)
    collapsed = Counter()
    for members in families.values():
        kinds = {r["physical_target"] for r in members}
        collapsed[next(iter(kinds)) if len(kinds) == 1 else "cross_domain"] += 1
    counts = {
        "sample_n": len(rows), "baseline_n": len(baseline), "added_n": len(rows) - len(baseline),
        "physical_target_counts": {g: groups[g] for g in GROUPS},
        "physical_target_percentages": {g: round(100 * groups[g] / len(rows), 1) for g in GROUPS},
        "positive_task_counts": {t: sum(t in r["demonstrated_tasks"] for r in rows) for t in TASKS},
        "family_collapsed_n": len(families), "family_collapsed_target_counts": dict(collapsed),
        "family_merge_groups": {f: [r["id"] for r in rr] for f, rr in families.items() if len(rr) > 1},
        "screening_record_n": len(screening), "logged_search_entries": len(searches),
        "search_cutoff": "2026-10-26", "counts_are_non_exhaustive": True,
        "boundary_conditions_are_not_physical_target": True,
        "cross_domain_counted_once": True,
    }
    write_json("systems.json", rows)
    write_json("counts.json", counts)
    write_json("screening.json", {"records_outside_main": screening, "previous_screening": "../agent_landscape_20261026/screening.json"})
    write_json("search_log.json", searches)
    columns = ["id", "name", "first_public_date", "date_basis", "physical_target", "demonstrated_target", "boundary_conditions", "tasks", "family", "sample_origin", "primary_url", "locator", "evidence", "all_sources", "limitations"]
    with (HERE / "source_index.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            s = r["sources"][0]
            writer.writerow({**{key: r[key] for key in columns if key in r}, "tasks": " ".join(r["demonstrated_tasks"]), "primary_url": s["url"], "locator": s["locator"], "evidence": s["evidence_paraphrase"], "all_sources": " | ".join(f"{v['url']} [{v['locator']}]" for v in r["sources"])})
    lines = ["# 扩展样本文献清单", "", "逐项来源与限制见 source_index.csv；任务标记只代表检查到的正面证据。", "", "T 建模/编辑；E 静态能量/电子或材料性质；O 几何优化；F 振动/频率热化学；R 显式路径/过渡态；D 分子/量子动力学。", "", "| 系统 | 日期 | 对象类别 | 任务 | 来源与证据位置 |", "|---|---|---|---|---|"]
    labels = dict(zip(GROUPS, ["材料/表面", "有限分子/配合物", "软物质/生物分子", "跨类展示"]))
    for r in rows:
        s = r["sources"][0]
        name = r["name"] + (" **新增**" if r["sample_origin"] != "retained_baseline" else "")
        lines.append(f"| {name} | {r['first_public_date']} | {labels[r['physical_target']]} | {''.join(r['demonstrated_tasks'])} | [{s['locator']}]({s['url']}) |")
    (HERE / "catalogue_zh.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
