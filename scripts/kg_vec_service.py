"""kg_vec_service.py — 知识卡片语义检索微服务（HTTP，供 chem-kb 混合 provider 调用）。

纯标准库 HTTP 服务器（ThreadingHTTPServer）；模型与向量计算依赖留在
外部 .venv-trans（sentence-transformers + numpy + 本机 HF 缓存的 bge-m3），
cloudra 自身 venv 不装 torch。本服务不随 cloudra 自启，用
scripts/kg_vec_service.ps1 或直接：

    <venv-trans>/Scripts/python.exe scripts/kg_vec_service.py [--port 8765]

端点：
    GET /health          → {"ok": true, "model": "BAAI/bge-m3", "count": 7497}
    GET /search?q=&k=    → {"hits": [{card_id, blog_id, domain, heading, content, score}]}
    POST /search {"query": "...", "k": 5}
                        → 同上（chem-kb 混合 provider 走这条；GET 供人工/脚本调试）

查询侧加 bge 指令前缀、库侧再归一化（f16 量化微偏差校正），与
向量库/retrieve.py 口径一致。只绑定 127.0.0.1。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "向量库"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
CONTENT_CAP = 600  # 单条 content 码点上限（调用方还会再折叠）

_cards: list[dict] = []
_mat = None  # np.ndarray (n, dim) float32
_model = None
_model_lock = threading.Lock()
_encode_lock = threading.Lock()


def _load_library() -> None:
    global _cards, _mat
    import numpy as np

    cards_p, vec_p = LIB_DIR / "cards.jsonl", LIB_DIR / "vectors.f16.npy"
    for p in (cards_p, vec_p):
        if not p.exists():
            print(f"缺少产物文件: {p}", file=sys.stderr)
            sys.exit(2)
    _cards = [json.loads(line) for line in cards_p.open(encoding="utf-8")]
    _mat = np.load(vec_p).astype(np.float32)
    if len(_cards) != _mat.shape[0]:
        print(f"行数不一致: cards={len(_cards)} vecs={_mat.shape[0]}", file=sys.stderr)
        sys.exit(2)


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 模型已缓存，离线加载
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer("BAAI/bge-m3", device="cpu")
    return _model


def _clamp_k(raw: Any) -> int:
    try:
        return max(1, min(50, int(raw)))
    except (TypeError, ValueError):
        return 5


def _search(query: str, k: int) -> list[dict]:
    import numpy as np

    model = _get_model()
    with _encode_lock:  # torch encode 释放 GIL，串行化避免并发竞态
        q = model.encode([QUERY_INSTRUCTION + query], normalize_embeddings=True,
                         show_progress_bar=False)[0].astype(np.float32)
    m_norm = np.linalg.norm(_mat, axis=1)
    m_norm[m_norm == 0] = 1.0
    scores = (_mat @ q) / m_norm  # 库侧再归一化 → 严格余弦
    top = np.argsort(-scores)[:k]
    hits = []
    for i in top:
        row = _cards[int(i)]
        hits.append({
            "card_id": row.get("card_id", ""),
            "blog_id": row.get("blog_id", ""),
            "domain": row.get("domain", ""),
            "heading": row.get("heading", ""),
            "content": row.get("content", "")[:CONTENT_CAP],
            "score": float(scores[int(i)]),
        })
    return hits


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({
                "ok": True,
                "model": "BAAI/bge-m3" if _model is not None else None,
                "count": len(_cards),
            })
            return
        if parsed.path == "/search":
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0].strip()
            k = _clamp_k((qs.get("k") or ["5"])[0])
            self._handle_search(q, k)
            return
        self._send_json({"error": "not found"}, code=404)

    def do_POST(self) -> None:  # noqa: N802  # 混合 provider 的通道
        parsed = urlparse(self.path)
        if parsed.path == "/search":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                q = str(body.get("query") or "").strip()
                k = _clamp_k(body.get("k", 5))
            except Exception:
                self._send_json({"error": "bad request"}, code=400)
                return
            self._handle_search(q, k)
            return
        self._send_json({"error": "not found"}, code=404)

    def _handle_search(self, q: str, k: int) -> None:
        if not q:
            self._send_json({"error": "missing q"}, code=400)
            return
        try:
            self._send_json({"hits": _search(q, k)})
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, code=500)

    def log_message(self, fmt: str, *args) -> None:  # 精简默认噪音
        sys.stderr.write(f"[kg_vec] {self.address_string()} {fmt % args}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="知识卡片语义检索微服务（bge-m3，外部 venv 运行）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    _load_library()
    # 后台预热 bge-m3：懒加载逻辑保留兜底，但冷启动（CPU 首载约 5-10s）必须
    # 不与调用方的 3s 超时赛跑——监听立即可用，模型在后台线程就绪。
    warm = threading.Thread(target=_get_model, daemon=True)
    warm.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[kg_vec] listening on http://{args.host}:{args.port}  cards={len(_cards)}  "
          f"(bge-m3 首次 /search 时懒加载)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
