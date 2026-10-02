/**
 * BenchmarkPanel — hosted benchmark cockpit (GH #32 Phase 2).
 *
 * Near-fullscreen modal over the /api/v2/benchmark/* control plane: a tier
 * selector driven by the built-in task catalog (`/api/v2/benchmark/catalog`,
 * so no directory typing is needed), optional custom task dirs, batch
 * start/stop controls, a live task matrix (per-tier filter, per-layer scores,
 * duration), and recent batch history. Live updates ride the
 * /api/v2/benchmark/stream SSE feed (snapshot on connect + batch events); a
 * slow status poll backs it up.
 * Each scored task row links into the task's standard project view — the
 * existing timeline/DagPanel components are the drill-down, so nothing here
 * re-renders agent internals.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  api,
  type BenchmarkCatalog,
  type BenchmarkCatalogTier,
  type BenchmarkHistory,
  type BenchmarkStatus,
  type BenchmarkTaskRow,
} from './api';
import { PathPickerModal } from './PathPickerModal';

interface BenchmarkPanelProps {
  onClose: () => void;
  onOpenProject: (projectId: string) => void;
  onToast: (kind: 'ok' | 'error' | 'info', text: string) => void;
}

const TIERS = ['easy', 'normal', 'hard', 'impossible'];

/** 档位说明（选题器与图例共用，文案与题源 ideapool/reaction_candidates/<tier>.md 对齐）。 */
const TIER_INFO: Record<string, string> = {
  easy: 'single elementary step (R → TS → P)',
  normal: 'multi-step network with intermediates',
  hard: 'competing stereochemical channels',
  impossible: 'uncomputable elements must be flagged accessible=false',
};

const STATUS_BADGES: Record<string, { glyph: string; label: string; cls: string }> = {
  queued: { glyph: '·', label: 'Queued', cls: 'queued' },
  running: { glyph: '▸', label: 'Running', cls: 'running' },
  scored: { glyph: '✓', label: 'Scored', cls: 'scored' },
  cancelled: { glyph: '—', label: 'Cancelled', cls: 'cancelled' },
  error: { glyph: '✗', label: 'Error', cls: 'error' },
};

function badge(row: BenchmarkTaskRow): { glyph: string; label: string; cls: string } {
  return STATUS_BADGES[row.status] ?? { glyph: '·', label: row.status, cls: 'queued' };
}

function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

function fmtDuration(started: number | null, finished: number | null): string {
  if (!started) return '—';
  const end = finished ?? Date.now() / 1000;
  const s = Math.max(0, Math.round(end - started));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`;
}

export default function BenchmarkPanel({ onClose, onOpenProject, onToast }: BenchmarkPanelProps) {
  const [status, setStatus] = useState<BenchmarkStatus | null>(null);
  const [history, setHistory] = useState<BenchmarkHistory | null>(null);
  const [catalog, setCatalog] = useState<BenchmarkCatalog | null>(null);
  const [tierFilter, setTierFilter] = useState<string>('all');
  const [selectedTiers, setSelectedTiers] = useState<string[]>(TIERS);
  const [customDirs, setCustomDirs] = useState('');
  const [dirPickerOpen, setDirPickerOpen] = useState(false);
  const [only, setOnly] = useState('');
  const [concurrency, setConcurrency] = useState('1');
  const [busy, setBusy] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  const refreshStatus = () =>
    api.benchmarkStatus().then(setStatus).catch(() => undefined);

  useEffect(() => {
    void refreshStatus();
    api.benchmarkRuns().then(setHistory).catch(() => undefined);
    api.benchmarkCatalog().then(setCatalog).catch(() => undefined);
    const source = new EventSource(api.benchmarkStreamUrl());
    sourceRef.current = source;
    const onEvent = (msg: MessageEvent) => {
      try {
        const data = JSON.parse(msg.data) as unknown;
        if (msg.type === 'benchmark.snapshot') setStatus(data as BenchmarkStatus);
        else void refreshStatus();
      } catch {
        /* ignore malformed */
      }
    };
    source.addEventListener('benchmark.snapshot', onEvent);
    source.addEventListener('benchmark.batch_started', onEvent);
    source.addEventListener('benchmark.task_started', onEvent);
    source.addEventListener('benchmark.task_scored', onEvent);
    source.addEventListener('benchmark.task_cancelled', onEvent);
    source.addEventListener('benchmark.task_error', onEvent);
    source.addEventListener('benchmark.batch_finished', onEvent);
    return () => {
      source.close();
      sourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Slow poll as SSE fallback while a batch is live.
  useEffect(() => {
    if (!status || !['running', 'stopping'].includes(status.status)) return;
    const timer = window.setInterval(() => void refreshStatus(), 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status]);

  const running = status?.status === 'running' || status?.status === 'stopping';

  const start = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        tiers: selectedTiers,
        tasks_dirs: customDirs
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        only: only.trim(),
        concurrency: Math.max(1, Number(concurrency) || 1),
      };
      const snap = await api.benchmarkStart(body);
      setStatus(snap);
      onToast('ok', `batch ${snap.batch_id} started with ${snap.tasks.length} tasks`);
    } catch (e) {
      onToast('error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      const snap = await api.benchmarkStop();
      setStatus(snap);
      onToast('info', 'batch stop requested — agents are being cancelled (compute runs untouched)');
    } catch (e) {
      onToast('error', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const tasks = useMemo(() => {
    const all = status?.tasks ?? [];
    return tierFilter === 'all' ? all : all.filter((t) => t.tier === tierFilter);
  }, [status, tierFilter]);

  const tierCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of status?.tasks ?? []) counts[t.tier] = (counts[t.tier] ?? 0) + 1;
    return counts;
  }, [status]);

  const catalogByTier = useMemo(() => {
    const m: Record<string, BenchmarkCatalogTier> = {};
    for (const t of catalog?.tiers ?? []) m[t.tier] = t;
    return m;
  }, [catalog]);

  // 题库已知档位在前，catalog 里多出的档位追加在后（新增档位不必改这份清单）。
  const chipTiers = useMemo(
    () => [...TIERS, ...(catalog?.tiers ?? []).map((t) => t.tier).filter((t) => !TIERS.includes(t))],
    [catalog],
  );

  const selectedTaskCount = useMemo(
    () => selectedTiers.reduce((n, t) => n + (catalogByTier[t]?.task_count ?? 0), 0),
    [selectedTiers, catalogByTier],
  );

  const hasBatch = (status?.tasks.length ?? 0) > 0;
  // 空选择时后端会回落到内置 easy 档——那与界面显示不符，直接禁用 Start。
  const canStart = selectedTiers.length > 0 || customDirs.trim() !== '';

  return (
    <div className="modal-backdrop">
      <div className="modal bm-modal">
        <div className="modal-head">
          <span className="modal-title">Benchmark cockpit</span>
          <div className="bm-batch-status" title="batch status">
            <span className={`state-dot ${running ? 'running' : status?.status === 'done' ? 'succeeded' : status?.status === 'stopped' ? 'cancelled' : 'waiting_input'}`} />
            {status?.batch_id ? `${status.batch_id} · ${status.status}` : 'idle'}
          </div>
          <button className="btn ghost sm" type="button" onClick={onClose}>✕</button>
        </div>

        <div className="bm-body">
          <div className="bm-guide">
            <strong>Pick the tiers to run, then press Start.</strong> Every task becomes its own
            project (open ↗) with a live agent, DAG and compute; scores land in the matrix below as
            each one finishes. <em>Impossible</em> tasks contain elements that the allowed methods
            cannot compute — the correct delivery still submits the graph and flags those elements
            accessible=false. Start sends
            compute jobs to the ordinary scheduler (it never launches QM processes itself), and
            Stop only cancels the task agents — running calculations are left alone.
            <div className="bm-legend">
              {chipTiers.map((t) => (
                <span key={t}>
                  <code>{t}</code> {TIER_INFO[t] ?? ''}
                </span>
              ))}
            </div>
          </div>

          <div className="bm-controls">
            <span className="bm-field-label">Run tiers</span>
            {chipTiers.map((t) => {
              const on = selectedTiers.includes(t);
              const entry = catalogByTier[t];
              return (
                <button
                  key={t}
                  type="button"
                  className={`btn ghost sm bm-tier ${on ? 'active' : ''}`}
                  title={TIER_INFO[t] ?? entry?.path ?? ''}
                  disabled={running}
                  onClick={() =>
                    setSelectedTiers((prev) =>
                      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
                    )
                  }
                >
                  {on ? '✓ ' : ''}{t}
                  {entry ? ` · ${entry.task_count}` : ''}
                </button>
              );
            })}
            <button
              type="button"
              className="btn ghost sm"
              disabled={running}
              onClick={() =>
                setSelectedTiers(
                  selectedTiers.length === chipTiers.length ? [] : [...chipTiers],
                )
              }
            >
              {selectedTiers.length === chipTiers.length ? 'none' : 'all'}
            </button>
            <span className="bm-selection" title="built-in tasks this batch will run">
              {selectedTaskCount} task{selectedTaskCount === 1 ? '' : 's'}
              {customDirs.trim() ? ' + custom dirs' : ''}
            </span>
            <div className="bm-filter-spacer" />
            <label className="bm-field" title="how many tasks run in parallel">
              parallel
              <input
                className="input bm-num"
                value={concurrency}
                onChange={(e) => setConcurrency(e.target.value)}
                disabled={running}
              />
            </label>
            {running ? (
              <button className="btn danger sm" type="button" onClick={() => void stop()} disabled={busy}>
                Stop
              </button>
            ) : (
              <button
                className="btn primary sm"
                type="button"
                onClick={() => void start()}
                disabled={busy || !canStart}
                title={canStart ? 'Run the selected tasks' : 'Select at least one tier (or add custom task dirs)'}
              >
                Start
              </button>
            )}
          </div>

          <details className="bm-advanced">
            <summary>Custom task dirs &amp; id filter (optional)</summary>
            <div className="bm-advanced-body">
              <div className="bm-dirs-wrap">
                <input
                  className="input bm-dirs"
                  value={customDirs}
                  onChange={(e) => setCustomDirs(e.target.value)}
                  placeholder="extra task JSON dirs (comma separated)"
                  title="One or more extra task JSON directories; relative paths resolve against the working directory, then the repo root"
                  disabled={running}
                />
                <button
                  type="button"
                  className="btn ghost sm"
                  style={{ height: 30, padding: '0 8px' }}
                  title="Browse tasks directory"
                  disabled={running}
                  onClick={() => setDirPickerOpen(true)}
                >
                  📁
                </button>
              </div>
              <input
                className="input bm-only"
                value={only}
                onChange={(e) => setOnly(e.target.value)}
                placeholder="only ids (C1,D3…)"
                title="Comma-separated task ids; filters the whole selection"
                disabled={running}
              />
            </div>
            <div className="bm-hint">
              The tier buttons above already cover the built-in task bank — these two fields only
              matter for your own task JSONs. “Only ids” filters everything selected (built-in and
              custom): e.g. <code>C1,D3</code>.
            </div>
          </details>

          {hasBatch && (
            <div className="bm-filter-row">
              <span className="bm-filter-label">Show</span>
              <button className={`btn ghost sm ${tierFilter === 'all' ? 'active' : ''}`} type="button" onClick={() => setTierFilter('all')}>
                all ({status?.tasks.length ?? 0})
              </button>
              {TIERS.map((t) => (
                <button
                  key={t}
                  className={`btn ghost sm ${tierFilter === t ? 'active' : ''}`}
                  type="button"
                  onClick={() => setTierFilter(t)}
                >
                  {t} ({tierCounts[t] ?? 0})
                </button>
              ))}
            </div>
          )}

          <div className="bm-matrix">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Tier</th>
                  <th>Status</th>
                  <th>Graph</th>
                  <th>Self-cons.</th>
                  <th>Accuracy</th>
                  <th>Final</th>
                  <th>Duration</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 && (
                  <tr>
                    <td colSpan={9} className="empty-hint">
                      {hasBatch
                        ? 'No task matches this tier filter.'
                        : selectedTaskCount > 0 || customDirs.trim()
                          ? `${selectedTaskCount} built-in task${selectedTaskCount === 1 ? '' : 's'} selected${
                              customDirs.trim() ? ' plus your custom dirs' : ''
                            } — press Start to run them.`
                          : 'Nothing selected yet — tick a tier above, or add task dirs under “Custom task dirs”.'}
                    </td>
                  </tr>
                )}
                {tasks.map((row) => {
                  const b = badge(row);
                  return (
                    <tr key={row.task_id} className={`bm-task bm-${b.cls}`} title={row.error || row.notes.join('\n') || undefined}>
                      <td className="bm-task-id">
                        <span className="bm-id">{row.task_id}</span>
                        <span className="bm-name">{row.name || row.family}</span>
                      </td>
                      <td>{row.tier}</td>
                      <td>
                        <span className={`bm-badge ${b.cls}`}>{b.glyph} {b.label}</span>
                      </td>
                      <td>{fmtNum(row.graph_score)}</td>
                      <td>{row.selfconsistency_passed == null ? '—' : row.selfconsistency_passed ? '✓' : '✗'}</td>
                      <td>{fmtNum(row.accuracy_score)}</td>
                      <td className={`bm-final ${row.final_score != null && row.final_score < 0 ? 'neg' : ''}`}>
                        {fmtNum(row.final_score)}
                      </td>
                      <td>{fmtDuration(row.started_at, row.finished_at)}</td>
                      <td>
                        {row.project_id ? (
                          <button
                            className="btn ghost sm"
                            type="button"
                            title="Open this task's project (timeline, DagPanel, compute)"
                            onClick={() => onOpenProject(row.project_id)}
                          >
                            open ↗
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <details className="bm-history">
            <summary>Recent batches ({history?.batches.length ?? 0})</summary>
            {(history?.batches ?? []).map((batch) => (
              <div key={batch.batch_id} className="bm-history-row">
                <span className="bm-history-head">
                  <span className="bm-id">{batch.batch_id}</span>
                  <span className={`bm-badge ${batch.status === 'done' ? 'scored' : 'cancelled'}`}>{batch.status}</span>
                  <span className="bm-history-meta">
                    {new Date(batch.started_at * 1000).toLocaleString()} · {batch.runs.length} runs
                  </span>
                </span>
                <div className="bm-history-runs">
                  {batch.runs.map((run) => (
                    <span key={run.task_id} className="bm-history-run">
                      {run.task_id}: {fmtNum(run.final_score)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {history !== null && history.batches.length === 0 && (
              <div className="empty-hint">No benchmark batches recorded yet.</div>
            )}
          </details>
        </div>
      </div>
      <PathPickerModal
        isOpen={dirPickerOpen}
        title="Select Tasks Directory"
        initialPath={customDirs ? customDirs.split(',')[0].trim() : undefined}
        onSelect={(dir) => {
          setCustomDirs((prev) => (prev ? `${prev}, ${dir}` : dir));
        }}
        onClose={() => setDirPickerOpen(false)}
      />
    </div>
  );
}
