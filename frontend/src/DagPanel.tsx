import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import dagre from 'dagre';
import { api } from './api';
import type { Project } from './types';

/* Structured DAG panel (delivery-only orchestration): dagre-laid-out SVG of the
   delivery/mechanism graph with per-element stage chips, coverage gates with
   inline waivers, the pending CallReview inbox (read-only — verdicts are the
   Supervisor's), a draft banner while no mechanism is accepted, mutation
   history and supervisor replan.  Data comes from the v2 DAG routes. */

type Json = Record<string, any>;
type Sel = { kind: 'node' | 'edge'; id: string } | null;

interface DagData {
  mode: string;
  delivery: Json | null;
  report: Json | null;
  history: Json[];
  projection: Json | null;
  reviews: Json | null;
  draft: Json | null;
}

const DEL_ROLES = ['reactant', 'intermediate', 'product'];
const NODE_H = 46;

function shortId(value: unknown): string {
  const s = String(value ?? '');
  return s.length > 18 ? `${s.slice(0, 18)}…` : s;
}

function trunc(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text;
}

/* ------------------------------------------------------------- stages */

const STAGE_ICON: Record<string, string> = {
  supported: '✓',
  pending: '…',
  skipped: '⊘',
  rejected: '✗',
};

function stageKind(status: unknown): 'ok' | 'warn' | undefined {
  const s = String(status ?? '');
  if (s === 'supported') return 'ok';
  if (s === 'skipped' || s === 'rejected') return 'warn';
  return undefined;
}

function StageChips({ stages }: { stages: Json[] }) {
  if (!stages.length) return null;
  return (
    <span className="dag-stages">
      {stages.map((s, i) => (
        <span
          key={`${String(s.kind)}:${i}`}
          className={`dag-badge${stageKind(s.status) ? ` ${stageKind(s.status)}` : ''}`}
          title={String(s.reason ?? '')}
        >
          {String(s.kind)}
          {STAGE_ICON[String(s.status)] ?? '?'}
        </span>
      ))}
    </span>
  );
}

function stageSummary(stages: unknown): string {
  const list = (stages as Json[] | undefined) ?? [];
  return list.map((s) => `${String(s.kind)}${STAGE_ICON[String(s.status)] ?? '?'}`).join(' ');
}

/* ------------------------------------------------------------- colors */

function evidenceColor(level: unknown): string {
  const l = String(level ?? '');
  if (!l || l === 'proposed') return 'var(--border-strong)';
  if (l === 'rejected' || l === 'inconclusive') return 'var(--yellow-soft)';
  return 'var(--green-soft)'; // *_supported / thermo_annotated
}

/* ------------------------------------------------------------- layout */

interface LNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  data: Json;
}
interface LEdge {
  id: string;
  points: Array<{ x: number; y: number }>;
  data: Json;
}

function layoutGraph(graph: Json): { nodes: LNode[]; edges: LEdge[]; width: number; height: number } {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 56, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));
  const nodes: Json[] = graph.nodes ?? [];
  const edges: Json[] = graph.edges ?? [];
  for (const n of nodes) {
    const label = String(n.label ?? n.node_id);
    const w = Math.max(120, Math.min(240, label.length * 8 + 24));
    g.setNode(String(n.node_id), { width: w, height: NODE_H });
  }
  const ids = new Set(nodes.map((n) => String(n.node_id)));
  const laidOut = new Set<string>();
  for (const e of edges) {
    const s = String(e.source_node_id);
    const t = String(e.target_node_id);
    const id = String(e.edge_id);
    if (ids.has(s) && ids.has(t) && s !== t) {
      g.setEdge(s, t, {}, id);
      laidOut.add(id);
    }
  }
  dagre.layout(g);
  const ln: LNode[] = nodes.map((n) => {
    const id = String(n.node_id);
    const p = g.node(id);
    return { id, x: p?.x ?? 0, y: p?.y ?? 0, w: p?.width ?? 120, h: p?.height ?? NODE_H, data: n };
  });
  const byId = new Map(ln.map((n) => [n.id, n]));
  const le: LEdge[] = [];
  for (const e of edges) {
    const id = String(e.edge_id);
    const s = String(e.source_node_id);
    const t = String(e.target_node_id);
    const src = byId.get(s);
    const dst = byId.get(t);
    if (!src || !dst) continue;
    if (laidOut.has(id)) {
      const pts = (g.edge({ v: s, w: t, name: id }) as { points?: Array<{ x: number; y: number }> })?.points;
      if (pts && pts.length >= 2) {
        le.push({ id, points: pts, data: e });
        continue;
      }
    }
    // self-loop / fallback: straight line between node centers
    le.push({ id, points: [{ x: src.x, y: src.y }, { x: dst.x, y: dst.y }], data: e });
  }
  const dims = g.graph();
  return { nodes: ln, edges: le, width: Math.max(dims?.width ?? 0, 200), height: Math.max(dims?.height ?? 0, 80) };
}

/* ------------------------------------------------------------- svg view */

function GraphView({ graph, sel, onSelect }: {
  graph: Json;
  sel: Sel;
  onSelect: (s: Sel) => void;
}) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  if (layout.nodes.length === 0) return <div className="empty-hint">empty graph</div>;
  const isSel = (k: 'node' | 'edge', id: string) => sel?.kind === k && sel.id === id;
  return (
    <div className="dag-canvas">
      <svg width={layout.width} height={layout.height} onClick={() => onSelect(null)}>
        <defs>
          <marker id="dag-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--fg-faint)" />
          </marker>
        </defs>
        {layout.edges.map((e) => {
          const pts = e.points.map((p) => `${p.x},${p.y}`).join(' ');
          const mid = e.points[Math.floor((e.points.length - 1) / 2)];
          const selected = isSel('edge', e.id);
          const stroke = selected ? 'var(--green)' : evidenceColor(e.data.evidence_level);
          const stages = stageSummary(e.data.stages);
          return (
            <g key={e.id}>
              <polyline
                className="dag-edge-hit"
                points={pts}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSelect({ kind: 'edge', id: e.id });
                }}
              />
              <polyline
                className="dag-edge-line"
                points={pts}
                markerEnd="url(#dag-arrow)"
                style={{
                  stroke,
                  strokeWidth: selected ? 2.2 : 1.2,
                  strokeDasharray: e.data.evidence_vetoed ? '5 3' : undefined,
                }}
              />
              {e.data.label ? (
                <text className="dag-edge-label" x={mid.x} y={mid.y - 6} textAnchor="middle">
                  {trunc(String(e.data.label), 28)}
                </text>
              ) : null}
              {stages ? (
                <text className="dag-edge-label" x={mid.x} y={mid.y + 10} textAnchor="middle">
                  {trunc(stages, 40)}
                </text>
              ) : null}
            </g>
          );
        })}
        {layout.nodes.map((n) => {
          const selected = isSel('node', n.id);
          const stroke = selected ? 'var(--green)' : evidenceColor(n.data.evidence_level);
          const stages = stageSummary(n.data.stages);
          const sub = stages || String(n.data.evidence_level ?? '-');
          const maxChars = Math.floor((n.w - 16) / 6.8);
          return (
            <g
              key={n.id}
              className={selected ? 'dag-sel' : undefined}
              transform={`translate(${n.x - n.w / 2}, ${n.y - n.h / 2})`}
              onClick={(ev) => {
                ev.stopPropagation();
                onSelect({ kind: 'node', id: n.id });
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
                  strokeWidth: selected ? 2.4 : 1.2,
                  strokeDasharray: n.data.evidence_vetoed ? '5 3' : undefined,
                }}
              />
              <text className="dag-node-label" x={n.w / 2} y={n.h / 2 - 3} textAnchor="middle">
                {trunc(String(n.data.label ?? n.id), maxChars)}
              </text>
              <text className="dag-node-sub" x={n.w / 2} y={n.h / 2 + 12} textAnchor="middle" style={{ fill: stroke }}>
                {trunc(sub, maxChars + 8)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------- small bits */

function Badge({ text, kind }: { text: string; kind?: 'ok' | 'warn' }) {
  return <span className={`dag-badge${kind ? ` ${kind}` : ''}`}>{text}</span>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="dag-field">
      <label>{label}</label>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------- edit forms */

interface FormCtx {
  busy: boolean;
  onSave: (ops: unknown[], rationale: string, okMsg: string) => void;
}

function NodeEditForm({ node, ctx }: { node: Json; ctx: FormCtx }) {
  const [label, setLabel] = useState(String(node.label ?? ''));
  const [reason, setReason] = useState(String(node.reason ?? ''));
  const [role, setRole] = useState(String(node.role ?? ''));
  const [smiles, setSmiles] = useState(String(node.smiles ?? ''));
  const [rationale, setRationale] = useState('');

  function save() {
    const changes: Json = {
      label: label.trim(),
      reason: reason.trim(),
      role: role || null,
      smiles: smiles.trim() || null,
    };
    ctx.onSave([{ op: 'update_node', graph: 'delivery', node_id: node.node_id, changes }], rationale.trim(), 'Node updated');
  }

  return (
    <div className="dag-form">
      <div className="dag-title">delivery node · {String(node.node_id)}</div>
      <div className="dag-meta">
        type:{String(node.node_type ?? '-')} · required:{String(Boolean(node.required))} · evidence:
        {String(node.evidence_level ?? '-')}
        {node.evidence_vetoed ? ' (vetoed)' : ''}
      </div>
      <StageChips stages={(node.stages as Json[] | undefined) ?? []} />
      <Field label="label">
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Field label="role">
        <select className="select" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">(none)</option>
          {DEL_ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </Field>
      <Field label="smiles">
        <input className="input" value={smiles} onChange={(e) => setSmiles(e.target.value)} placeholder="(none)" />
      </Field>
      <Field label="reason">
        <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="rationale (for the mutation log, optional)">
        <input className="input" value={rationale} onChange={(e) => setRationale(e.target.value)} />
      </Field>
      <div className="dag-actions">
        <button className="btn outline sm" disabled={ctx.busy || !label.trim()} onClick={save}>
          Save
        </button>
      </div>
    </div>
  );
}

function EdgeEditForm({ edge, nodeLabels, ctx }: {
  edge: Json;
  nodeLabels: Map<string, string>;
  ctx: FormCtx;
}) {
  const [label, setLabel] = useState(String(edge.label ?? ''));
  const [reason, setReason] = useState(String(edge.reason ?? ''));
  const [rationale, setRationale] = useState('');
  const flags = Object.keys(edge).filter((k) => k.endsWith('_supported') && edge[k]);
  const src = nodeLabels.get(String(edge.source_node_id)) ?? String(edge.source_node_id);
  const dst = nodeLabels.get(String(edge.target_node_id)) ?? String(edge.target_node_id);

  function save() {
    const changes: Json = { label: label.trim(), reason: reason.trim() };
    ctx.onSave([{ op: 'update_edge', graph: 'delivery', edge_id: edge.edge_id, changes }], rationale.trim(), 'Edge updated');
  }

  function remove() {
    if (!rationale.trim()) return;
    ctx.onSave(
      [{ op: 'remove_edge', graph: 'delivery', edge_id: edge.edge_id }],
      rationale.trim(),
      'Edge removed',
    );
  }

  return (
    <div className="dag-form">
      <div className="dag-title">delivery edge · {String(edge.edge_id)}</div>
      <div className="dag-meta">
        {src} → {dst} · type:{String(edge.edge_type ?? '-')} · required:{String(Boolean(edge.required))} · evidence:
        {String(edge.evidence_level ?? '-')}
        {edge.evidence_vetoed ? ' (vetoed)' : ''}
      </div>
      <StageChips stages={(edge.stages as Json[] | undefined) ?? []} />
      {flags.length > 0 && (
        <div className="dag-meta">flags: {flags.map((f) => <Badge key={f} text={f} kind="ok" />)}</div>
      )}
      <Field label="label">
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Field label="reason">
        <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="rationale (required to remove edge)">
        <input className="input" value={rationale} onChange={(e) => setRationale(e.target.value)} />
      </Field>
      <div className="dag-actions">
        <button className="btn outline sm" disabled={ctx.busy} onClick={save}>
          Save
        </button>
        <button className="btn yellow sm" disabled={ctx.busy || !rationale.trim()} onClick={remove}>
          Remove edge
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- add forms */

function AddForms({ nodes, ctx }: { nodes: Json[]; ctx: FormCtx }) {
  const [nLabel, setNLabel] = useState('');
  const [nRole, setNRole] = useState('');
  const [nSmiles, setNSmiles] = useState('');
  const [eSrc, setESrc] = useState('');
  const [eDst, setEDst] = useState('');
  const [eLabel, setELabel] = useState('');

  function addNode() {
    if (!nLabel.trim()) return;
    const node: Json = { node_id: `n_${Date.now()}`, node_type: 'occurrence', label: nLabel.trim() };
    if (nRole) node.role = nRole;
    if (nSmiles.trim()) node.smiles = nSmiles.trim();
    ctx.onSave([{ op: 'add_node', graph: 'delivery', node }], '', 'Node added');
    setNLabel('');
    setNSmiles('');
  }

  function addEdge() {
    if (!eSrc || !eDst) return;
    const edge: Json = {
      edge_id: `e_${Date.now()}`,
      edge_type: 'elementary_step',
      source_node_id: eSrc,
      target_node_id: eDst,
    };
    if (eLabel.trim()) edge.label = eLabel.trim();
    ctx.onSave([{ op: 'add_edge', graph: 'delivery', edge }], '', 'Edge added');
    setELabel('');
  }

  return (
    <details className="dag-add">
      <summary>＋ add node / edge</summary>
      <div className="dag-form">
        <div className="dag-title">add node</div>
        <Field label="label">
          <input className="input" value={nLabel} onChange={(e) => setNLabel(e.target.value)} placeholder="describe the species" />
        </Field>
        <Field label="role (optional)">
          <select className="select" value={nRole} onChange={(e) => setNRole(e.target.value)}>
            <option value="">(none)</option>
            {DEL_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </Field>
        <Field label="smiles (optional)">
          <input className="input" value={nSmiles} onChange={(e) => setNSmiles(e.target.value)} />
        </Field>
        <div className="dag-actions">
          <button className="btn outline sm" disabled={ctx.busy || !nLabel.trim()} onClick={addNode}>
            Add node
          </button>
        </div>
        <div className="dag-title" style={{ marginTop: 10 }}>add edge</div>
        <div className="dag-link-row">
          <select className="select" value={eSrc} onChange={(e) => setESrc(e.target.value)}>
            <option value="">source…</option>
            {nodes.map((n) => (
              <option key={String(n.node_id)} value={String(n.node_id)}>
                {trunc(String(n.label ?? n.node_id), 28)}
              </option>
            ))}
          </select>
          <select className="select" value={eDst} onChange={(e) => setEDst(e.target.value)}>
            <option value="">target…</option>
            {nodes.map((n) => (
              <option key={String(n.node_id)} value={String(n.node_id)}>
                {trunc(String(n.label ?? n.node_id), 28)}
              </option>
            ))}
          </select>
        </div>
        <Field label="label (optional)">
          <input className="input" value={eLabel} onChange={(e) => setELabel(e.target.value)} />
        </Field>
        <div className="dag-actions">
          <button className="btn outline sm" disabled={ctx.busy || !eSrc || !eDst || eSrc === eDst} onClick={addEdge}>
            Add edge
          </button>
        </div>
      </div>
    </details>
  );
}

/* ------------------------------------------------------------- gates */

function GateRow({ gate, kind, ctx }: { gate: Json; kind?: 'warn'; ctx: FormCtx }) {
  const [open, setOpen] = useState(false);
  const [rationale, setRationale] = useState('');
  const waived = Boolean(gate.waiver?.rationale);

  function waive() {
    if (!rationale.trim()) return;
    ctx.onSave(
      [
        {
          op: 'waive_gate',
          waiver: {
            gate_code: gate.code,
            target_type: gate.target_type,
            target_id: gate.target_id,
            user_id: 'user',
            session_id: 'ui',
            rationale: rationale.trim(),
          },
        },
      ],
      rationale.trim(),
      'Gate waived',
    );
    setOpen(false);
  }

  return (
    <div className="dag-row">
      <Badge text={`${String(gate.target_type)}:${shortId(gate.target_id)}`} kind={kind} /> {String(gate.code)}
      <span className="dim"> — {String(gate.detail ?? '')}</span>
      {waived ? (
        <span className="dim"> (waived: {String(gate.waiver.rationale)})</span>
      ) : (
        <>
          {' '}
          <button className="btn ghost sm" onClick={() => setOpen(!open)}>
            waive
          </button>
          {open && (
            <span className="dag-waive-row">
              <input
                className="input"
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="waiver rationale (required)"
              />
              <button className="btn yellow sm" disabled={ctx.busy || !rationale.trim()} onClick={waive}>
                Waive
              </button>
            </span>
          )}
        </>
      )}
    </div>
  );
}

function GateList({ title, gates, kind, ctx }: { title: string; gates: Json[]; kind?: 'warn'; ctx: FormCtx }) {
  if (!gates.length) return null;
  return (
    <div className="dag-section">
      <div className="dag-title">{title}</div>
      {gates.map((g, i) => (
        <GateRow key={`${String(g.code)}:${String(g.target_id)}:${i}`} gate={g} kind={kind} ctx={ctx} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- reviews */

function ReviewRow({ review }: { review: Json }) {
  return (
    <div className="dag-row">
      <Badge
        text={review.is_success ? 'ok' : 'failed'}
        kind={review.is_success ? 'ok' : 'warn'}
      />{' '}
      {String(review.tool_name ?? '?')}
      <span className="dim">
        {' '}
        by {String(review.caller_legacy_id || review.caller_role_id || '?')}
        {review.compute_job_id ? ` · job ${String(review.compute_job_id)}` : ''}
        {review.arguments_digest ? ` · ${shortId(review.arguments_digest)}` : ''}
        {review.result_summary ? ` — ${trunc(String(review.result_summary), 80)}` : ''}
        {review.created_at ? ` · ${String(review.created_at).slice(0, 19)}` : ''}
        {review.state && review.state !== 'pending' ? ` · ${String(review.state)}` : ''}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------- panel */

export default function DagPanel({ project, onError, onToast }: {
  project: Project;
  onError: (e: unknown) => void;
  onToast: (kind: 'error' | 'ok' | 'info', text: string) => void;
}) {
  const [data, setData] = useState<DagData | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [replanNote, setReplanNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [delivery, report, history, projection, reviews, draft] = await Promise.all([
      api.dagDelivery(project.id),
      api.dagReport(project.id),
      api.dagHistory(project.id),
      api.dagProjection(project.id),
      api.dagReviews(project.id),
      api.dagDraft(project.id),
    ]);
    setData({
      mode: delivery.mode,
      delivery: delivery.graph,
      report,
      history,
      projection,
      reviews,
      draft,
    });
  }, [project.id]);

  useEffect(() => {
    load().catch(onError);
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  async function applyOps(operations: unknown[], rationale: string, okMsg: string) {
    setBusy(true);
    try {
      // Pin the freshest revisions to avoid stale_revision rejections.
      const projection = await api.dagProjection(project.id);
      const base = (projection?.revisions as Record<string, number> | undefined) ?? {};
      const result = await api.dagMutations(project.id, operations, base, rationale);
      if (result.accepted === false) {
        throw new Error(`rejected: ${String(result.rejection_code ?? '')} ${String(result.rejection_reason ?? '')}`);
      }
      onToast('ok', okMsg);
      await load();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function replan() {
    setBusy(true);
    try {
      const result = await api.dagReplan(project.id, replanNote.trim());
      // replan is asynchronous now: the request is persisted and queued for
      // the Supervisor; the verdict arrives later via the Coordinator.
      onToast(result.queued ? 'ok' : 'info', String(result.summary ?? 'replan queued'));
      setReplanNote('');
      await load();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="empty-hint">Loading DAG…</div>;
  if (data.mode === 'standard') {
    return <div className="empty-hint">standard mode — pick dag_record or dag_guided in the agent bar to enable the DAG.</div>;
  }

  const revisions = (data.projection?.revisions ?? {}) as Record<string, number>;
  const gaps = (data.projection?.delivery_gaps ?? []) as Json[];
  const report = data.report;
  const pending = (data.reviews?.pending ?? []) as Json[];
  const recent = (data.reviews?.recent ?? []) as Json[];
  const draft = data.draft?.draft as Json | null | undefined;
  const mechanismAccepted = data.draft?.mechanism_accepted !== false;
  const ctx: FormCtx = { busy, onSave: (ops, rationale, okMsg) => void applyOps(ops, rationale, okMsg) };

  const graph = data.delivery;
  const selNode =
    sel?.kind === 'node' ? ((graph?.nodes ?? []) as Json[]).find((n) => String(n.node_id) === sel.id) : undefined;
  const selEdge =
    sel?.kind === 'edge' ? ((graph?.edges ?? []) as Json[]).find((e) => String(e.edge_id) === sel.id) : undefined;
  const nodeLabels = new Map(((graph?.nodes ?? []) as Json[]).map((n) => [String(n.node_id), String(n.label ?? n.node_id)]));

  return (
    <div>
      <div className="dag-head">
        <Badge text={data.mode} kind={data.mode === 'dag_guided' ? 'ok' : undefined} />
        <Badge text={`delivery r${revisions.delivery ?? '-'}`} />
        {report && (
          <Badge text={report.complete ? 'delivery complete' : 'delivery incomplete'} kind={report.complete ? 'ok' : 'warn'} />
        )}
        {pending.length > 0 && <Badge text={`${pending.length} pending review${pending.length > 1 ? 's' : ''}`} kind="warn" />}
        <button className="btn ghost sm" onClick={() => load().catch(onError)}>refresh</button>
      </div>

      {!mechanismAccepted && (
        <div className="dag-section">
          <div className="dag-title">mechanism not accepted</div>
          <div className="dag-row">
            <span className="dim">
              The compute gate is closed until a mechanism draft is accepted
              {data.mode === 'dag_guided' ? ' by the Supervisor' : ''}.
            </span>
          </div>
          {draft && draft.state === 'open' && (
            <div className="dag-row">
              <Badge text={`draft ${shortId(draft.draft_id)}`} />{' '}
              <span className="dim">{trunc(String(draft.rationale ?? ''), 120)}</span>
            </div>
          )}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="dag-section">
          <div className="dag-title">coverage gaps</div>
          {gaps.map((g, i) => (
            <div key={`g${i}`} className="dag-row"><span className="dim">gap </span>{String(g.label ?? g.detail ?? '')}</div>
          ))}
        </div>
      )}

      {graph && (
        <div className="dag-section">
          <div className="dag-title">
            delivery graph <Badge text={`r${graph.revision ?? revisions.delivery ?? '-'}`} />
          </div>
          <GraphView graph={graph} sel={sel} onSelect={setSel} />
          <AddForms nodes={(graph.nodes ?? []) as Json[]} ctx={ctx} />
        </div>
      )}

      {sel && (selNode || selEdge) && (
        <div className="dag-section">
          {selNode && (
            <NodeEditForm
              key={`n:${sel.id}:${revisions.delivery ?? 0}`}
              node={selNode}
              ctx={ctx}
            />
          )}
          {selEdge && (
            <EdgeEditForm
              key={`e:${sel.id}:${revisions.delivery ?? 0}`}
              edge={selEdge}
              nodeLabels={nodeLabels}
              ctx={ctx}
            />
          )}
        </div>
      )}

      {(pending.length > 0 || recent.length > 0) && (
        <div className="dag-section">
          <div className="dag-title">call reviews (Supervisor adjudicates)</div>
          {pending.map((r) => (
            <ReviewRow key={String(r.review_id)} review={r} />
          ))}
          {recent.length > 0 && <div className="dag-title" style={{ marginTop: 6 }}>recent history</div>}
          {recent.map((r) => (
            <ReviewRow key={String(r.review_id)} review={r} />
          ))}
        </div>
      )}

      {report && (
        <>
          <GateList title="unresolved gates" gates={(report.unresolved ?? []) as Json[]} kind="warn" ctx={ctx} />
          <GateList title="inconclusive gates" gates={(report.inconclusive ?? []) as Json[]} kind="warn" ctx={ctx} />
          <GateList title="waived gates" gates={(report.waived ?? []) as Json[]} ctx={ctx} />
        </>
      )}

      {data.history.length > 0 && (
        <div className="dag-section">
          <div className="dag-title">mutation history</div>
          {data.history.slice(0, 10).map((m) => (
            <div key={String(m.mutation_id)} className="dag-row">
              <span className={m.accepted ? 'dag-ok' : 'dag-fail'}>{m.accepted ? '✓' : '✗'}</span>{' '}
              {String(m.actor ?? '?')}
              <span className="dim">
                {m.rationale ? ` — ${String(m.rationale)}` : ''}
                {m.rejection_code ? ` (${String(m.rejection_code)})` : ''}
                {m.created_at ? ` · ${String(m.created_at).slice(0, 19)}` : ''}
              </span>
            </div>
          ))}
        </div>
      )}

      {data.mode === 'dag_guided' && (
        <div className="dag-section">
          <div className="dag-title">supervisor replan</div>
          <input
            className="input"
            style={{ width: '100%' }}
            value={replanNote}
            onChange={(e) => setReplanNote(e.target.value)}
            placeholder="note for the supervisor (optional)"
          />
          <button className="btn outline sm" style={{ marginTop: 6 }} disabled={busy} onClick={replan}>
            {busy ? 'Requesting…' : 'Request replan'}
          </button>
        </div>
      )}
    </div>
  );
}
