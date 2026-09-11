#!/usr/bin/env python3
"""合并有机知识碎片 → 主 kg-entities/kg-relations + cards.jsonl。

用法：
  uv run python scripts/kg_merge_organic.py            # 合并 + 抽卡
  uv run python scripts/kg_merge_organic.py --check    # 只校验不写
  uv run python scripts/kg_merge_organic.py --cards    # 只重抽卡片

子 agent 只写 kg_data/organic/entities_<family>.csv 与 relations_<family>.csv；
本脚本负责与主 CSV 的幂等合并（org: 前缀实体整组替换）与 markdown 卡片抽取。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KG = ROOT / "kg_data"
ORG = KG / "organic"
CARDS_DIR = ROOT / "知识卡片" / "ORG-有机反应机理"
CARDS_JSONL = ROOT / "vector_store" / "cards.jsonl"

ENT_HEADER = ["id", "type", "label", "smiles", "props", "n_sources"]
REL_HEADER = ["src_id", "dst_id", "rel_type", "evidence_level", "source", "falsified", "note"]

# 从 organic_schema.md 抽取的 tags controlled vocabulary（与 schema 同步）
TAG_NAMESPACES: dict[str, set[str]] = {
    "class": {
        "cross-coupling", "carbonyl", "substitution", "elimination", "oxidation",
        "reduction", "rearrangement", "pericyclic", "cycloaddition", "ch_activation",
        "photoredox", "electrochem", "organocatalysis", "biocatalysis",
        "multicomponent", "cascade", "total_synthesis", "radical", "organometallic",
        "acid_base",
    },
    "mechanism": {
        "SN1", "SN2", "E1", "E2", "E1cb", "nucleophilic_addition",
        "electrophilic_addition", "nucleophilic_acyl_sub", "oxidative_addition",
        "reductive_elimination", "migratory_insertion", "beta_hydride_elimination",
        "transmetalation", "ligand_exchange", "proton_transfer", "hydride_transfer",
        "electron_transfer", "radical_chain", "radical_addition",
        "radical_substitution", "sigmatropic", "electrocyclic", "cheletropic",
        "ene", "pericyclic", "chelation_control", "ion_pair", "adjacent_group",
        "somopy", "hydrogen_atom_transfer", "single_electron_transfer",
        "proton_coupled_et", "dyotropic", "metallacycle", "carbene_transfer",
        "nitrene_transfer",
    },
    "metal": {
        "Pd", "Ni", "Cu", "Rh", "Ir", "Ru", "Fe", "Co", "Mn", "Au", "Ag", "Zn",
        "Mg", "Li", "Na", "K", "B", "Si", "Al", "Sc", "Ti", "Zr", "Mo", "W", "Re",
        "Os", "Sn", "Pb", "Sb", "Bi", "Cr", "Ce", "In", "Ga", "none",
    },
    "reactant_type": {
        "aryl_halide", "vinyl_halide", "alkyl_halide", "pseudohalide", "alkene",
        "alkyne", "allene", "arene", "heteroarene", "aldehyde", "ketone", "ester",
        "amide", "acid", "acid_chloride", "anhydride", "nitrile", "imine", "enone",
        "epoxide", "aziridine", "alcohol", "amine", "thiol", "boronic_acid",
        "boronate", "organozinc", "organoboron", "organosilane", "organotin",
        "grignard", "organolithium", "enol", "enolate", "enamine", "diene",
        "dienophile", "carbene", "carbenoid", "nitrene", "radical_precursor",
        "diazo", "azide", "isocyanate", "phosphine", "NHC",
    },
    "bond_formed": {
        "C-C", "C-N", "C-O", "C-S", "C-B", "C-Si", "C-P", "C-F", "C-Cl", "C-Br",
        "C-I", "C-H", "C-metal", "N-H", "O-H", "S-H", "C-halogen", "C-CN", "C-CO",
        "C-acyl",
    },
    "selectivity": {"chemo", "regio", "stereo", "enantio", "diastereo", "site", "size"},
    "role": {
        "catalyst", "reagent", "solvent", "base", "acid", "ligand", "additive",
        "oxidant", "reductant", "template", "reactant", "product", "side_product",
        "intermediate",
    },
    "condition": {
        "temperature", "solvent", "base", "acid", "atmosphere", "catalyst_loading",
        "ligand", "time", "light", "pressure", "concentration", "additive",
        "order_of_addition", "technique",
    },
    "polarity": {"protic", "aprotic", "polar", "nonpolar", "lewis_acidic", "lewis_basic"},
    "frontier": {"true", "false"},
    "compchem": {
        "barrier_prediction", "ts_search", "mechanism_study", "selectivity_model",
        "solvent_effect", "redox_potential", "excited_state", "spectra_prediction",
        "conformational",
    },
    "strategy": {
        "linear", "convergent", "ring_closing", "cascade", "chiral_pool",
        "asymmetric_catalysis", "biomimetic", "diversity_oriented",
        "protecting_group_free", "late_stage_functionalization",
    },
    "target_class": {
        "alkaloid", "polyketide", "terpenoid", "peptide", "carbohydrate", "polyene",
        "polyether", "nucleoside", "antibiotic", "natural_product", "unnatural",
    },
    "oxidation_state": set(),  # 开放：如 Pd(0), Pd(II) — 不校验具体值
    "side": set(),  # 开放：副路径细分类
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines(keepends=True)))


def _validate_tags(props_str: str, row_id: str, problems: list[str]) -> None:
    if not props_str:
        return
    try:
        props = json.loads(props_str)
    except json.JSONDecodeError as e:
        problems.append(f"{row_id}: props 不是合法 JSON: {e}")
        return
    tags = props.get("tags", [])
    if not isinstance(tags, list):
        problems.append(f"{row_id}: tags 不是数组")
        return
    for t in tags:
        if ":" not in t:
            problems.append(f"{row_id}: tag 无命名空间: {t!r}")
            continue
        ns, val = t.split(":", 1)
        allowed = TAG_NAMESPACES.get(ns)
        if allowed is None:
            problems.append(f"{row_id}: 未知 tag 命名空间: {t!r}")
        elif allowed and val not in allowed:
            problems.append(f"{row_id}: tag 值不在词表: {t!r}")


def _validate_entities(rows: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    ids: set[str] = set()
    kept: list[dict] = []
    for i, r in enumerate(rows, start=2):
        rid = (r.get("id") or "").strip()
        if not rid:
            problems.append(f"entities line {i}: 空 id")
            continue
        if not rid.startswith(("reaction:", "molecule:", "mechanism_step:", "side_pathway:",
                               "condition:", "functional_group:", "total_synthesis_case:")):
            problems.append(f"entities line {i}: id 前缀不是有机命名空间: {rid}")
            continue
        # 跨族共享实体（functional_group:*, molecule:water 等）：首定义优先，静默去重
        if rid in ids:
            continue
        ids.add(rid)
        etype = (r.get("type") or "").strip()
        if etype not in {"reaction", "molecule", "mechanism_step", "side_pathway",
                         "condition", "functional_group", "total_synthesis_case"}:
            problems.append(f"entities line {i}: 非法 type {etype!r} for {rid}")
            continue
        label = (r.get("label") or "").strip()
        if not label:
            problems.append(f"entities line {i}: 空 label for {rid}")
            continue
        props = (r.get("props") or "").strip()
        _validate_tags(props, rid, problems)
        kept.append({
            "id": rid, "type": etype, "label": label,
            "smiles": (r.get("smiles") or "").strip(),
            "props": props, "n_sources": (r.get("n_sources") or "1").strip() or "1",
        })
    return kept, problems


def _validate_relations(rows: list[dict[str, str]], known_ids: set[str]) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    kept: list[dict] = []
    seen: set[tuple] = set()
    for i, r in enumerate(rows, start=2):
        src = (r.get("src_id") or "").strip()
        dst = (r.get("dst_id") or "").strip()
        if not src or not dst:
            problems.append(f"relations line {i}: 空 src/dst")
            continue
        if src not in known_ids:
            problems.append(f"relations line {i}: 悬挂 src {src}")
            continue
        rel = (r.get("rel_type") or "").strip()
        if not rel:
            problems.append(f"relations line {i}: 空 rel_type for {src}->{dst}")
            continue
        # relevant_to_compchem 允许 dst 指向主 KG 计算化学实体（不在有机碎片表）
        if rel != "relevant_to_compchem" and dst not in known_ids:
            problems.append(f"relations line {i}: 悬挂 dst {dst}")
            continue
        key = (src, dst, rel, (r.get("source") or "").strip())
        if key in seen:
            problems.append(f"relations line {i}: 重复关系 {key}")
            continue
        seen.add(key)
        kept.append({
            "src_id": src, "dst_id": dst, "rel_type": rel,
            "evidence_level": (r.get("evidence_level") or "L0").strip() or "L0",
            "source": (r.get("source") or "").strip(),
            "falsified": (r.get("falsified") or "false").strip().lower(),
            "note": (r.get("note") or "").strip(),
        })
    return kept, problems


def _extract_cards_from_md(md_path: Path, family: str) -> list[dict]:
    """从卡片 markdown 抽取 cards.jsonl 行（中英分段约定：en 段在 zh 段后成对出现或整体标注）。"""
    text = md_path.read_text(encoding="utf-8")
    # frontmatter
    fm: dict[str, str] = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        body = text[m.end():]

    card_id_base = fm.get("id") or f"org:{family}:{md_path.stem}"
    title = fm.get("title") or md_path.stem
    topic = fm.get("topic") or title
    domain = fm.get("domain") or "有机反应机理与副反应"
    fm_title = title

    # 按 ## N. 切分
    sections = re.split(r"^##\s+", body, flags=re.M)
    cards: list[dict] = []
    n = 0
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.splitlines()
        heading = lines[0].strip().rstrip("#").strip()
        content = "\n".join(lines[1:]).strip()
        # 去掉分隔用的 --- 行
        content = re.sub(r"^---\s*$", "", content, flags=re.M).strip()
        if not content or len(content) < 20:
            continue
        n += 1
        # 中英检测：ASCII 占比 > 0.7 视为英文
        ascii_letters = sum(1 for c in content if c.isascii() and (c.isalpha() or c.isspace()))
        cjk = sum(1 for c in content if "一" <= c <= "鿿")
        lang = "en" if (cjk == 0 and ascii_letters > 30) else "zh"
        cards.append({
            "card_id": f"{card_id_base}:{n}",
            "blog_id": "org",
            "file": f"ORG-有机反应机理/{family}/{md_path.name}",
            "heading": heading,
            "content": content,
            "domain": domain,
            "topic": topic,
            "fm_title": fm_title,
            "lang": lang,
        })
    return cards


def _collect_all_cards() -> list[dict]:
    all_cards: list[dict] = []
    if not CARDS_DIR.exists():
        return all_cards
    for family_dir in sorted(CARDS_DIR.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        for md in sorted(family_dir.glob("*_卡片.md")):
            all_cards.extend(_extract_cards_from_md(md, family))
    return all_cards


def _merge_entities(main_rows: list[dict], org_rows: list[dict]) -> tuple[list[dict], int, int]:
    """org: 前缀整组替换；返回 (merged, n_org, n_removed)."""
    org_ids = {r["id"] for r in org_rows}
    kept = [r for r in main_rows if (r.get("id") or "") not in org_ids]
    removed = len(main_rows) - len(kept)
    return kept + org_rows, len(org_rows), removed


def _merge_relations(main_rows: list[dict], org_rows: list[dict]) -> tuple[list[dict], int, int]:
    """source 以 org: 开头的关系整组替换。"""
    kept = [r for r in main_rows if not (r.get("source") or "").startswith("org:")]
    removed = len(main_rows) - len(kept)
    # 主关系表若无 source 列（已按 CSV 头），按列名处理
    return kept + org_rows, len(org_rows), removed


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    shutil.move(str(tmp), str(path))


def _atomic_write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    shutil.move(str(tmp), str(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="合并有机知识碎片到主 KG")
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    ap.add_argument("--cards", action="store_true", help="只重抽卡片并写 cards.jsonl")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    t0 = time.perf_counter()
    problems: list[str] = []

    # ── 收集有机碎片 ──
    ent_files = sorted(ORG.glob("entities_*.csv"))
    rel_files = sorted(ORG.glob("relations_*.csv"))
    org_ent_rows: list[dict] = []
    org_rel_rows: list[dict] = []
    for p in ent_files:
        org_ent_rows.extend(_read_csv(p))
    for p in rel_files:
        org_rel_rows.extend(_read_csv(p))

    org_entities, ent_problems = _validate_entities(org_ent_rows)
    problems.extend(ent_problems)
    known_ids = {r["id"] for r in org_entities}
    org_relations, rel_problems = _validate_relations(org_rel_rows, known_ids)
    problems.extend(rel_problems)

    if args.verbose:
        print(f"[organic] fragments: {len(ent_files)} ent files, {len(rel_files)} rel files")
        print(f"[organic] entities: {len(org_entities)}, relations: {len(org_relations)}")
        print(f"[organic] problems: {len(problems)}")
        for p in problems[:40]:
            print(f"  ⚠ {p}")
        if len(problems) > 40:
            print(f"  ... +{len(problems) - 40} more")

    if problems and not args.check:
        print(f"\n✗ 校验失败（{len(problems)} 个问题），拒绝写入。", file=sys.stderr)
        return 1

    if args.check:
        print(f"✓ 校验通过：{len(org_entities)} entities, {len(org_relations)} relations, "
              f"0 problems" if not problems else f"✗ {len(problems)} problems")
        return 1 if problems else 0

    # ── 合并实体 ──
    main_ent_path = KG / "kg-entities.csv"
    main_ent = _read_csv(main_ent_path)
    merged_ent, n_org, n_rm = _merge_entities(main_ent, org_entities)
    if not args.cards:
        _write_csv(main_ent_path, ENT_HEADER, merged_ent)
        print(f"[entities] main={len(main_ent)} → merged={len(merged_ent)} "
              f"(org替换 {n_org}, removed {n_rm})")

    # ── 合并关系 ──
    main_rel_path = KG / "kg-relations.csv"
    main_rel = _read_csv(main_rel_path)
    # 主表已有 org: source 的行需要去掉再加新的
    merged_rel, n_rorg, n_rrm = _merge_relations(main_rel, org_relations)
    if not args.cards:
        _write_csv(main_rel_path, REL_HEADER, merged_rel)
        print(f"[relations] main={len(main_rel)} → merged={len(merged_rel)} "
              f"(org替换 {n_rorg}, removed {n_rrm})")

    # ── 卡片抽取 ──
    org_cards = _collect_all_cards()
    print(f"[cards] extracted {len(org_cards)} card rows from {CARDS_DIR.name}/")

    cards_path = CARDS_JSONL
    existing: list[dict] = []
    if cards_path.exists():
        with cards_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 去掉旧的 org: 行（整组替换）
                if (obj.get("blog_id") == "org"
                        or str(obj.get("card_id", "")).startswith("org:")):
                    continue
                existing.append(obj)

    merged_cards = existing + org_cards
    _atomic_write_jsonl(cards_path, merged_cards)
    print(f"[cards] cards.jsonl: {len(existing)} existing + {len(org_cards)} org = {len(merged_cards)}")

    # ── 汇总统计 ──
    type_counts: dict[str, int] = defaultdict(int)
    for r in org_entities:
        type_counts[r["type"]] += 1
    rel_counts: dict[str, int] = defaultdict(int)
    for r in org_relations:
        rel_counts[r["rel_type"]] += 1
    lang_counts: dict[str, int] = defaultdict(int)
    for c in org_cards:
        lang_counts[c["lang"]] += 1

    stats = {
        "merged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "entities_org": len(org_entities),
        "relations_org": len(org_relations),
        "cards_org": len(org_cards),
        "type_distribution": dict(type_counts),
        "rel_distribution": dict(rel_counts),
        "card_langs": dict(lang_counts),
        "entity_files": [p.name for p in ent_files],
        "relation_files": [p.name for p in rel_files],
        "problems": len(problems),
    }
    stats_path = ORG / "organic-stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[stats] → {stats_path.relative_to(ROOT)}")
    print(f"✓ 完成（{time.perf_counter() - t0:.2f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
