/**
 * BenchmarkPanel — hosted benchmark cockpit (GH #32 Phase 2).
 *
 * Near-fullscreen modal over the /api/v2/benchmark/* control plane: batch
 * start/stop controls, a live task matrix (per-tier filter, per-layer scores,
 * refusal outcome, duration), the cross-tier refusal confusion matrix, and
 * recent batch history. Live updates ride the /api/v2/benchmark/stream SSE
 * feed (snapshot on connect + batch events); a slow status poll backs it up.
 * Each scored task row links into the task's standard project view — the
 * existing timeline/DagPanel components are the drill-down, so nothing here
 * re-renders agent internals.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  api,
  type BenchmarkHistory,
  type BenchmarkRefusalStats,
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

const STATUS_BADGES: Record<string, { glyph: string; label: string; cls: string }> = {
  queued: { glyph: '·', label: 'Queued', cls: 'queued' },
  running: { glyph: '▸', label: 'Running', cls: 'running' },
  scored: { glyph: '✓', label: 'Scored', cls: 'scored' },
  cancelled: { glyph: '—', label: 'Cancelled', cls: 'cancelled' },
  error: { glyph: '✗', label: 'Error', cls: 'error' },
};

function badge(row: BenchmarkTaskRow): { glyph: string; label: string; cls: string } {
  if (row.status === 'scored' && row.outcome === 'refused') {
    return { glyph: '—', label: 'Refused', cls: 'cancelled' };
  }
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

function RefusalCard({ stats }: { stats: BenchmarkRefusalStats | Record<string, never> }) {
  const r = stats as BenchmarkRefusalStats;
  const has = typeof r.tp === 'number';
  return (
    <div className="bm-card bm-refusal">
      <div className="bm-card-title">Refusal (cross-tier)</div>
      <div className="bm-refusal-grid">
        <span title="correct refusals (impossible tier answered with refusal)">TP {has ? r.tp : '—'}</span>
        <span title="wrong refusals (solvable tier refused)">FP {has ? r.fp : '—'}</span>
        <span title="missed refusals (impossible tier answered)">FN {has ? r.fn : '—'}</span>
        <span title="correct answers (solvable tier answered)">TN {has ? r.tn : '—'}</span>
      </div>
      <div className="bm-refusal-metrics">
        <span>precision {has ? fmtNum(r.precision) : '—'}</span>
        <span>recall {has ? fmtNum(r.recall) : '—'}</span>
        <span>F1 {has ? fmtNum(r.f1) : '—'}</span>
      </div>
    </div>
  );
}

export default function BenchmarkPanel({ onClose, onOpenProject, onToast }: BenchmarkPanelProps) {
  const [status, setStatus] = useState<BenchmarkStatus | null>(null);
  const [history, setHistory] = useState<BenchmarkHistory | null>(null);
  const [tierFilter, setTierFilter] = useState<string>('all');
  const [tasksDirs, setTasksDirs] = useState('');
  const [dirPickerOpen, setDirPickerOpen] = useState(false);
  const [only, setOnly] = useState('');
  const [concurrency, setConcurrency] = useState('1');
  const [timeout, setTimeoutS] = useState('7200');
  const [busy, setBusy] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  const refreshStatus = () =>
    api.benchmarkStatus().then(setStatus).catch(() => undefined);

  useEffect(() => {
    void refreshStatus();
    api.benchmarkRuns().then(setHistory).catch(() => undefined);
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
        tasks_dirs: tasksDirs
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        only: only.trim(),
        concurrency: Math.max(1, Number(concurrency) || 1),
        timeout: Math.max(60, Number(timeout) || 7200),
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
          <div className="bm-controls">
            <div className="bm-dirs-wrap">
              <input
                className="input bm-dirs"
                value={tasksDirs}
                onChange={(e) => setTasksDirs(e.target.value)}
                placeholder="tasks dirs (comma separated; empty = built-in easy tier)"
                title="One or more task JSON directories; relative paths resolve against cwd then the repo root"
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
              disabled={running}
            />
            <input
              className="input bm-num"
              value={concurrency}
              onChange={(e) => setConcurrency(e.target.value)}
              title="parallel tasks"
              disabled={running}
            />
            <input
              className="input bm-num"
              value={timeout}
              onChange={(e) => setTimeoutS(e.target.value)}
              title="per-task run timeout, seconds"
              disabled={running}
            />
            {running ? (
              <button className="btn danger sm" type="button" onClick={() => void stop()} disabled={busy}>
                Stop
              </button>
            ) : (
              <button className="btn primary sm" type="button" onClick={() => void start()} disabled={busy}>
                Start
              </button>
            )}
          </div>

          <div className="bm-filter-row">
            <span className="bm-filter-label">Tier:</span>
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
            <div className="bm-filter-spacer" />
            <RefusalCard stats={status?.refusal ?? {}} />
          </div>

          <div className="bm-matrix">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Tier</th>
                  <th>Status</th>
                  <th>Integrity</th>
                  <th>Graph</th>
                  <th>Self-cons.</th>
                  <th>Accuracy</th>
                  <th>Final</th>
                  <th>Outcome</th>
                  <th>Duration</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 && (
                  <tr>
                    <td colSpan={11} className="empty-hint">
                      No batch yet — configure task dirs and press Start.
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
                      <td>{row.integrity_passed == null ? '—' : row.integrity_passed ? '✓' : '✗'}</td>
                      <td>{fmtNum(row.graph_score)}</td>
                      <td>{row.selfconsistency_passed == null ? '—' : row.selfconsistency_passed ? '✓' : '✗'}</td>
                      <td>{fmtNum(row.accuracy_score)}</td>
                      <td className={`bm-final ${row.final_score != null && row.final_score < 0 ? 'neg' : ''}`}>
                        {fmtNum(row.final_score)}
                      </td>
                      <td>{row.outcome ?? '—'}</td>
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
                      {run.task_id}: {fmtNum(run.final_score)} ({run.outcome})
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
        initialPath={tasksDirs ? tasksDirs.split(',')[0].trim() : undefined}
        onSelect={(dir) => {
          setTasksDirs((prev) => (prev ? `${prev}, ${dir}` : dir));
        }}
        onClose={() => setDirPickerOpen(false)}
      />
    </div>
  );
}
