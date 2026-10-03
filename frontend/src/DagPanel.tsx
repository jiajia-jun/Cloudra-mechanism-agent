import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import dagre from 'dagre';
import { api } from './api';
import type { Project } from './types';
import { hasSaddleEvidence } from './tsEvidence';
import { Molecule3DViewer } from './Molecule3DViewer';

/* Structured DAG panel:
   - Left Column:
     - Top-left: RDKit 2D molecular structure depiction frame
     - Bottom-left: Draggable slider & categorized evidence shelf for the selected node/step
   - Right Column:
     - Top-right: Reaction DAG topology graph + overall physical consistency & completion stats
     - Right Main: 3D Molecular Structure Visualizer (Cartesian ball-and-stick, vibration animation)
   - Bottom Drawer: Collapsible graph mutation forms & audit reviews
*/

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

/* ------------------------------------------------------------- colors */

function evidenceColor(level: unknown): string {
  const l = String(level ?? '');
  if (!l || l === 'proposed') return 'var(--border-strong)';
  if (l === 'rejected' || l === 'inconclusive') return 'var(--yellow-soft)';
  return 'var(--green-soft)';
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
  g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 42, marginx: 12, marginy: 12 });
  g.setDefaultEdgeLabel(() => ({}));
  const nodes: Json[] = graph.nodes ?? [];
  const edges: Json[] = graph.edges ?? [];
  for (const n of nodes) {
    const label = String(n.label ?? n.node_id);
    const hasSmiles = Boolean(n.smiles && String(n.smiles).trim());
    const h = hasSmiles ? 74 : NODE_H;
    const w = Math.max(hasSmiles ? 110 : 96, Math.min(180, label.length * 7 + 20));
    g.setNode(String(n.node_id), { width: w, height: h });
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
    const hasSmiles = Boolean(n.smiles && String(n.smiles).trim());
    const defaultH = hasSmiles ? 74 : NODE_H;
    return { id, x: p?.x ?? 0, y: p?.y ?? 0, w: p?.width ?? 110, h: p?.height ?? defaultH, data: n };
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
    const pts = (g.edge({ v: s, w: t, name: id }) as { points?: Array<{ x: number; y: number }> })?.points;
    if (pts && pts.length > 0) {
      le.push({ id, points: pts, data: e });
      continue;
    }
    le.push({ id, points: [{ x: src.x, y: src.y }, { x: dst.x, y: dst.y }], data: e });
  }
  const dims = g.graph();
  return { nodes: ln, edges: le, width: Math.max(dims?.width ?? 0, 180), height: Math.max(dims?.height ?? 0, 70) };
}

/* ------------------------------------------------------------- svg view */

function GraphView({ graph, sel, onSelect }: {
  graph: Json;
  sel: Sel;
  onSelect: (s: Sel) => void;
}) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  if (layout.nodes.length === 0) return <div className="empty-hint">暂无反应节点</div>;
  const isSel = (k: 'node' | 'edge', id: string) => sel?.kind === k && sel.id === id;
  return (
    <div className="dag-canvas-compact">
      <svg width={layout.width} height={layout.height} onClick={() => onSelect(null)}>
        <defs>
          <marker id="dag-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 z" fill="var(--fg-faint)" />
          </marker>
        </defs>
        {layout.edges.map((e) => {
          const pts = e.points.map((p) => `${p.x},${p.y}`).join(' ');
          const mid = e.points[Math.floor((e.points.length - 1) / 2)];
          const selected = isSel('edge', e.id);
          const stroke = selected ? 'var(--green)' : evidenceColor(e.data.evidence_level);
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
                  strokeWidth: selected ? 2.5 : 1.2,
                  strokeDasharray: e.data.evidence_vetoed ? '5 3' : undefined,
                }}
              />
              {e.data.label ? (
                <text className="dag-edge-label" x={mid.x} y={mid.y - 6} textAnchor="middle">
                  {trunc(String(e.data.label), 20)}
                </text>
              ) : null}
            </g>
          );
        })}
        {layout.nodes.map((n) => {
          const selected = isSel('node', n.id);
          const stroke = selected ? 'var(--green)' : evidenceColor(n.data.evidence_level);
          const maxChars = Math.floor((n.w - 12) / 6.5);
          const smiles = String(n.data.smiles ?? '').trim();
          const hasSmiles = Boolean(smiles);
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
                className="dag-node-rect"
                width={n.w}
                height={n.h}
                rx={4}
                style={{
                  fill: selected ? 'var(--bg-layer-2)' : 'var(--bg-panel)',
                  stroke,
                  strokeWidth: selected ? 2.2 : 1.1,
                  strokeDasharray: n.data.evidence_vetoed ? '5 3' : undefined,
                }}
              />
              <text className="dag-node-label" x={n.w / 2} y={hasSmiles ? 14 : n.h / 2 + 4} textAnchor="middle">
                {trunc(String(n.data.label ?? n.id), maxChars)}
              </text>
              {hasSmiles && (
                <image
                  href={api.chemRenderSmilesUrl(smiles, Math.round(n.w - 12), 40, 'dark')}
                  x={6}
                  y={18}
                  width={n.w - 12}
                  height={40}
                  preserveAspectRatio="xMidYMid meet"
                  style={{
                    pointerEvents: 'none',
                    opacity: selected ? 1 : 0.85,
                  }}
                />
              )}
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
      <div className="dag-title">编辑反应节点 · {String(node.node_id)}</div>
      <StageChips stages={(node.stages as Json[] | undefined) ?? []} />
      <Field label="名称标签 (Label)">
        <input className="input sm" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Field label="角色 (Role)">
        <select className="select sm" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">(none)</option>
          {DEL_ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </Field>
      <Field label="SMILES 结构式">
        <input className="input sm" value={smiles} onChange={(e) => setSmiles(e.target.value)} placeholder="(none)" />
      </Field>
      <Field label="化学依据 (Reason)">
        <input className="input sm" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="变更说明 (Rationale)">
        <input className="input sm" value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="记录至突变审计日志（可选）" />
      </Field>
      <div className="dag-actions">
        <button className="btn primary sm" disabled={ctx.busy || !label.trim()} onClick={save}>
          保存更改
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
      <div className="dag-title">编辑过渡态反应步 · {String(edge.edge_id)}</div>
      <div className="dag-meta">{src} → {dst}</div>
      <Field label="步骤名称 (Label)">
        <input className="input sm" value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Field label="反应依据 (Reason)">
        <input className="input sm" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field label="删除理由 (Rationale)">
        <input className="input sm" value={rationale} onChange={(e) => setRationale(e.target.value)} />
      </Field>
      <div className="dag-actions">
        <button className="btn primary sm" disabled={ctx.busy} onClick={save}>
          保存更改
        </button>
        <button className="btn yellow sm" disabled={ctx.busy || !rationale.trim()} onClick={remove}>
          移除此步
        </button>
      </div>
    </div>
  );
}

function AddForms({ nodes, ctx }: { nodes: Json[]; ctx: FormCtx }) {
  const [nLabel, setNLabel] = useState('');
  const [nRole, setNRole] = useState('');
  const [nSmiles, setNSmiles] = useState('');
  const [eSrc, setESrc] = useState('');
  const [eDst, setEDst] = useState('');
  const [eLabel, setELabel] = useState('');

  function addNode() {
    if (!nLabel.trim()) return;
    const node: Json = { node_id: `sp_${Date.now()}`, node_type: 'species', name: nLabel.trim(), label: nLabel.trim() };
    if (nRole) node.role = nRole;
    if (nSmiles.trim()) node.smiles = nSmiles.trim();
    ctx.onSave([{ op: 'add_node', graph: 'delivery', node }], 'User added node', 'Node added');
    setNLabel('');
    setNSmiles('');
  }

  function addEdge() {
    if (!eSrc || !eDst || eSrc === eDst) return;
    const edge: Json = {
      edge_id: `step_${Date.now()}`,
      edge_type: 'elementary_step',
      source_node_id: eSrc,
      target_node_id: eDst,
      label: eLabel.trim() || undefined,
    };
    ctx.onSave([{ op: 'add_edge', graph: 'delivery', edge }], 'User added step', 'Step added');
    setELabel('');
  }

  return (
    <div className="dag-add-grid">
      <div className="dag-form-card">
        <div className="form-card-title">+ 新增反应基态/中间体节点</div>
        <Field label="名称标签">
          <input className="input sm" value={nLabel} onChange={(e) => setNLabel(e.target.value)} placeholder="如 Int-3" />
        </Field>
        <Field label="SMILES 结构式">
          <input className="input sm" value={nSmiles} onChange={(e) => setNSmiles(e.target.value)} placeholder="如 CC(=O)O" />
        </Field>
        <Field label="角色">
          <select className="select sm" value={nRole} onChange={(e) => setNRole(e.target.value)}>
            <option value="">(选择角色)</option>
            {DEL_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </Field>
        <button className="btn outline sm" disabled={ctx.busy || !nLabel.trim()} onClick={addNode}>
          添加节点
        </button>
      </div>

      <div className="dag-form-card">
        <div className="form-card-title">+ 新增反应过渡态步 (Elementary Step)</div>
        <Field label="起始物/反应物">
          <select className="select sm" value={eSrc} onChange={(e) => setESrc(e.target.value)}>
            <option value="">(选择起点)</option>
            {nodes.map((n) => (
              <option key={String(n.node_id)} value={String(n.node_id)}>{String(n.label ?? n.node_id)}</option>
            ))}
          </select>
        </Field>
        <Field label="目标物/产物">
          <select className="select sm" value={eDst} onChange={(e) => setEDst(e.target.value)}>
            <option value="">(选择终点)</option>
            {nodes.map((n) => (
              <option key={String(n.node_id)} value={String(n.node_id)}>{String(n.label ?? n.node_id)}</option>
            ))}
          </select>
        </Field>
        <Field label="步骤/过渡态标签">
          <input className="input sm" value={eLabel} onChange={(e) => setELabel(e.target.value)} placeholder="如 TS-1" />
        </Field>
        <button className="btn outline sm" disabled={ctx.busy || !eSrc || !eDst || eSrc === eDst} onClick={addEdge}>
          添加反应步
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- gates */

function GateRow({ gate, kind, ctx }: { gate: Json; kind?: 'warn'; ctx: FormCtx }) {
  const [open, setOpen] = useState(false);
  const [rationale, setRationale] = useState('');
  const waived = Boolean(gate.waiver);

  function waive() {
    if (!rationale.trim()) return;
    ctx.onSave(
      [{ op: 'waive_gate', target_type: gate.target_type, target_id: gate.target_id, code: gate.code, rationale: rationale.trim() }],
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
          <button className="btn ghost sm" onClick={() => setOpen(!open)}>waive</button>
          {open && (
            <span className="dag-waive-row">
              <input
                className="input sm"
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
      </span>
    </div>
  );
}

/* ------------------------------------------------------------- main component */

export default function DagPanel({
  project,
  onError,
  onToast,
}: {
  project: Project;
  onError: (e: unknown) => void;
  onToast: (kind: 'error' | 'ok' | 'info', text: string) => void;
}) {
  const [data, setData] = useState<DagData | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [replanNote, setReplanNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [evidenceCategory, setEvidenceCategory] = useState<'all' | 'geometry' | 'frequency' | 'irc' | 'thermo'>('all');
  const [stageSliderIdx, setStageSliderIdx] = useState<number>(0);
  const [showAdminDrawer, setShowAdminDrawer] = useState<boolean>(false);

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

  // Default selection to first node if none selected
  useEffect(() => {
    if (!sel && data?.delivery?.nodes && data.delivery.nodes.length > 0) {
      setSel({ kind: 'node', id: String(data.delivery.nodes[0].node_id) });
    }
  }, [data?.delivery?.nodes, sel]);

  async function applyOps(operations: unknown[], rationale: string, okMsg: string) {
    setBusy(true);
    try {
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
      onToast(result.queued ? 'ok' : 'info', String(result.summary ?? 'replan queued'));
      setReplanNote('');
      await load();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  const graph = data?.delivery;
  const nodes = (graph?.nodes ?? []) as Json[];
  const edges = (graph?.edges ?? []) as Json[];
  const revisions = (data?.projection?.revisions ?? {}) as Record<string, number>;
  const report = data?.report;
  const pending = (data?.reviews?.pending ?? []) as Json[];
  const recent = (data?.reviews?.recent ?? []) as Json[];
  const draft = data?.draft?.draft as Json | null | undefined;
  const mechanismAccepted = data?.draft?.mechanism_accepted !== false;
  const gaps = (data?.projection?.delivery_gaps ?? []) as Json[];
  const ctx: FormCtx = { busy, onSave: (ops, rationale, okMsg) => void applyOps(ops, rationale, okMsg) };

  const selNode = sel?.kind === 'node' ? nodes.find((n) => String(n.node_id) === sel.id) : undefined;
  const selEdge = sel?.kind === 'edge' ? edges.find((e) => String(e.edge_id) === sel.id) : undefined;
  const nodeLabels = new Map(nodes.map((n) => [String(n.node_id), String(n.label ?? n.node_id)]));

  // Determine current active item's details for 2D & 3D view
  const currentItem = useMemo(() => {
    if (selNode) {
      return {
        id: String(selNode.node_id),
        label: String(selNode.label ?? selNode.node_id),
        smiles: String(selNode.smiles ?? '').trim(),
        role: String(selNode.role ?? 'intermediate'),
        isTS: false,
        saddleEvidenceSupported: false,
        evidenceLevel: String(selNode.evidence_level ?? 'proposed'),
        stages: (selNode.stages as Json[] | undefined) ?? [],
        xyz: String(selNode.xyz ?? selNode.metadata?.xyz ?? ''),
      };
    }
    if (selEdge) {
      const src = nodeLabels.get(String(selEdge.source_node_id)) ?? String(selEdge.source_node_id);
      const dst = nodeLabels.get(String(selEdge.target_node_id)) ?? String(selEdge.target_node_id);
      return {
        id: String(selEdge.edge_id),
        label: `${String(selEdge.label ?? selEdge.edge_id)} (${src} → ${dst})`,
        smiles: String(selEdge.smiles ?? '').trim(),
        role: 'transition_state',
        isTS: true,
        saddleEvidenceSupported: hasSaddleEvidence(selEdge),
        evidenceLevel: String(selEdge.evidence_level ?? 'proposed'),
        stages: (selEdge.stages as Json[] | undefined) ?? [],
        xyz: String(selEdge.xyz ?? selEdge.metadata?.xyz ?? ''),
        barrier: selEdge.barrier,
      };
    }
    return null;
  }, [selNode, selEdge, nodeLabels]);

  // Filter stages based on category
  const filteredStages = useMemo(() => {
    if (!currentItem) return [];
    const list = currentItem.stages;
    if (evidenceCategory === 'all') return list;
    if (evidenceCategory === 'geometry') return list.filter((s) => ['geometry', 'ts_guess', 'ts_opt'].includes(String(s.kind)));
    if (evidenceCategory === 'frequency') return list.filter((s) => String(s.kind) === 'frequency');
    if (evidenceCategory === 'irc') return list.filter((s) => ['short_irc', 'endpoint_a', 'endpoint_b', 'direction'].includes(String(s.kind)));
    if (evidenceCategory === 'thermo') return list.filter((s) => ['single_point', 'thermochemistry'].includes(String(s.kind)));
    return list;
  }, [currentItem, evidenceCategory]);

  const activeStage = filteredStages[stageSliderIdx] || filteredStages[0] || null;

  // Completion & physical consistency stats
  const completionStats = useMemo(() => {
    const verifiedMinima = nodes.filter((n) => {
      const st = (n.stages as Json[] | undefined) ?? [];
      return st.some((s) => s.kind === 'frequency' && s.status === 'supported');
    }).length;

    const verifiedTs = edges.filter(hasSaddleEvidence).length;

    const verifiedIrc = edges.filter((e) => {
      const st = (e.stages as Json[] | undefined) ?? [];
      return st.some((s) => s.kind === 'short_irc' && s.status === 'supported');
    }).length;

    const minimaRate = nodes.length > 0 ? Math.round((verifiedMinima / nodes.length) * 100) : 0;
    const tsRate = edges.length > 0 ? Math.round((verifiedTs / edges.length) * 100) : 0;
    const ircRate = edges.length > 0 ? Math.round((verifiedIrc / edges.length) * 100) : 0;
    const pathClosure = nodes.length >= 2 && edges.length >= nodes.length - 1;

    return {
      nodesCount: nodes.length,
      edgesCount: edges.length,
      verifiedMinima,
      verifiedTs,
      verifiedIrc,
      minimaRate,
      tsRate,
      ircRate,
      pathClosure,
    };
  }, [nodes, edges]);

  return (
    <div className="dag-workspace-root">
      {/* Top Bar */}
      <div className="dag-topbar">
        <div className="dag-topbar-left">
          <span className="dag-main-title">反应机理图与证据交付看板</span>
          <Badge text={data?.mode ?? 'standard'} kind={data?.mode === 'dag_guided' ? 'ok' : undefined} />
          <Badge text={`delivery r${revisions.delivery ?? '-'}`} />
          {report && (
            <Badge text={report.complete ? '交付完备' : '交付中'} kind={report.complete ? 'ok' : 'warn'} />
          )}
          {pending.length > 0 && <Badge text={`${pending.length} 项审核待裁决`} kind="warn" />}
        </div>

        <div className="dag-topbar-right">
          <button
            type="button"
            className="btn outline sm"
            onClick={() => setShowAdminDrawer(!showAdminDrawer)}
          >
            {showAdminDrawer ? '收起图操作' : '图操作与审计'}
          </button>
          <button type="button" className="btn ghost sm" onClick={() => load().catch(onError)} disabled={busy}>
            {busy ? '刷新中…' : '刷新'}
          </button>
        </div>
      </div>

      {data?.mode === 'standard' && (
        <div className="dag-standard-notice">
          <span>
            ℹ 当前项目处于标准对话模式。你可以在上方项目配置中开启 DAG 引导，也可以在此自由交互设计反应拓扑与三维立体结构。
          </span>
        </div>
      )}

      {/* Main 2-Column Split: Left Focus & 3D Viewer, Right Topology & Overview */}
      <div className="dag-grid-container">
        {/* Left Column: 3D Visualizer (Top) + Compact Evidence Shelf (Bottom) */}
        <div className="dag-left-focus-col">
          {/* Top-left: 3D Molecular Structure Visualizer */}
          <div className="dag-card dag-3d-visualizer-card">
            <Molecule3DViewer
              smiles={currentItem?.smiles}
              xyz={currentItem?.xyz}
              title={currentItem?.label}
              isTransitionState={currentItem?.isTS}
              saddleEvidenceSupported={currentItem?.saddleEvidenceSupported}
            />
          </div>

          {/* Bottom-left: Compact Evidence Shelf & Slider ("矮胖点，带滚动条") */}
          <div className="dag-card dag-evidence-shelf-card compact-shelf">
            <div className="dag-card-header compact">
              <div className="shelf-header-left">
                <span className="mono-subhead">绑定交付物与证据分类</span>
                <span className="badge sm">
                  {filteredStages.filter((s) => s.status === 'supported').length} / {filteredStages.length} 确证
                </span>
              </div>
              {currentItem?.role && (
                <span className={`badge sm role-${currentItem.role}`}>
                  {currentItem.role === 'transition_state' ? '过渡态 (TS)' : currentItem.role.toUpperCase()}
                </span>
              )}
            </div>

            <div className="shelf-scroll-body">
              {/* Category Filter Pills */}
              <div className="shelf-category-pills">
                <button
                  type="button"
                  className={`pill-btn ${evidenceCategory === 'all' ? 'active' : ''}`}
                  onClick={() => {
                    setEvidenceCategory('all');
                    setStageSliderIdx(0);
                  }}
                >
                  全部
                </button>
                <button
                  type="button"
                  className={`pill-btn ${evidenceCategory === 'geometry' ? 'active' : ''}`}
                  onClick={() => {
                    setEvidenceCategory('geometry');
                    setStageSliderIdx(0);
                  }}
                >
                  几何优化
                </button>
                <button
                  type="button"
                  className={`pill-btn ${evidenceCategory === 'frequency' ? 'active' : ''}`}
                  onClick={() => {
                    setEvidenceCategory('frequency');
                    setStageSliderIdx(0);
                  }}
                >
                  频率确证
                </button>
                <button
                  type="button"
                  className={`pill-btn ${evidenceCategory === 'irc' ? 'active' : ''}`}
                  onClick={() => {
                    setEvidenceCategory('irc');
                    setStageSliderIdx(0);
                  }}
                >
                  短 IRC 证明
                </button>
                <button
                  type="button"
                  className={`pill-btn ${evidenceCategory === 'thermo' ? 'active' : ''}`}
                  onClick={() => {
                    setEvidenceCategory('thermo');
                    setStageSliderIdx(0);
                  }}
                >
                  热力学能垒
                </button>
              </div>

              {/* Evidence Slider Scrubber */}
              {filteredStages.length > 1 && (
                <div className="shelf-slider-control">
                  <input
                    type="range"
                    min={0}
                    max={filteredStages.length - 1}
                    value={stageSliderIdx}
                    onChange={(e) => setStageSliderIdx(parseInt(e.target.value, 10))}
                    className="shelf-slider-range"
                  />
                  <div className="shelf-slider-labels">
                    {filteredStages.map((s, idx) => (
                      <span
                        key={idx}
                        className={`slider-tick ${idx === stageSliderIdx ? 'active' : ''}`}
                        onClick={() => setStageSliderIdx(idx)}
                      >
                        {String(s.kind)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Active Evidence Item Card */}
              <div className="shelf-active-stage-view">
                {activeStage ? (
                  <div className="evidence-stage-card compact">
                    <div className="stage-card-head">
                      <div className="stage-kind-title">
                        <span className="stage-kind-name">{String(activeStage.kind)}</span>
                        <span className={`badge sm ${stageKind(activeStage.status) ?? 'neutral'}`}>
                          {String(activeStage.status).toUpperCase()}
                        </span>
                      </div>
                      <span className="stage-required-tag">
                        {activeStage.required ? '必需核心证据' : '建议证据'}
                      </span>
                    </div>

                    <div className="stage-card-body">
                      {activeStage.reason && (
                        <div className="stage-reason-box">
                          <span className="reason-label">确证依据:</span>
                          <span className="reason-text">{String(activeStage.reason)}</span>
                        </div>
                      )}

                      {activeStage.ref && (
                        <div className="stage-ref-box">
                          <span className="ref-type-tag">{String(activeStage.ref.ref_type)}:</span>
                          <span className="ref-id-tag mono">{String(activeStage.ref.ref_id)}</span>
                          {activeStage.ref.ref_type === 'artifact' && (
                            <a
                              href={api.artifactDownloadUrl(project.id, String(activeStage.ref.ref_id))}
                              download
                              className="btn primary sm"
                            >
                              下载产物
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="empty-hint" style={{ padding: '8px 0' }}>
                    {currentItem ? '当前分类下暂无绑定物理证据' : '请先在右侧选择分子或反应过渡态'}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: DAG Reaction Graph (Top Half) + Mechanism Overview (Bottom Half) */}
        <div className="dag-right-col">
          {/* Top Half: Reaction DAG Topology Graph */}
          <div className="dag-card dag-topology-card full-half">
            <div className="dag-card-header">
              <span className="mono-subhead">反应网络有向无环图 (DAG 拓扑)</span>
              <div className="topology-header-actions">
                <span className="badge sm">{nodes.length} 节点 · {edges.length} 反应步</span>
                <span className="dag-zoom-hint">点击节点或过渡态边查看 3D 构象</span>
              </div>
            </div>
            <div className="topology-viewport">
              {graph ? (
                <GraphView graph={graph} sel={sel} onSelect={setSel} />
              ) : (
                <div className="empty-hint">暂无图数据</div>
              )}
            </div>
          </div>

          {/* Bottom Half: Overall Physical Consistency & Delivery Overview */}
          <div className="dag-card dag-stats-card full-half">
            <div className="dag-card-header">
              <div className="overview-header-left">
                <span className="mono-subhead">反应机理自洽性与交付总览</span>
                <span className={`badge sm ${completionStats.pathClosure ? 'ok' : 'neutral'}`}>
                  {completionStats.pathClosure ? '路径连通闭合' : '拓扑开放'}
                </span>
                {report && (
                  <span className={`badge sm ${report.complete ? 'ok' : 'warn'}`}>
                    {report.complete ? '物理交付已完备' : '探索与计算中'}
                  </span>
                )}
              </div>
              <span className="badge sm mono">delivery r{revisions.delivery ?? 0}</span>
            </div>

            <div className="dag-overview-body">
              {/* Three Verification Rate Progress Bars */}
              <div className="overview-metrics-grid">
                <div className="stat-metric-row">
                  <span className="metric-label">极小值 0 虚频确证率</span>
                  <div className="metric-bar-wrap">
                    <div className="metric-bar-fill green" style={{ width: `${completionStats.minimaRate}%` }} />
                  </div>
                  <span className="metric-val mono">{completionStats.minimaRate}%</span>
                </div>

                <div className="stat-metric-row">
                  <span className="metric-label">过渡态 1 虚频鞍点确证率</span>
                  <div className="metric-bar-wrap">
                    <div className="metric-bar-fill cyan" style={{ width: `${completionStats.tsRate}%` }} />
                  </div>
                  <span className="metric-val mono">{completionStats.tsRate}%</span>
                </div>

                <div className="stat-metric-row">
                  <span className="metric-label">短 IRC 双向倒向覆盖率</span>
                  <div className="metric-bar-wrap">
                    <div className="metric-bar-fill purple" style={{ width: `${completionStats.ircRate}%` }} />
                  </div>
                  <span className="metric-val mono">{completionStats.ircRate}%</span>
                </div>
              </div>

              {/* Status Summary Pill Cards */}
              <div className="overview-summary-cards">
                <div className="summary-pill-card">
                  <span className="pill-num green">{completionStats.nodesCount}</span>
                  <span className="pill-title">驻点 (Minima)</span>
                  <span className="pill-desc">{completionStats.verifiedMinima} 个已通过 0 虚频</span>
                </div>
                <div className="summary-pill-card">
                  <span className="pill-num cyan">{completionStats.edgesCount}</span>
                  <span className="pill-title">过渡态 (TS)</span>
                  <span className="pill-desc">{completionStats.verifiedTs} 个已鞍点确证</span>
                </div>
                <div className="summary-pill-card">
                  <span className="pill-num purple">{completionStats.verifiedIrc}</span>
                  <span className="pill-title">IRC 证明</span>
                  <span className="pill-desc">{completionStats.ircRate}% 双向区间吻合</span>
                </div>
                <div className="summary-pill-card">
                  <span className="pill-num amber">{pending.length}</span>
                  <span className="pill-title">待审查项</span>
                  <span className="pill-desc">导师智能体裁判队列</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Collapsible Admin Drawer: Graph Mutations & Reviews */}
      {showAdminDrawer && (
        <div className="dag-admin-drawer">
          <div className="admin-drawer-head">
            <span className="admin-drawer-title">反应图结构变更、门禁豁免与历史审计</span>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setShowAdminDrawer(false)}
            >
              收起
            </button>
          </div>

          <div className="admin-drawer-content">
            {sel && (selNode || selEdge) && (
              <div className="admin-subblock">
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

            {!mechanismAccepted && (
              <div className="admin-subblock">
                <div className="dag-title">机理草案未获批</div>
                <div className="dag-row">
                  <span className="dim">计算门禁处于关闭状态，直至导师智能体审核通过机理草案。</span>
                  {draft && (
                    <span className="dim"> 草案: {String(draft.rationale ?? draft.draft_id ?? '')}</span>
                  )}
                </div>
              </div>
            )}

            {gaps.length > 0 && (
              <div className="admin-subblock">
                <div className="dag-title">覆盖性缺口 (Coverage Gaps)</div>
                {gaps.map((g, i) => (
                  <div key={i} className="dag-row"><span className="dim">缺口: </span>{String(g.label ?? g.detail ?? '')}</div>
                ))}
              </div>
            )}

            {(pending.length > 0 || recent.length > 0) && (
              <div className="admin-subblock">
                <div className="dag-title">工具调用审查队列 (Call Reviews)</div>
                {pending.map((r, i) => (
                  <ReviewRow key={String(r.review_id ?? i)} review={r} />
                ))}
                {recent.slice(0, 5).map((r, i) => (
                  <ReviewRow key={String(r.review_id ?? i)} review={r} />
                ))}
              </div>
            )}

            <div className="admin-subblock">
              <AddForms nodes={nodes} ctx={ctx} />
            </div>

            {report && (
              <div className="admin-subblock">
                <GateList title="未决门禁 (Unresolved Gates)" gates={(report.unresolved ?? []) as Json[]} kind="warn" ctx={ctx} />
                <GateList title="不确定门禁 (Inconclusive Gates)" gates={(report.inconclusive ?? []) as Json[]} kind="warn" ctx={ctx} />
                <GateList title="已豁免门禁 (Waived Gates)" gates={(report.waived ?? []) as Json[]} ctx={ctx} />
              </div>
            )}

            {data?.history && data.history.length > 0 && (
              <div className="admin-subblock">
                <div className="dag-title">图结构突变日志 (Mutation History)</div>
                {data.history.slice(0, 8).map((m) => (
                  <div key={String(m.mutation_id)} className="dag-row">
                    <span className={m.accepted ? 'dag-ok' : 'dag-fail'}>{m.accepted ? '✓' : '✗'}</span>{' '}
                    {String(m.actor ?? '?')}
                    <span className="dim">
                      {m.rationale ? ` — ${String(m.rationale)}` : ''}
                      {m.created_at ? ` · ${String(m.created_at).slice(0, 19)}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {data?.mode === 'dag_guided' && (
              <div className="admin-subblock">
                <div className="dag-title">向导师智能体 (Supervisor) 申请重新规划</div>
                <input
                  className="input sm"
                  style={{ width: '100%' }}
                  value={replanNote}
                  onChange={(e) => setReplanNote(e.target.value)}
                  placeholder="请输入对新机理探索路径的指导或建议（可选）"
                />
                <button
                  type="button"
                  className="btn outline sm"
                  style={{ marginTop: 6 }}
                  disabled={busy}
                  onClick={replan}
                >
                  {busy ? '请求中…' : '提交重新规划请求'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
