"""kg_vec_service.py — 知识卡片语义检索微服务（HTTP，供 chem-kb 混合 provider 调用）。

纯标准库 HTTP 服务器（ThreadingHTTPServer）；模型与向量计算依赖留在
外部 .venv-trans（sentence-transformers + numpy + 本机 HF 缓存的 bge-m3），
cloudra 自身 venv 不装 torch。chem-kb 插件激活时本服务由 cloudra web
启动器自动 detach 拉起（``CLOUDRA_KG_VEC=off`` 关闭自启）；也可手动：
scripts/kg_vec_service.ps1 或直接：

    <venv-trans>/bin/python scripts/kg_vec_service.py [--port 8765] [--model NAME] [--lock-file PATH]

**约束**：本脚本跑在外部 .venv-trans 解释器下，cloudra 包不可导入——logging
只能 stdlib ``basicConfig`` 自理（main() 入口，级别取环境变量
``KG_VEC_LOG_LEVEL``，缺省 INFO），不能复用 cloudra.infra.logging_setup。
detach 拉起时 stdout/stderr 已被重定向进 logs/kg_vec.log，日志写 stdout 即落盘。

单实例：--lock-file（或环境变量 KG_VEC_LOCK_FILE）给定路径时启动即抢排他
flock 并持有到进程退出——锁已被别的实例持有则直接退出（返回码 0，防重不
算错误）；启动方的判定链（/health 探测 + 同一把锁的探测）见
cloudra/services/daemon_supervisor.py 的 ensure_kg_vec。平台无 fcntl（Windows）时锁
退化不启用，仅靠启动方的 /health 探测防重。

模型可用 --model 或环境变量 KG_VEC_MODEL 自选（默认 BAAI/bge-m3，离线加载）；
换成与 vector_store/meta.json 记录不同的模型时启动即告警——跨模型余弦分数无效，
需自行用所选模型重新编码向量库。非默认模型首次使用从 HF 下载。

端点：
    GET /health          → {"ok": true, "model": ..., "library_model": ..., "count": 14986}
    GET /search?q=&k=[&lang=zh|en][&domain=...][&tags=a,b] → {"hits": [{card_id, lang, blog_id, domain, tags, heading, content, score}]}
    POST /search {"query": "...", "k": 5, "lang": "en",
                  "domain": "波函数与电子结构分析" | [...],
                  "tags": ["scf_not_converged"] | {"problem": ["scf_not_converged"]}}
                         → 同上（chem-kb 混合 provider 走这条；GET 供人工/脚本调试）

过滤（v13）：domain 精确匹配行值（zh/en 任一形式）；tags 过滤——扁平列表
= 任一 tag 命中即可，dict = facet 间 AND、facet 内任一命中。过滤是
top-k 后过滤（扫完整 order 直到凑满 k 或耗尽），因此"过滤后不足 k 条"
不会用不相关行凑数。

双语库（cards.jsonl 每卡 zh+en 两行，"lang" 字段区分）：lang 缺省混合检索；
指定 zh/en 只在该语言行上排名。同 card_id 的双行**去重**——按分数序保留
高分行，防止同一张卡中英双占 top-k（旧单语库无 lang 字段视为 zh，行为不变）。

查询侧对 bge 系模型加专用指令前缀、库侧再归一化（f16 量化微偏差校正），与
vector_store/retrieve.py 口径一致。只绑定 127.0.0.1。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "vector_store"
DEFAULT_MODEL = "BAAI/bge-m3"
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："  # bge 系专用查询前缀
CONTENT_CAP = 600  # 单条 content 码点上限（调用方还会再折叠）

logger = logging.getLogger("kg_vec")

_cards: list[dict] = []
_mat = None  # np.ndarray (n, dim) float32
_model = None
_model_name = DEFAULT_MODEL  # main() 里被 --model / KG_VEC_MODEL 覆盖
_lib_model: str | None = None  # meta.json 记录的库编码模型
_model_lock = threading.Lock()
_encode_lock = threading.Lock()


def _load_library() -> None:
    global _cards, _mat, _lib_model
    import numpy as np

    cards_p, vec_p = LIB_DIR / "cards.jsonl", LIB_DIR / "vectors.f16.npy"
    for p in (cards_p, vec_p):
        if not p.exists():
            logger.error("缺少产物文件: %s", p)
            sys.exit(2)
    _cards = [json.loads(line) for line in cards_p.open(encoding="utf-8")]
    _mat = np.load(vec_p).astype(np.float32)
    if len(_cards) != _mat.shape[0]:
        logger.error("行数不一致: cards=%d vecs=%d", len(_cards), _mat.shape[0])
        sys.exit(2)
    meta_p = LIB_DIR / "meta.json"
    if meta_p.exists():
        try:
            _lib_model = json.loads(meta_p.read_text(encoding="utf-8")).get("model")
        except Exception:  # noqa: BLE001 — meta 损坏不阻断服务，只是无法校验模型
            _lib_model = None


def _query_instruction() -> str:
    """查询指令前缀：bge 系模型需要专用前缀，其余模型裸查询。"""
    return BGE_QUERY_INSTRUCTION if "bge" in _model_name.lower() else ""


def _check_model_match() -> str | None:
    """查询模型与库编码模型不一致时返回告警文本（跨模型余弦分数无意义）。"""
    if _lib_model and _model_name != _lib_model:
        return (f"模型不匹配：向量库由 {_lib_model!r} 编码，当前查询模型为 {_model_name!r}。"
                "跨模型检索的相似度分数无效——请先用所选模型重新编码向量库"
                "（一键入口：vector_store/encode.py --model 模型名），或把 --model 换回库编码模型。")
    return None


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                if _model_name == DEFAULT_MODEL:
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 默认模型已缓存，离线加载
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(_model_name, device="cpu")
    return _model


def _clamp_k(raw: Any) -> int:
    try:
        return max(1, min(50, int(raw)))
    except (TypeError, ValueError):
        return 5


def _clamp_lang(raw: Any) -> str | None:
    """lang 参数白名单：zh/en，其余（含缺省）→ None 表示混合。"""
    val = str(raw or "").strip().lower()
    return val if val in ("zh", "en") else None


def _try_hold_lock(path: str):
    """非阻塞抢排他 flock 并持有到进程退出（单实例守卫，scheduler.lock 同款）。

    返回持有锁的 fd；锁已被别的实例持有返回 ``False``；未配置路径、锁文件
    不可达或平台无 fcntl（Windows）返回 ``None``——退化为仅靠启动方的
    /health 探测防重，服务照常运行。
    """
    if not path:
        return None
    try:
        import fcntl
    except ImportError:
        logger.warning("平台无 fcntl，单实例锁未启用（仅靠 /health 探测防重）")
        return None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        logger.warning("锁文件不可达（%s），单实例锁未启用", exc)
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    return fd  # 故意不关闭：进程退出（含 kill -9）时内核自动放锁


def _norm_domain_filter(raw: Any) -> set[str] | None:
    """domain 过滤归一：str 或 list → 精确匹配值集合；空 → None。"""
    if isinstance(raw, str) and raw.strip():
        return {raw.strip()}
    if isinstance(raw, list):
        vals = {str(v).strip() for v in raw if str(v).strip()}
        return vals or None
    return None


def _norm_tag_filter(raw: Any) -> dict[str, set[str]] | None:
    """tags 过滤归一：扁平 list → {"_any": ids}（任一命中）；dict {facet: ids}
    → facet 间 AND、facet 内任一命中；空/畸形 → None。"""
    if isinstance(raw, dict):
        out = {str(f): {str(i) for i in (ids or []) if i}
               for f, ids in raw.items() if ids}
        return {f: s for f, s in out.items() if s} or None
    if isinstance(raw, list):
        s = {str(i) for i in raw if i}
        return {"_any": s} if s else None
    return None


def _row_matches(row: dict, domains: set[str] | None, tag_filter: dict[str, set[str]] | None) -> bool:
    if domains and str(row.get("domain") or "") not in domains:
        return False
    if tag_filter:
        tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}

        def _facet_ids(facet: str) -> set[str]:
            vals = tags.get(facet)
            return {str(v) for v in vals} if isinstance(vals, list) else set()

        if "_any" in tag_filter:
            row_tags = {t for f in tags for t in _facet_ids(f)}
            if not (row_tags & tag_filter["_any"]):
                return False
        else:
            for facet, want in tag_filter.items():
                if not (_facet_ids(facet) & want):
                    return False
    return True


def _select_hits(cards: list[dict], scores, order, k: int,
                 lang: str | None, domains: set[str] | None = None,
                 tag_filter: dict[str, set[str]] | None = None) -> list[dict]:
    """按分数序选 top-k：语言/标签过滤 + 同 card_id 去重（保留高分行）。

    过滤是"继续扫"语义：当前行被滤掉不终止扫描，直到凑满 k 或耗尽全库——
    耗尽时宁缺毋滥，不回填被滤掉的行。
    """
    hits: list[dict] = []
    seen: set[str] = set()
    for i in order:
        row = cards[int(i)]
        row_lang = row.get("lang") or "zh"  # 单语旧库无 lang 字段 → zh
        if lang and row_lang != lang:
            continue
        if not _row_matches(row, domains, tag_filter):
            continue
        cid = row.get("card_id", "")
        if cid in seen:
            continue
        seen.add(cid)
        hits.append({
            "card_id": cid,
            "lang": row_lang,
            "blog_id": row.get("blog_id", ""),
            "domain": row.get("domain", ""),
            "tags": row.get("tags", {}),
            "heading": row.get("heading", ""),
            "content": row.get("content", "")[:CONTENT_CAP],
            "score": float(scores[int(i)]),
        })
        if len(hits) >= k:
            break
    return hits


def _search(query: str, k: int, lang: str | None = None,
            domains: set[str] | None = None,
            tag_filter: dict[str, set[str]] | None = None) -> list[dict]:
    import numpy as np

    model = _get_model()
    with _encode_lock:  # torch encode 释放 GIL，串行化避免并发竞态
        q = model.encode([_query_instruction() + query], normalize_embeddings=True,
                         show_progress_bar=False)[0].astype(np.float32)
    m_norm = np.linalg.norm(_mat, axis=1)
    m_norm[m_norm == 0] = 1.0
    scores = (_mat @ q) / m_norm  # 库侧再归一化 → 严格余弦
    return _select_hits(_cards, scores, np.argsort(-scores), k, lang, domains, tag_filter)


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
            payload = {
                "ok": True,
                "model": _model_name if _model is not None else None,
                "library_model": _lib_model,
                "count": len(_cards),
            }
            mismatch = _check_model_match()
            if mismatch:
                payload["warning"] = mismatch
            self._send_json(payload)
            return
        if parsed.path == "/search":
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0].strip()
            k = _clamp_k((qs.get("k") or ["5"])[0])
            lang = _clamp_lang((qs.get("lang") or [None])[0])
            domains = _norm_domain_filter((qs.get("domain") or [None])[0])
            tags_raw = (qs.get("tags") or [None])[0]
            tag_filter = _norm_tag_filter(
                [t for t in tags_raw.split(",") if t.strip()] if tags_raw else None)
            self._handle_search(q, k, lang, domains, tag_filter)
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
                lang = _clamp_lang(body.get("lang"))
                domains = _norm_domain_filter(body.get("domain"))
                tag_filter = _norm_tag_filter(body.get("tags"))
            except Exception:
                self._send_json({"error": "bad request"}, code=400)
                return
            self._handle_search(q, k, lang, domains, tag_filter)
            return
        self._send_json({"error": "not found"}, code=404)

    def _handle_search(self, q: str, k: int, lang: str | None = None,
                       domains: set[str] | None = None,
                       tag_filter: dict[str, set[str]] | None = None) -> None:
        if not q:
            self._send_json({"error": "missing q"}, code=400)
            return
        try:
            self._send_json({"hits": _search(q, k, lang, domains, tag_filter)})
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, code=500)

    def log_message(self, fmt: str, *args) -> None:  # 访问日志默认静音，DEBUG 级可取
        logger.debug("%s %s", self.address_string(), fmt % args)


def _watch_stop_marker(server, lock_file: str) -> None:
    """显式全停自检：`cloudra stop` 在数据目录写 daemons.stop 后，本线程
    触发 server.shutdown() 让主线程干净退出（flock 随进程释放）。

    marker 路径由 --lock-file 的父目录（即数据目录）推导；无 lock-file
    时不启用（手动独立运行的实例不受 Cloudra 全停管辖）。
    """
    if not lock_file:
        return
    marker = os.path.join(os.path.dirname(os.path.abspath(lock_file)), "daemons.stop")
    while True:
        time.sleep(1.0)
        try:
            if os.path.isfile(marker):
                logger.info("检测到 daemons.stop（显式全停），kg_vec 退出。")
                server.shutdown()
                return
        except OSError:
            return


def main() -> int:
    global _model_name
    # cloudra 包在本解释器下不可导入，logging 用 stdlib 自理（见模块 docstring）。
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=os.environ.get("KG_VEC_LOG_LEVEL", "INFO").upper(),
    )
    ap = argparse.ArgumentParser(description="知识卡片语义检索微服务（外部 venv 运行）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=os.environ.get("KG_VEC_MODEL", DEFAULT_MODEL),
                    help=f"查询侧 embedding 模型（默认 {DEFAULT_MODEL}，也可用环境变量 "
                         "KG_VEC_MODEL 指定）。换成与向量库不同的模型时必须自行重新编码"
                         "向量库，否则检索分数无效；非默认模型首次使用会从 HF 下载。")
    ap.add_argument("--lock-file", default=os.environ.get("KG_VEC_LOCK_FILE", ""),
                    help="单实例 flock 路径（web_launcher 自启动时传入，也可用环境变量 "
                         "KG_VEC_LOCK_FILE）：抢到才运行，已被持有则直接退出。")
    args = ap.parse_args()
    _model_name = args.model

    lock_fd = _try_hold_lock(args.lock_file)
    if lock_fd is False:
        logger.info("已有活实例（锁被持有: %s），退出。", args.lock_file)
        return 0

    _load_library()
    mismatch = _check_model_match()
    if mismatch:
        logger.warning("%s", mismatch)
    # 后台预热模型：懒加载逻辑保留兜底，但冷启动（CPU 首载约 5-10s）必须
    # 不与调用方的 3s 超时赛跑——监听立即可用，模型在后台线程就绪。
    warm = threading.Thread(target=_get_model, daemon=True)
    warm.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("listening on http://%s:%d  cards=%d  model=%s  library_model=%s",
                args.host, args.port, len(_cards), _model_name, _lib_model)
    threading.Thread(
        target=_watch_stop_marker, args=(server, args.lock_file), daemon=True
    ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if isinstance(lock_fd, int):
            os.close(lock_fd)  # 进程退出内核同样会放锁；显式关闭只是整洁
    return 0


if __name__ == "__main__":
    sys.exit(main())
