/**
 * KnowledgePanel — chem-kb knowledge base browser (near-fullscreen modal).
 *
 * Three stacked views over the /api/v2/knowledge/* routes: the overview stats
 * (default), keyword search (FTS→LIKE fallback + 1–2 hop neighborhood), and
 * the ego graph of a focus entity laid out with dagre (same technique as
 * DagPanel, different field mapping).  Nodes are colored by entity type,
 * edges by relation type; corroborated edges (same triple from ≥2 source
 * cards) carry a badge.  Source pointers are kb: ids in plain text.
 */

import { useEffect, useMemo, useState } from 'react';
import dagre from 'dagre';
import { api } from './api';
import type { KgEdge, KgGraph, KgHealth, KgHealthChannel, KgNode, KgOverview, KgSearchResponse } from './types';

interface KnowledgePanelProps {
  onClose: () => void;
  onToast: (kind: 'ok' | 'error', text: string) => void;
}

type Sel = { kind: 'node' | 'edge'; key: string } | null;

const NODE_H = 44;

const TYPE_COLORS: Record<string, string> = {
  concept: 'hsl(210, 45%, 62%)',
  method: 'hsl(140, 45%, 58%)',
  software: 'hsl(35, 70%, 62%)',
  parameter: 'hsl(280, 40%, 66%)',
  pitfall: 'hsl(8, 65%, 62%)',
  condition: 'hsl(185, 45%, 58%)',
  molecule: 'hsl(95, 45%, 60%)',
  reaction: 'hsl(50, 65%, 60%)',
};

const REL_COLORS: Record<string, string> = {
  applies_to: 'hsl(140, 45%, 58%)',
  common_error_of: 'hsl(8, 65%, 62%)',
  parameter_of: 'hsl(280, 40%, 66%)',
  alternative_to: 'hsl(185, 45%, 58%)',
  part_of: 'hsl(210, 45%, 62%)',
  depends_on: 'hsl(35, 70%, 62%)',
  recommends: 'hsl(95, 45%, 60%)',
  validates: 'hsl(50, 65%, 60%)',
};

function typeColor(t: string): string {
  return TYPE_COLORS[t] ?? 'var(--fg-tertiary)';
}

function relColor(r: string): string {
  return REL_COLORS[r] ?? 'var(--fg-faint)';
}

function trunc(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text;
}

/* Channel health pill: green when ok, red when down (hover shows the error),
   gray while the health probe has not landed yet. */
function HealthPill({
  label,
  ch,
  okText,
}: {
  label: string;
  ch: KgHealthChannel | undefined;
  okText: (c: KgHealthChannel) => string;
}) {
  const state = !ch ? 'unknown' : ch.ok ? 'ok' : 'bad';
  const text = !ch ? '…' : ch.ok ? okText(ch) : 'down';
  return (
    <span className={`kg-health-item ${state}`} title={ch?.error || undefined}>
      <i className="kg-dot" />
      {label}: {text}
    </span>
  );
}

/* Merge per-source edge rows into one edge per (src, dst, rel): corroborated
   becomes "same triple seen from ≥2 different source cards". */
function mergeEdges(edges: KgEdge[]): Array<KgEdge & { sources: string[] }> {
  const byKey = new Map<string, KgEdge & { sources: string[] }>();
  for (const e of edges) {
    const key = `${e.src_id}\u0000${e.dst_id}\u0000${e.rel_type}`;
    const cur = byKey.get(key);
    if (cur) {
      if (!cur.sources.includes(e.source)) cur.sources.push(e.source);
      cur.corroborated = cur.corroborated || e.corroborated;
    } else {
      byKey.set(key, { ...e, sources: [e.source] });
    }
  }
  return [...byKey.values()];
}

interface LNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  data: KgNode;
}
interface LEdge {
  id: string;
  points: Array<{ x: number; y: number }>;
  data: KgEdge & { sources: string[] };
}

function layoutGraph(graph: KgGraph, edges: Array<KgEdge & { sources: string[] }>): {
  nodes: LNode[];
  edges: LEdge[];
  width: number;
  height: number;
} {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 52, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of graph.nodes) {
    const label = n.label || n.id;
    const w = Math.max(110, Math.min(240, label.length * 9 + 24));
    g.setNode(n.id, { width: w, height: NODE_H });
  }
  const ids = new Set(graph.nodes.map((n) => n.id));
  for (const [i, e] of edges.entries()) {
    if (ids.has(e.src_id) && ids.has(e.dst_id) && e.src_id !== e.dst_id) {
      g.setEdge(e.src_id, e.dst_id, {}, `${i}`);
    }
  }
  dagre.layout(g);
  const nodes: LNode[] = graph.nodes.map((n) => {
    const p = g.node(n.id);
    return { id: n.id, x: p?.x ?? 0, y: p?.y ?? 0, w: p?.width ?? 110, h: p?.height ?? NODE_H, data: n };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const laid: LEdge[] = [];
  for (const [i, e] of edges.entries()) {
    const src = byId.get(e.src_id);
    const dst = byId.get(e.dst_id);
    if (!src || !dst) continue;
    const name = `${i}`;
    const pts = (g.edge({ v: e.src_id, w: e.dst_id, name }) as
      | { points?: Array<{ x: number; y: number }> }
      | undefined)?.points;
    if (pts && pts.length >= 2) laid.push({ id: name, points: pts, data: e });
    else laid.push({ id: name, points: [{ x: src.x, y: src.y }, { x: dst.x, y: dst.y }], data: e });
  }
  const dims = g.graph();
  return { nodes, edges: laid, width: Math.max(dims?.width ?? 0, 200), height: Math.max(dims?.height ?? 0, 80) };
}

export default function KnowledgePanel({ onClose, onToast }: KnowledgePanelProps) {
  const [overview, setOverview] = useState<KgOverview | null>(null);
  const [health, setHealth] = useState<KgHealth | null>(null);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState<KgSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [graph, setGraph] = useState<KgGraph | null>(null);
  const [merged, setMerged] = useState<Array<KgEdge & { sources: string[] }>>([]);
  const [hops, setHops] = useState<1 | 2>(1);
  const [lang, setLang] = useState<'zh' | 'en'>('zh');
  const [sel, setSel] = useState<Sel>(null);

  // EN 模式显示 label_en（缺失回退中文 label）；子行展示另一语言（可溯源）。
  const displayName = (n: { label: string; label_en?: string | null }) =>
    lang === 'en' ? n.label_en || n.label : n.label;
  const subName = (n: { label: string; label_en?: string | null }) =>
    lang === 'en' ? (n.label_en && n.label !== n.label_en ? n.label : '') : n.label_en || '';

  useEffect(() => {
    api
      .knowledgeOverview()
      .then(setOverview)
      .catch((e) => onToast('error', e instanceof Error ? e.message : String(e)));
    // 通道健康条与 overview 同拉；健康探测失败不打扰（状态条保持灰显）。
    api
      .knowledgeHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [onToast]);

  const runSearch = () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setGraph(null);
    api
      .knowledgeSearch(q, 10)
      .then(setSearch)
      .catch((e) => onToast('error', e instanceof Error ? e.message : String(e)))
      .finally(() => setSearching(false));
  };

  const openGraph = (focusId: string) => {
    // focus ids contain ":" and CJK — always encode (api.ts handles it too).
    api
      .knowledgeGraph(focusId, hops)
      .then((g) => {
        setGraph(g);
        setMerged(mergeEdges(g.edges));
        setSel(null);
      })
      .catch((e) => onToast('error', e instanceof Error ? e.message : String(e)));
  };

  const layout = useMemo(
    () => (graph ? layoutGraph(graph, merged) : null),
    [graph, merged],
  );

  const selNode = sel?.kind === 'node' ? graph?.nodes.find((n) => n.id === sel.key) : undefined;
  const selEdge =
    sel?.kind === 'edge' && graph ? merged.find((e) => `${e.src_id}\u0000${e.dst_id}\u0000${e.rel_type}` === sel.key) : undefined;
  const byId = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);

  return (
    <div className="modal-backdrop">
      <div className="modal kg-modal">
        <div className="modal-head">
          <span className="modal-title">Knowledge base (chem-kb)</span>
          {graph && (
            <button className="btn ghost sm" onClick={() => setGraph(null)}>
              ← overview
            </button>
          )}
          <div className="kg-hops">
            hops:
            {([1, 2] as const).map((h) => (
              <button
                key={h}
                type="button"
                className={`btn ghost sm${hops === h ? ' active' : ''}`}
                onClick={() => setHops(h)}
              >
                {h}
              </button>
            ))}
            <span className="kg-hops" style={{ marginLeft: 8 }}>
              lang:
              {(['zh', 'en'] as const).map((l) => (
                <button
                  key={l}
                  type="button"
                  className={`btn ghost sm${lang === l ? ' active' : ''}`}
                  onClick={() => setLang(l)}
                >
                  {l === 'zh' ? '中' : 'EN'}
                </button>
              ))}
            </span>
          </div>
          <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={onClose}>
            close
          </button>
        </div>

        <div className="kg-health">
          <HealthPill
            label="semantic"
            ch={health?.semantic}
            okText={(c) => `${c.model || 'warming'} · ${c.count ?? '?'} cards`}
          />
          <HealthPill
            label="graph"
            ch={health?.graph}
            okText={(c) => `${(c.entities ?? 0).toLocaleString()} entities`}
          />
          <HealthPill label="fuzzy" ch={health?.fuzzy} okText={(c) => `${c.cards ?? '?'} cards`} />
        </div>

        <div className="kg-toolbar">
          <input
            className="input kg-query"
            placeholder="search entities…（FTS，短词自动 LIKE 回退）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runSearch()}
          />
          <button className="btn primary sm" disabled={searching} onClick={runSearch}>
            {searching ? '…' : 'search'}
          </button>
          {search && (
            <span className="kg-fallback">
              fallback: <b>{search.fallback ?? '—'}</b>
            </span>
          )}
        </div>

        <div className="kg-body">
          {graph && layout ? (
            <>
              <div className="kg-main dag-canvas">
                <svg width={layout.width} height={layout.height} onClick={() => setSel(null)}>
                  <defs>
                    <marker id="kg-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 z" fill="var(--fg-faint)" />
                    </marker>
                  </defs>
                  {layout.edges.map((e) => {
                    const pts = e.points.map((p) => `${p.x},${p.y}`).join(' ');
                    const mid = e.points[Math.floor((e.points.length - 1) / 2)];
                    const key = `${e.data.src_id}\u0000${e.data.dst_id}\u0000${e.data.rel_type}`;
                    const selected = sel?.kind === 'edge' && sel.key === key;
                    const stroke = selected ? 'var(--green)' : relColor(e.data.rel_type);
                    return (
                      <g key={e.id}>
                        <polyline
                          className="dag-edge-hit"
                          points={pts}
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setSel({ kind: 'edge', key });
                          }}
                        />
                        <polyline
                          className="dag-edge-line"
                          points={pts}
                          markerEnd="url(#kg-arrow)"
                          style={{ stroke, strokeWidth: selected ? 2.2 : 1.2 }}
                        />
                        <text className="dag-edge-label" x={mid.x} y={mid.y - 6} textAnchor="middle">
                          {trunc(e.data.rel_type, 24)}
                          {e.data.corroborated ? ' ⨯2' : ''}
                        </text>
                      </g>
                    );
                  })}
                  {layout.nodes.map((n) => {
                    const selected = sel?.kind === 'node' && sel.key === n.id;
                    const stroke = selected ? 'var(--green)' : typeColor(n.data.type);
                    const isFocus = graph.focus?.id === n.id;
                    const maxChars = Math.floor((n.w - 16) / 7.2);
                    return (
                      <g
                        key={n.id}
                        className={selected ? 'dag-sel' : undefined}
                        transform={`translate(${n.x - n.w / 2}, ${n.y - n.h / 2})`}
                        onClick={(ev) => {
                          ev.stopPropagation();
                          setSel({ kind: 'node', key: n.id });
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        <rect
                          width={n.w}
                          height={n.h}
                          rx={8}
                          style={{
                            fill: 'var(--bg-panel)',
                            stroke,
                            strokeWidth: isFocus ? 2.4 : 1.2,
                          }}
                        />
                        <text className="dag-node-label" x={n.w / 2} y={n.h / 2 - 3} textAnchor="middle">
                          {trunc(displayName(n.data) || n.id, maxChars)}
                        </text>
                        <text
                          className="dag-node-sub"
                          x={n.w / 2}
                          y={n.h / 2 + 12}
                          textAnchor="middle"
                          style={{ fill: stroke }}
                        >
                          {trunc(subName(n.data) || n.data.type, maxChars + 8)}
                          {isFocus ? ' · focus' : ''}
                        </text>
                      </g>
                    );
                  })}
                </svg>
                {graph.truncated && <div className="empty-hint">truncated to 300 nodes</div>}
              </div>
              <div className="kg-side">
                {selNode ? (
                  <div className="modal-section">
                    <div className="modal-section-title">{displayName(selNode)}</div>
                    <div className="kg-fields">
                      <div>
                        <span>type</span> <b style={{ color: typeColor(selNode.type) }}>{selNode.type}</b>
                      </div>
                      {selNode.label_en ? (
                        <div>
                          <span>label_en</span> <b>{selNode.label_en}</b>
                        </div>
                      ) : null}
                      {selNode.label !== selNode.label_en ? (
                        <div>
                          <span>label_zh</span> <b>{selNode.label}</b>
                        </div>
                      ) : null}
                      <div>
                        <span>sources</span> <b>{selNode.n_sources}</b>
                      </div>
                      <div>
                        <span>degree</span> <b>{selNode.degree}</b>
                      </div>
                      <div>
                        <span>hop</span> <b>{selNode.hop}</b>
                      </div>
                    </div>
                    <div className="kg-edges-list">
                      {merged
                        .filter((e) => e.src_id === selNode.id || e.dst_id === selNode.id)
                        .slice(0, 12)
                        .map((e, i) => {
                          const other = e.src_id === selNode.id ? byId.get(e.dst_id) : byId.get(e.src_id);
                          return (
                            <div key={i} className="kg-edge-row">
                              <span style={{ color: relColor(e.rel_type) }}>
                                {e.src_id === selNode.id ? '→' : '←'} {e.rel_type}
                              </span>{' '}
                              {other?.label ?? (e.src_id === selNode.id ? e.dst_id : e.src_id)}
                              {e.corroborated ? <span className="kg-corr">corroborated</span> : null}
                            </div>
                          );
                        })}
                    </div>
                    <div className="kg-src-list">
                      {merged
                        .filter((e) => e.src_id === selNode.id || e.dst_id === selNode.id)
                        .flatMap((e) => e.sources)
                        .filter((s, i, arr) => arr.indexOf(s) === i)
                        .slice(0, 10)
                        .map((s) => (
                          <div key={s}>{s}</div>
                        ))}
                    </div>
                    <button className="btn outline sm" onClick={() => openGraph(selNode.id)}>
                      focus on this node
                    </button>
                  </div>
                ) : selEdge ? (
                  <div className="modal-section">
                    <div className="modal-section-title">{selEdge.rel_type}</div>
                    <div className="kg-fields">
                      <div>
                        <span>from</span> <b>{byId.get(selEdge.src_id)?.label ?? selEdge.src_id}</b>
                      </div>
                      <div>
                        <span>to</span> <b>{byId.get(selEdge.dst_id)?.label ?? selEdge.dst_id}</b>
                      </div>
                      <div>
                        <span>corroborated</span> <b>{selEdge.corroborated ? 'yes' : 'no'}</b>
                      </div>
                    </div>
                    <div className="kg-src-list">
                      {selEdge.sources.map((s) => (
                        <div key={s}>{s}</div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="empty-hint">click a node or edge for details</div>
                )}
              </div>
            </>
          ) : (
            <div className="kg-main kg-overview">
              {overview === null ? (
                <div className="empty-hint">Loading overview…</div>
              ) : !overview.db_present ? (
                <div className="empty-hint">
                  chem_kg.db not found — run <code>cloudra knowledge import</code> first.
                </div>
              ) : (
                <>
                  <div className="kg-stat-row">
                    <div className="kg-stat">
                      <b>{overview.entities.toLocaleString()}</b>
                      <span>entities</span>
                    </div>
                    <div className="kg-stat">
                      <b>{overview.relations.toLocaleString()}</b>
                      <span>relations</span>
                    </div>
                    <div className="kg-stat">
                      <b>{overview.corroborated}</b>
                      <span>corroborated triples</span>
                    </div>
                  </div>
                  <div className="kg-dist">
                    {Object.entries(overview.type_dist).map(([t, n]) => (
                      <button
                        key={t}
                        type="button"
                        className="kg-chip"
                        style={{ borderColor: typeColor(t), color: typeColor(t) }}
                        onClick={() => {
                          setQuery(t);
                        }}
                      >
                        {t} · {n}
                      </button>
                    ))}
                  </div>
                  <div className="kg-dist">
                    {Object.entries(overview.rel_dist).slice(0, 12).map(([r, n]) => (
                      <button
                        key={r}
                        type="button"
                        className="kg-chip"
                        style={{ borderColor: relColor(r), color: relColor(r) }}
                        onClick={() => {
                          setQuery(r);
                        }}
                      >
                        {r} · {n}
                      </button>
                    ))}
                  </div>
                </>
              )}
              {search && (
                <div className="kg-results">
                  {search.results.length === 0 ? (
                    <div className="empty-hint">no hits</div>
                  ) : (
                    search.results.map((r) => (
                      <div
                        key={`${r.id}:${r.hop}`}
                        className="kg-result"
                        onClick={() => openGraph(r.id)}
                        title="open ego graph"
                      >
                        <span className="kg-result-type" style={{ color: typeColor(r.type) }}>
                          {r.type}
                        </span>
                        <span className="kg-result-label">
                          {lang === 'en' ? r.label_en || r.label : r.label}
                        </span>
                        {r.hop > 0 && <span className="kg-result-hop">hop {r.hop}</span>}
                        <span className="kg-result-src">{r.source}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
