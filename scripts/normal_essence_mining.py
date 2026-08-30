"""Normal 档候选池"化学本质"数据挖掘：成键变化指纹聚类。

对 normal.md 的每条反应，用 RDKit 分别统计反应物侧与产物侧的重原子键型
直方图（键型 = 无序元素对 + 键级，芳香键记 1.5；X–H 键不计，催化剂/副产物
写入两侧自动对消），取差集得"净成键指纹"（formed/broken 多重集）。指纹相同
= 净化学转化（化学计学层面）相同；指纹聚类结果再人工合并机理本质（同一净
转化可能对应不同机理，如 X3 E2 vs X4 syn Ei），最终报告两层数字。

用法：.venv/bin/python scripts/normal_essence_mining.py
输出：终端打印聚类 + ideapool/reaction_candidates/normal_essence_mining.json
"""

import json
import re
from collections import Counter
from pathlib import Path

from rdkit import Chem

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ideapool" / "reaction_candidates" / "normal.md"
OUT = ROOT / "ideapool" / "reaction_candidates" / "normal_essence_mining.json"

ROW_RE = re.compile(r"^\|\s*([A-Z]\d+)\s*\|")
SMILES_RE = re.compile(r"`([^`]+)`(?:（[^）]*）)?\s*[，,]\s*([+−\-]?\d+)\s*/\s*(\d+)")


def atom_sig(atom) -> str:
    """原子环境签名：元素 + 重原子度 + 携带 H 数 + 芳香性。

    区分同元素不同化学环境（醇 O–H vs 酯 O），否则酯化/环氧开环这类
    净转化只换取代基位置的反应会得到空指纹。
    """
    return f"{atom.GetSymbol()}{atom.GetDegree()}h{atom.GetTotalNumHs()}{'a' if atom.GetIsAromatic() else ''}"


def bond_histogram(smiles_side: str) -> Counter:
    """一侧（点分隔多分子）的环境感知重原子键型直方图。"""
    hist: Counter = Counter()
    for frag in smiles_side.split("."):
        mol = Chem.MolFromSmiles(frag)
        if mol is None:
            raise SystemExit(f"RDKit 解析失败: {frag!r}（{smiles_side!r}）")
        for bond in mol.GetBonds():
            a, b = bond.GetBeginAtom(), bond.GetEndAtom()
            if a.GetAtomicNum() == 1 or b.GetAtomicNum() == 1:
                continue
            pair = tuple(sorted((atom_sig(a), atom_sig(b))))
            ring = "r" if bond.IsInRing() else ""
            hist[(pair, bond.GetBondTypeAsDouble(), ring)] += 1
    return hist


def fmt_bond(key: tuple) -> str:
    (e1, e2), order, ring = key
    sym = {1.0: "-", 2.0: "=", 3.0: "#", 1.5: "~", 4.0: "$"}.get(order, f"?{order}")
    return f"{e1}{sym}{e2}{ring}"


def main() -> None:
    rows: list[dict] = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        sm = SMILES_RE.search(cells[2])
        if not sm:
            raise SystemExit(f"{m.group(1)}: SMILES 格解析失败")
        reactants, _, products = sm.group(1).partition(">>")
        if not reactants or not products:
            raise SystemExit(f"{m.group(1)}: SMILES 缺 >> 分隔")
        hr, hp = bond_histogram(reactants), bond_histogram(products)
        formed = hp - hr  # 产物侧多出的键
        broken = hr - hp  # 反应物侧多出的键
        rows.append({
            "id": m.group(1),
            "name": cells[1],
            "smiles": sm.group(1),
            "formed": sorted(f"{fmt_bond(k)}×{v}" for k, v in formed.items()),
            "broken": sorted(f"{fmt_bond(k)}×{v}" for k, v in broken.items()),
        })
    if len(rows) != 48:
        raise SystemExit(f"行数 {len(rows)} != 48，池子有变动，先核对")

    clusters: dict[str, list[str]] = {}
    for r in rows:
        key = f"+[{', '.join(r['formed'])}] -[{', '.join(r['broken'])}]"
        clusters.setdefault(key, []).append(r["id"])
    for r in rows:
        key = f"+[{', '.join(r['formed'])}] -[{', '.join(r['broken'])}]"
        r["cluster_size"] = len(clusters[key])

    OUT.write_text(json.dumps({"rows": rows, "clusters": clusters}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"条目 {len(rows)}；净成键指纹类（化学计学本质）{len(clusters)} 个\n")
    for i, (key, ids) in enumerate(sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
        print(f"[{i:2d}] {', '.join(ids):<28} {key}")


if __name__ == "__main__":
    main()
