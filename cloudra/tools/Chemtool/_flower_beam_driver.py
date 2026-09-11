"""FlowER beam-search driver.

本脚本由 flower conda 环境的 python 执行（Cloudra 主进程永不 import 它，
它的依赖 torch/torchdiffeq/rdkit/networkx 只存在于那个环境）。职责：

1. 在 import FlowER 代码之前装好它要求的环境变量（settings.py 的 Args
   在 import 时读 env，缺 EMB_DIM/SIGMA/RBF_* 会直接抛 TypeError）；
2. 以开放式（bare reactant）跑 beam search——刻意不传 ``>>products``，
   因为 FlowER 仅在所有目标 exact 命中时才落盘结果 pickle，目标匹配由
   Cloudra 侧在 network.json 上做；
3. 把结果 pickle 转成 network.json（Cloudra 侧唯一消费格式）：节点清洁为
   去氢去映射的 canonical 非立体 SMILES，平行边按 (reactant, product)
   合并（count 求和、rank 取最小），边概率 = count / sample_size。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import sys
import traceback

# FlowER 官方 run_FlowER_large_newData.sh 的模型/输入表示参数（大模型检查点）。
MODEL_ENV_DEFAULTS = {
    "EMB_DIM": "256",
    "SIGMA": "0.15",
    "RBF_HIGH": "12",
    "RBF_GAP": "0.1",
    "SCALE": "1",
    "NUM_GPUS_PER_NODE": "1",
    "NUM_NODES": "1",
    # DataLoader worker 必须为 0：FlowER 的 init_loader 用局部 lambda 作
    # collate_fn，macOS 的 spawn 启动方式无法 pickle 它（Linux fork 才没事），
    # CPU 推理在主进程内迭代即可。
    "NUM_WORKERS": "0",
    "CUDA_VISIBLE_DEVICES": "",
    "DATA_NAME": "cloudra",
    "EXP_NAME": "beam",
    "SEED": "42",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FlowER beam-search driver")
    parser.add_argument("--repo", required=True, help="FlowER repository root")
    parser.add_argument("--checkpoint", required=True, help="absolute path to model.*.pt")
    parser.add_argument("--input", required=True, help="beam.txt with one bare reactant line")
    parser.add_argument("--result-dir", required=True, help="FlowER RESULT_PATH (pickle output)")
    parser.add_argument("--out", required=True, help="network.json output path")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--nbest", type=int, default=3)
    parser.add_argument("--max-depth", type=int, default=10)
    parser.add_argument("--sample-size", type=int, default=16)
    parser.add_argument("--chunk-size", type=int, default=1)
    return parser.parse_args()


def _to_network_json(entry, sample_size: int, clean) -> dict:
    """(graph, root, (reactant, products), check) -> 合并后的 JSON 网络。"""
    graph, root, meta = entry[0], entry[1], entry[2]
    nodes: list[str] = []
    seen: set[str] = set()
    skipped_edges = 0

    def safe_clean(raw: str) -> str | None:
        """清洁 SMILES（去氢去映射、canonical、非立体）；失败返回 None。"""
        try:
            cleaned = clean(raw)
        except Exception:
            return None
        return cleaned or None

    def node_smiles(raw: str) -> str | None:
        cleaned = safe_clean(raw)
        if cleaned is not None and cleaned not in seen:
            seen.add(cleaned)
            nodes.append(cleaned)
        return cleaned

    merged: dict[tuple[str, str], dict] = {}
    for u, v, data in graph.edges(data=True):
        uc, vc = node_smiles(u), node_smiles(v)
        if uc is None or vc is None:  # clean 失败的节点不进合并网络
            skipped_edges += 1
            continue
        key = (uc, vc)
        rank = int(data.get("rank", 0))
        count = int(data.get("count", 0))
        if key in merged:
            merged[key]["count"] += count
            merged[key]["rank"] = min(merged[key]["rank"], rank)
        else:
            merged[key] = {"rank": rank, "count": count}

    edges = [
        {
            "reactant": u,
            "product": v,
            "rank": payload["rank"],
            "count": payload["count"],
            "probability": payload["count"] / sample_size,
        }
        for (u, v), payload in sorted(
            merged.items(), key=lambda item: (item[1]["rank"], item[0])
        )
    ]
    return {
        "reactant_input": meta[0],
        "root": safe_clean(root) or root,
        "sample_size": sample_size,
        "skipped_edges": skipped_edges,
        "nodes": nodes,
        "edges": edges,
    }


def main() -> int:
    ns = _parse_args()

    for key, value in MODEL_ENV_DEFAULTS.items():
        os.environ[key] = value
    checkpoint = os.path.abspath(ns.checkpoint)
    os.environ["TEST_FILE"] = os.path.abspath(ns.input)
    os.environ["RESULT_PATH"] = os.path.abspath(ns.result_dir)
    os.environ["MODEL_PATH"] = os.path.dirname(checkpoint) + os.sep
    os.environ["MODEL_NAME"] = os.path.basename(checkpoint)
    os.environ["BEAM_SIZE"] = str(ns.beam_size)
    os.environ["NBEST"] = str(ns.nbest)
    os.environ["MAX_DEPTH"] = str(ns.max_depth)
    os.environ["CHUNK_SIZE"] = str(ns.chunk_size)
    os.environ["SAMPLE_SIZE"] = str(ns.sample_size)

    sys.path.insert(0, ns.repo)
    logging.basicConfig(level=logging.INFO)

    # settings 必须在 env 就位后 import（Args 在类定义时读环境变量）。
    import beam_predict  # noqa: E402
    import settings  # noqa: E402

    args = settings.Args
    args.local_rank = -1  # 单进程：不初始化 torch.distributed
    os.makedirs(ns.result_dir, exist_ok=True)
    try:
        beam_predict.main(args)
    except Exception:
        traceback.print_exc()
        return 2

    pickles = sorted(
        name
        for name in os.listdir(ns.result_dir)
        if name.startswith("result_chunk_") and name.endswith(".pickle")
    )
    if not pickles:
        print("FlowER finished but produced no result_chunk_*_s0.pickle", file=sys.stderr)
        return 3
    with open(os.path.join(ns.result_dir, pickles[-1]), "rb") as handle:
        all_results = pickle.load(handle)
    if not all_results:
        print("FlowER result pickle is empty", file=sys.stderr)
        return 3

    network = _to_network_json(all_results[0], ns.sample_size, beam_predict.clean)
    with open(ns.out, "w", encoding="utf-8") as handle:
        json.dump(network, handle, indent=2)
    print(
        f"network.json written: {len(network['nodes'])} species, "
        f"{len(network['edges'])} step edges"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
