"""chem_kg.db 的持久化与查询（sync-only）。

所有函数都是同步 SQLite 访问：CLI / 测试上下文可直接调用；事件循环里的
调用方（api_v2 路由、knowledge provider 的宿主线程除外）必须经
``asyncio.to_thread`` 卸载。写路径只有 ``ensure_schema`` / ``import_csv``
（建库/导入时切 WAL + 结束后 checkpoint TRUNCATE）；读路径一律只读连接
（``mode=ro``，``busy_timeout=60000`` + ``synchronous=NORMAL``），缺库时
返回空结果、绝不建库。方法命名避开 ``connect``（运行时同步护栏会告警）。
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

PathLike = Union[str, Path]

SCHEMA_VERSION = 1
_CONTENT_FOLD = 200  # 码点（code points），非字节

_DDL = [
    "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)",
    """
    CREATE TABLE IF NOT EXISTS kg_entities(
      id TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT NOT NULL, smiles TEXT,
      props TEXT, n_sources INTEGER NOT NULL DEFAULT 1, created_at TEXT, updated_at TEXT)
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_relations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      src_id TEXT NOT NULL REFERENCES kg_entities(id), dst_id TEXT NOT NULL REFERENCES kg_entities(id),
      rel_type TEXT NOT NULL, evidence_level TEXT NOT NULL DEFAULT 'L0', source TEXT NOT NULL,
      falsified INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '', created_at TEXT,
      UNIQUE(src_id, dst_id, rel_type, source))
    """,
    "CREATE INDEX IF NOT EXISTS idx_rel_src ON kg_relations(src_id)",
    "CREATE INDEX IF NOT EXISTS idx_rel_dst ON kg_relations(dst_id)",
    # 混合 provider 的"卡→图缝合"查询（relations_of_source）走这枚索引。
    "CREATE INDEX IF NOT EXISTS idx_rel_source ON kg_relations(source)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS kg_entities_fts USING fts5(
      label, smiles, props, content='kg_entities', content_rowid='rowid', tokenize='trigram')
    """,
    # 官方 external-content 三触发器：写 kg_entities 时同步维护 FTS。
    """
    CREATE TRIGGER IF NOT EXISTS kg_entities_ai AFTER INSERT ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(rowid, label, smiles, props)
      VALUES (new.rowid, new.label, new.smiles, new.props);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS kg_entities_ad AFTER DELETE ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(kg_entities_fts, rowid, label, smiles, props)
      VALUES ('delete', old.rowid, old.label, old.smiles, old.props);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS kg_entities_au AFTER UPDATE ON kg_entities BEGIN
      INSERT INTO kg_entities_fts(kg_entities_fts, rowid, label, smiles, props)
      VALUES ('delete', old.rowid, old.label, old.smiles, old.props);
      INSERT INTO kg_entities_fts(rowid, label, smiles, props)
      VALUES (new.rowid, new.label, new.smiles, new.props);
    END
    """,
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _probe_sqlite() -> None:
    # FTS5 trigram 分词器需要 >= 3.34；只在建库/导入路径探测并硬失败。
    if sqlite3.sqlite_version_info < (3, 34, 0):
        raise RuntimeError(
            f"sqlite {sqlite3.sqlite_version} too old for FTS5 trigram (need >= 3.34.0)"
        )


def _open_rw(db_path: PathLike) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=60.0)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _open_ro(db_path: PathLike) -> Optional[sqlite3.Connection]:
    p = Path(db_path)
    if not p.exists():
        return None
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=60.0)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def ensure_schema(db_path: PathLike) -> None:
    """建库/补表（幂等）。只在导入路径调用；读路径绝不建库。"""
    _probe_sqlite()
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = _open_rw(p)
    try:
        con.execute("BEGIN")
        for stmt in _DDL:
            con.execute(stmt)
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------
# 查询（只读）
# --------------------------------------------------------------------------

def _fold(text: str, limit: int = _CONTENT_FOLD) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # 句边界优先（。；;！!？?．. ），找不到就硬截。
    for i in range(len(cut) - 1, max(limit - 60, 0), -1):
        if cut[i] in "。；;！!？?．.":
            return cut[: i + 1]
    return cut


def _escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# 度预聚合 CTE 片段（无 WITH 前缀，拼进各查询的 WITH 列表）：
# 实体在关系表中出现的总次数（出边 + 入边）。
_DEG_CTE = """
  deg AS (
    SELECT id, SUM(cnt) AS degree FROM (
      SELECT src_id AS id, COUNT(*) AS cnt FROM kg_relations GROUP BY src_id
      UNION ALL
      SELECT dst_id AS id, COUNT(*) AS cnt FROM kg_relations GROUP BY dst_id
    ) GROUP BY id
  )"""


def _match_seeds(con: sqlite3.Connection, query: str, cap: int) -> tuple[list[sqlite3.Row], str]:
    """直接命中（FTS 优先，整体 LIKE 回退）。

    v11 语义：≥3 字符的 token 进 FTS（先全 AND，零命中再 OR——bm25 排序天然
    压低英文停用词权重）；短 token（"to"/"TS"/2 字中文）不参与 FTS，保留给
    整串 LIKE 兜底。英文自然语句（"how to find …"）由此可经 props.label_en
    命中图谱。fallback 标记：fts / fts_or / like。
    """
    tokens = [t for t in query.split() if t]
    fts_tokens = [t for t in tokens if len(t) >= 3]
    if fts_tokens:
        match = " ".join('"' + t.replace('"', '""') + '"' for t in fts_tokens)
        rows = con.execute(
            """
            SELECT e.id, e.type, e.label, e.smiles, e.n_sources, e.props,
                   bm25(kg_entities_fts) AS r
            FROM kg_entities_fts f JOIN kg_entities e ON e.rowid = f.rowid
            WHERE kg_entities_fts MATCH ?
            ORDER BY r LIMIT ?
            """,
            (match, cap),
        ).fetchall()
        if rows:
            return rows, "fts"
        if len(fts_tokens) > 1:
            match_or = " OR ".join('"' + t.replace('"', '""') + '"' for t in fts_tokens)
            rows = con.execute(
                """
                SELECT e.id, e.type, e.label, e.smiles, e.n_sources, e.props,
                       bm25(kg_entities_fts) AS r
                FROM kg_entities_fts f JOIN kg_entities e ON e.rowid = f.rowid
                WHERE kg_entities_fts MATCH ?
                ORDER BY r LIMIT ?
                """,
                (match_or, cap),
            ).fetchall()
            if rows:
                return rows, "fts_or"
    like = "%" + _escape_like(" ".join(tokens)) + "%"
    rows = con.execute(
        """
        SELECT id, type, label, smiles, n_sources, props, NULL AS r
        FROM kg_entities
        WHERE label LIKE ? ESCAPE '\\' OR smiles LIKE ? ESCAPE '\\'
           OR props LIKE ? ESCAPE '\\'
        ORDER BY n_sources DESC, label LIMIT ?
        """,
        (like, like, like, cap),
    ).fetchall()
    return rows, "like"


def _label_en(props: Any) -> str | None:
    """props 列（JSON 字符串）里的 label_en；解析失败/缺失返回 None。"""
    if not props:
        return None
    try:
        val = json.loads(props).get("label_en")
        return str(val) if val else None
    except (TypeError, ValueError):
        return None


def _bm25_score(raw: Any, n_sources: int) -> float:
    # bm25 为负值（越负越相关）；归一到 (0,1) 并叠加轻量 n_sources 先验。
    try:
        r = float(raw)
    except (TypeError, ValueError):
        r = 0.0
    return -r / (1.0 + abs(r)) + 0.1 * min(n_sources, 5) / 5.0


def search_graph(db_path: PathLike, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """FTS(→LIKE) 直接命中 + 1~2 跳邻域扩展，确定性排序后返回条目列表。

    缺库时返回 ``[]``（绝不建库）。返回 dict 字段：id/type/label/content/
    score/hop/fallback/source（首个 kb: 关系指针，兜底 "chem-kb"）。
    """
    con = _open_ro(db_path)
    if con is None:
        return []
    try:
        con.row_factory = sqlite3.Row
        seeds, fallback = _match_seeds(con, query, cap=max(limit, 16))
        if not seeds:
            return []
        seed_ids = [str(r["id"]) for r in seeds]
        seed_score = {str(r["id"]): _bm25_score(r["r"], r["n_sources"] or 1) for r in seeds}
        if fallback == "like":
            seed_score = {k: 0.5 + 0.1 * min(s, 5) / 5.0 for k, s in
                          ((str(r["id"]), r["n_sources"] or 1) for r in seeds)}
        placeholders = ",".join("?" * len(seed_ids))
        rows = con.execute(
            f"""
            WITH RECURSIVE walk(id, hop) AS (
              SELECT id, 0 FROM kg_entities WHERE id IN ({placeholders})
              UNION
              SELECT CASE WHEN w.id = r.src_id THEN r.dst_id ELSE r.src_id END, w.hop + 1
              FROM walk w JOIN kg_relations r ON w.id IN (r.src_id, r.dst_id)
              WHERE w.hop < 2
            ),""" + _DEG_CTE + """
            SELECT e.id, e.type, e.label, e.smiles, e.n_sources, e.props,
                   MIN(w.hop) AS hop, COALESCE(d.degree, 0) AS degree
            FROM walk w JOIN kg_entities e ON e.id = w.id LEFT JOIN deg d ON d.id = e.id
            GROUP BY e.id
            ORDER BY hop, degree DESC, label
            LIMIT ?
            """,
            (*seed_ids, limit),
        ).fetchall()
        # 直接命中的相关性分要排在邻居前面（hop=0 优先由 ORDER BY 保证）；
        # 同 hop 内按 FTS/LIKE 原始分（邻居无原始分，用度数先验）。
        out: list[dict[str, Any]] = []
        for r in rows:
            eid = str(r["id"])
            score = seed_score.get(eid)
            if score is None:
                score = 0.1 * min(r["n_sources"] or 1, 5) / 5.0
            src_row = con.execute(
                "SELECT source FROM kg_relations WHERE src_id = ? OR dst_id = ? LIMIT 1",
                (eid, eid),
            ).fetchone()
            content = _fold(f"{r['label']}（{r['type']}，度 {r['degree']}，源 {r['n_sources']}）")
            out.append({
                "id": eid,
                "type": r["type"],
                "label": r["label"],
                "label_en": _label_en(r["props"]),
                "content": content,
                "score": score,
                "hop": int(r["hop"] or 0),
                "fallback": fallback,
                "source": str(src_row["source"]) if src_row else "chem-kb",
            })
        out.sort(key=lambda x: (x["hop"], -x["score"]))
        return out
    finally:
        con.close()


def relations_of_source(db_path: PathLike, source_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """按 source='kb:{id}' 取该知识卡片的行级关系（卡→图缝合用）。"""
    con = _open_ro(db_path)
    if con is None:
        return []
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT r.rel_type, r.falsified, s.label AS src_label, d.label AS dst_label
            FROM kg_relations r
            JOIN kg_entities s ON s.id = r.src_id
            JOIN kg_entities d ON d.id = r.dst_id
            WHERE r.source = ?
            ORDER BY r.id LIMIT ?
            """,
            (source_key, limit),
        ).fetchall()
        return [
            {
                "rel_type": r["rel_type"],
                "falsified": bool(r["falsified"]),
                "src_label": r["src_label"],
                "dst_label": r["dst_label"],
            }
            for r in rows
        ]
    finally:
        con.close()


def ego_graph(
    db_path: PathLike, focus_id: str, hops: int = 1, max_nodes: int = 300
) -> Optional[dict[str, Any]]:
    """focus 实体的 1~2 跳邻域。focus 不存在或缺库返回 ``None``。"""
    con = _open_ro(db_path)
    if con is None:
        return None
    try:
        con.row_factory = sqlite3.Row
        focus = con.execute("SELECT * FROM kg_entities WHERE id = ?", (focus_id,)).fetchone()
        if focus is None:
            return None
        rows = con.execute(
            """
            WITH RECURSIVE walk(id, hop) AS (
              SELECT ?, 0
              UNION
              SELECT CASE WHEN w.id = r.src_id THEN r.dst_id ELSE r.src_id END, w.hop + 1
              FROM walk w JOIN kg_relations r ON w.id IN (r.src_id, r.dst_id)
              WHERE w.hop < ?
            ),""" + _DEG_CTE + """
            SELECT e.id, e.type, e.label, e.n_sources, e.props, MIN(w.hop) AS hop,
                   COALESCE(d.degree, 0) AS degree
            FROM walk w JOIN kg_entities e ON e.id = w.id LEFT JOIN deg d ON d.id = e.id
            GROUP BY e.id
            """,
            (focus_id, hops),
        ).fetchall()
        truncated = False
        if len(rows) > max_nodes:
            # 去重后超限：按 n_sources DESC, degree DESC, label ASC 截断（确定性）；
            # focus 节点必须保留（哪怕它排序垫底），否则邻域失去锚点。
            rows = sorted(rows, key=lambda r: (-(r["n_sources"] or 0), -(r["degree"] or 0), r["label"]))
            others = [r for r in rows if str(r["id"]) != focus_id][:max_nodes - 1]
            rows = [r for r in rows if str(r["id"]) == focus_id] + others
            truncated = True
        node_ids = {str(r["id"]) for r in rows}
        by_id = {str(r["id"]): r for r in rows}
        nodes = [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "label": r["label"],
                "label_en": _label_en(r["props"]),
                "n_sources": int(r["n_sources"] or 1),
                "degree": int(r["degree"] or 0),
                "hop": int(r["hop"] or 0),
            }
            for r in rows
        ]
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        erows = con.execute(
            """
            SELECT r.src_id, r.dst_id, r.rel_type, r.source, r.falsified
            FROM kg_relations r
            WHERE r.src_id IN (%s) AND r.dst_id IN (%s)
            ORDER BY r.id
            """
            % (",".join("?" * len(node_ids)), ",".join("?" * len(node_ids))),
            (*node_ids, *node_ids),
        ).fetchall()
        corrob: dict[tuple[str, str, str], set[str]] = {}
        for er in erows:
            corrob.setdefault((er["src_id"], er["dst_id"], er["rel_type"]), set()).add(er["source"])
        for er in erows:
            key = (er["src_id"], er["dst_id"], er["rel_type"], er["source"])
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "src_id": er["src_id"],
                "dst_id": er["dst_id"],
                "rel_type": er["rel_type"],
                "corroborated": len(corrob[(er["src_id"], er["dst_id"], er["rel_type"])]) > 1,
                "source": er["source"],
                "falsified": bool(er["falsified"]),
            })
        return {
            "focus": {
                "id": str(focus["id"]), "type": focus["type"], "label": focus["label"],
                "label_en": _label_en(focus["props"]),
                "n_sources": int(focus["n_sources"] or 1),
                "degree": int(by_id[focus_id]["degree"] or 0), "hop": 0,
            },
            "nodes": nodes,
            "edges": edges,
            "truncated": truncated,
        }
    finally:
        con.close()


def overview(db_path: PathLike) -> dict[str, Any]:
    """库概览：计数、分布、corroborated（跨卡同构三元组）数。"""
    con = _open_ro(db_path)
    if con is None:
        return {"db_present": False, "entities": 0, "relations": 0,
                "type_dist": {}, "rel_dist": {}, "corroborated": 0}
    try:
        entities = con.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
        relations = con.execute("SELECT COUNT(*) FROM kg_relations").fetchone()[0]
        type_dist = dict(con.execute(
            "SELECT type, COUNT(*) FROM kg_entities GROUP BY type ORDER BY COUNT(*) DESC"))
        rel_dist = dict(con.execute(
            "SELECT rel_type, COUNT(*) FROM kg_relations GROUP BY rel_type ORDER BY COUNT(*) DESC"))
        corroborated = con.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT src_id, dst_id, rel_type FROM kg_relations
              GROUP BY src_id, dst_id, rel_type HAVING COUNT(DISTINCT source) > 1)
            """
        ).fetchone()[0]
        return {
            "db_present": True,
            "entities": entities,
            "relations": relations,
            "type_dist": type_dist,
            "rel_dist": rel_dist,
            "corroborated": corroborated,
        }
    finally:
        con.close()


# --------------------------------------------------------------------------
# 导入（唯一写路径）
# --------------------------------------------------------------------------

def _read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    """utf-8-sig 读取；严格 UTF-8 失败后整文件 GBK 重解码。返回 (rows, encoding)。"""
    raw = path.read_bytes()
    encoding = "utf-8-sig"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk")
        encoding = "gbk"
    return list(csv.DictReader(text.splitlines(keepends=True))), encoding


def import_csv(
    db_path: PathLike, entities_csv: PathLike, relations_csv: PathLike,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """KG CSV → chem_kg.db。幂等（两表 ON CONFLICT DO UPDATE）。

    entities 先行；relations 在事务内做引用校验，悬挂行进坏行报告（不中断）。
    结束后 FTS rebuild + wal_checkpoint(TRUNCATE)。
    """
    started = time.perf_counter()
    _probe_sqlite()
    ensure_schema(db_path)

    ent_path, rel_path = Path(entities_csv), Path(relations_csv)
    ent_rows, ent_enc = _read_csv_rows(ent_path)
    rel_rows, rel_enc = _read_csv_rows(rel_path)

    now = _utc_now()
    con = _open_rw(db_path)
    report: dict[str, Any] = {
        "entities_csv": ent_path.name, "relations_csv": rel_path.name,
        "encoding": {"entities": ent_enc, "relations": rel_enc},
        "entities": 0, "relations": 0, "bad_rows": [],
    }
    try:
        con.execute("BEGIN")
        for i in range(0, len(ent_rows), batch_size):
            chunk = ent_rows[i : i + batch_size]
            con.executemany(
                """
                INSERT INTO kg_entities(id, type, label, smiles, props, n_sources,
                                        created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  type=excluded.type, label=excluded.label, smiles=excluded.smiles,
                  props=excluded.props, n_sources=excluded.n_sources,
                  updated_at=excluded.updated_at
                """,
                [
                    (
                        (r.get("id") or "").strip(),
                        (r.get("type") or "concept").strip(),
                        (r.get("label") or "").strip(),
                        (r.get("smiles") or "").strip() or None,
                        (r.get("props") or "").strip() or None,
                        int(r.get("n_sources") or 1),
                        now, now,
                    )
                    for r in chunk
                ],
            )
            con.commit()
            report["entities"] += len(chunk)
        known_ids = {r[0] for r in con.execute("SELECT id FROM kg_entities")}

        good: list[tuple] = []
        for lineno, r in enumerate(rel_rows, start=2):  # +1 header, +1 1-based
            src, dst = (r.get("src_id") or "").strip(), (r.get("dst_id") or "").strip()
            if src not in known_ids or dst not in known_ids:
                report["bad_rows"].append({
                    "line": lineno,
                    "reason": f"dangling src/dst: {src} -> {dst}",
                })
                continue
            falsified = str(r.get("falsified") or "").strip().lower() in ("1", "true", "yes")
            good.append((
                src, dst,
                (r.get("rel_type") or "").strip() or "related_to",
                (r.get("evidence_level") or "L0").strip(),
                (r.get("source") or "").strip(),
                1 if falsified else 0,
                (r.get("note") or "").strip(),
                now,
            ))
        for i in range(0, len(good), batch_size):
            chunk = good[i : i + batch_size]
            con.executemany(
                """
                INSERT INTO kg_relations(src_id, dst_id, rel_type, evidence_level,
                                         source, falsified, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(src_id, dst_id, rel_type, source) DO UPDATE SET
                  evidence_level=excluded.evidence_level, falsified=excluded.falsified,
                  note=excluded.note
                """,
                chunk,
            )
            con.commit()
            report["relations"] += len(chunk)

        con.execute("INSERT INTO kg_entities_fts(kg_entities_fts) VALUES ('rebuild')")
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # rdkit 可选校验（软告警）：SMILES 列能解析的比例。
        smiles_bad = 0
        try:
            from rdkit import Chem  # type: ignore
        except ImportError:
            Chem = None  # noqa: N816
        if Chem is not None:
            for (smi,) in con.execute(
                "SELECT smiles FROM kg_entities WHERE smiles IS NOT NULL AND smiles != ''"
            ):
                if Chem.MolFromSmiles(smi) is None:
                    smiles_bad += 1
        report["smiles_invalid"] = smiles_bad
        report["seconds"] = round(time.perf_counter() - started, 2)
        return report
    finally:
        con.close()
