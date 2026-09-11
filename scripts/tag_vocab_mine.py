"""词表候选挖掘：从仓库语料提取 tag_vocab.yaml 的候选条目（一次性工具）。

产出去向：人工审核后手工整理进 vector_store/tag_vocab.yaml——本脚本只打印
候选清单，绝不改词表。

三类候选源：
1. 报错标题：知识卡片 markdown（含归档区——仅挖词表，卡片本身不入库，
   见 知识卡片/_ARCHIVE_NOTICE.md 护栏）里 "错误提示：/报错：" 式标题。
2. 报错签名：cards.jsonl 正文里的 verbatim 程序输出（L502/galloc/PGFIO…）。
3. 高频实体：kg_data/kg-entities.csv 里 n_sources≥N 的 pitfall/method/
   software label（方法/软件 tag 的种子）。

用法：uv run python scripts/tag_vocab_mine.py [--min-sources 3]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_SIGNATURE_PATTERNS = [
    r"Convergence failure[^\n\"]{0,40}", r"Erroneous wavefunction[^\n\"]{0,20}",
    r"SCF has not converged[^\n\"]{0,10}", r"galloc[^\n\"]{0,40}",
    r"PGFIO/stdio[^\n\"]{0,50}", r"Error termination[^\n\"]{0,40}",
    r"No executable[^\n\"]{0,40}", r"L\d{3}[^\n\"]{0,30}",
    r"illegal instruction[^\n\"]{0,30}", r"Segmentation fault[^\n\"]{0,20}",
    r"world accessible[^\n\"]{0,30}", r"out of memory[^\n\"]{0,30}",
]
_ERR_HEADING = re.compile(
    r"^##+\s*\d*[.、]?\s*(错误提示[:：][^\n]+|报错[:：][^\n]+)$", re.M)


def mine_error_headings() -> Counter[str]:
    hits: Counter[str] = Counter()
    for f in glob.glob(str(_REPO / "知识卡片" / "**" / "*.md"), recursive=True):
        try:
            text = Path(f).read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _ERR_HEADING.finditer(text):
            hits[m.group(1).strip()[:80]] += 1
    return hits


def mine_signatures() -> Counter[str]:
    hits: Counter[str] = Counter()
    cards = _REPO / "vector_store" / "cards.jsonl"
    if not cards.is_file():
        return hits
    with cards.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            text = str(row.get("heading") or "") + "\n" + str(row.get("content") or "")
            for p in _SIGNATURE_PATTERNS:
                for m in re.finditer(p, text, re.I):
                    hits[m.group(0)[:60]] += 1
    return hits


def mine_entities(min_sources: int) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    csv_path = _REPO / "kg_data" / "kg-entities.csv"
    if not csv_path.is_file():
        return out
    with csv_path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            n = int(row.get("n_sources") or 1)
            if n >= min_sources and row.get("type") in ("pitfall", "method", "software"):
                out.setdefault(row["type"], []).append((row["label"], n))
    for v in out.values():
        v.sort(key=lambda x: -x[1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="tag 词表候选挖掘")
    ap.add_argument("--min-sources", type=int, default=3,
                    help="实体入选的最小来源数（默认 3）")
    args = ap.parse_args()

    print("=== 1. 报错标题候选（知识卡片，含归档区；仅用于词表） ===")
    for h, c in mine_error_headings().most_common(60):
        print(f"{c:3d}  {h}")

    print("\n=== 2. 报错签名候选（cards.jsonl verbatim） ===")
    for s, c in mine_signatures().most_common(50):
        print(f"{c:4d}  {s}")

    print(f"\n=== 3. 高频实体种子（n_sources>={args.min_sources}） ===")
    for etype, items in mine_entities(args.min_sources).items():
        print(f"--- {etype} (top 40) ---")
        for label, n in items[:40]:
            print(f"{n:4d}  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
