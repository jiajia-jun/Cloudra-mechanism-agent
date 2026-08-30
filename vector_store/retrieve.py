"""retrieve.py — 知识卡片语义检索 CLI(本地 embedding 模型)

用法:
    <venv>/Scripts/python.exe retrieve.py "查询词" [-k 10] [-m MODEL]
依赖: numpy + sentence_transformers(默认 BAAI/bge-m3 缓存于本机 HF 缓存,自动离线加载)
模型: -m/--model 或环境变量 KG_VEC_MODEL 自选;与 meta.json 记录的库编码模型
      不一致时打印告警——跨模型分数无效,请自行重新编码向量库。
打印: card_id | domain | 卡标题 | 正文片段(120 字)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

DEFAULT_MODEL = "BAAI/bge-m3"
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："  # bge 系专用查询前缀
LIB = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    ap = argparse.ArgumentParser(description="知识卡片语义检索")
    ap.add_argument("query", help="查询文本")
    ap.add_argument("-k", type=int, default=10, help="返回 top-k,默认 10")
    ap.add_argument("-m", "--model", default=os.environ.get("KG_VEC_MODEL", DEFAULT_MODEL),
                    help=f"查询侧 embedding 模型(默认 {DEFAULT_MODEL});换模型须自行重新编码向量库")
    args = ap.parse_args()

    if args.model == DEFAULT_MODEL:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 默认模型已缓存,离线加载,不触网

    import pathlib
    lib = pathlib.Path(LIB)
    cards_p, vec_p, meta_p = lib / "cards.jsonl", lib / "vectors.f16.npy", lib / "meta.json"
    for p in (cards_p, vec_p, meta_p):
        if not p.exists():
            print(f"缺少产物文件: {p.name}", file=sys.stderr)
            return 2

    lib_model = json.loads(meta_p.read_text(encoding="utf-8")).get("model")
    if lib_model and args.model != lib_model:
        print(f"⚠ 模型不匹配：向量库由 {lib_model!r} 编码，当前查询模型为 {args.model!r}。"
              "跨模型检索的相似度分数无效——请先用所选模型重新编码向量库"
              "（一键入口：encode.py --model 模型名）。",
              file=sys.stderr)

    cards = [line.rstrip("\n") for line in cards_p.open(encoding="utf-8")]
    mat = np.load(vec_p).astype(np.float32)
    if len(cards) != mat.shape[0]:
        print(f"行数不一致: cards={len(cards)} vecs={mat.shape[0]}", file=sys.stderr)
        return 2

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model, device="cpu")
    instruction = BGE_QUERY_INSTRUCTION if "bge" in args.model.lower() else ""
    q = model.encode([instruction + args.query], normalize_embeddings=True,
                     show_progress_bar=False)[0].astype(np.float32)

    m_norm = np.linalg.norm(mat, axis=1)
    m_norm[m_norm == 0] = 1.0
    scores = (mat @ q) / m_norm  # 库侧再归一化 → 严格余弦(f16 量化微偏差校正)
    top = np.argsort(-scores)[: args.k]

    for i in top:
        row = json.loads(cards[int(i)])
        snippet = row["content"].replace("\n", " ")[:120]
        print(f"{row['card_id']} | {row['domain']} | {row['heading']} | {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
