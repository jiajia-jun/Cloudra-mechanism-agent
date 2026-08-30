"""encode.py — 知识卡片向量库一键重编码

用法:
    <venv>/bin/python encode.py [-m MODEL] [--batch-size 64]

读 cards.jsonl，用指定 embedding 模型重编码全部卡片，原子覆写
vectors.f16.npy 并更新 meta.json（model/dim/count/时间）。换模型重编码后，
kg_vec_service / retrieve.py 的"模型不匹配"告警即消除。

编码文本 = heading + "\\n" + content（库侧不加查询前缀；查询前缀由
retrieve.py / kg_vec_service 按模型家族在查询侧添加）。向量 L2 归一化后
以 float16 存储；检索端会再归一化（f16 量化微偏差校正），口径不变。
注意：重编码会整体替换向量库，非 bge-m3 模型首次使用从 HF 下载。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "BAAI/bge-m3"
LIB = Path(__file__).resolve().parent


def encode_library(lib_dir: Path, model_name: str, batch_size: int = 64) -> dict:
    """重编码 lib_dir 下的 cards.jsonl，原子覆写向量与 meta。返回新 meta。"""
    cards_p = lib_dir / "cards.jsonl"
    if not cards_p.exists():
        print(f"缺少产物文件: {cards_p}", file=sys.stderr)
        sys.exit(2)
    cards = [json.loads(line) for line in cards_p.open(encoding="utf-8")]
    texts = [f"{c.get('heading', '')}\n{c.get('content', '')}" for c in cards]

    if model_name == DEFAULT_MODEL:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 默认模型已缓存，离线加载
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    model = SentenceTransformer(model_name, device="cpu")
    mat = model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                       show_progress_bar=True).astype(np.float16)
    elapsed = time.time() - t0

    meta = {
        "model": model_name,
        "dim": int(mat.shape[1]),
        "count": int(mat.shape[0]),
        "batch_size": batch_size,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "backend": "local",
        "device": "cpu",
        "elapsed_s": round(elapsed, 1),
        "text_recipe": "heading\\n+content, L2-normalized, float16",
    }
    vec_tmp = lib_dir / "vectors.f16.tmp.npy"  # np.save 只对非 .npy 结尾补后缀
    np.save(vec_tmp, mat)
    os.replace(vec_tmp, lib_dir / "vectors.f16.npy")
    meta_tmp = lib_dir / "meta.json.tmp"
    meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(meta_tmp, lib_dir / "meta.json")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description="知识卡片向量库一键重编码")
    ap.add_argument("-m", "--model", default=os.environ.get("KG_VEC_MODEL", DEFAULT_MODEL),
                    help=f"编码模型(默认 {DEFAULT_MODEL};与环境变量 KG_VEC_MODEL 同槽)")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    meta = encode_library(LIB, args.model, args.batch_size)
    print(f"重编码完成: {meta['count']} 张卡, dim={meta['dim']}, model={meta['model']}, "
          f"耗时 {meta['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
