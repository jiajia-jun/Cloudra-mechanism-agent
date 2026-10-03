/**
 * AuditLog — human-readable audit trail of one agent's run history.
 *
 * Rendering and fetching are both lazy: only the newest page (200 events) is
 * fetched up front, older pages load on demand through the `before` cursor,
 * and the DOM only ever holds one page of cards.  Live SSE events are merged
 * into the newest end.  Events are split into tool activity (LLM calls, tool
 * executions, run lifecycle, compaction) and system events (commands,
 * approvals, DAG, hub, reminders), rendered as collapsible cards with
 * structured fields instead of raw JSON; string payloads are never truncated.
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import type { EventEnvelope } from './types';

interface AuditLogProps {
  agentId: string | null;
  projectId: string | null;
  liveEvents: EventEnvelope[];
  onError: (e: unknown) => void;
}

const PAGE_SIZE = 200;

/** Events that describe the model's working loop (tools / LLM / run / compact). */
function isToolActivity(type: string): boolean {
  return (
    type.startsWith('tool.') ||
    type.startsWith('llm.') ||
    type.startsWith('run.') ||
    type.startsWith('compaction.') ||
    type === 'loop.detected' ||
    type === 'agent.thinking'
  );
}

/** Events that describe a failure or a warning — accent them in the list. */
function isAlert(type: string, data: Record<string, unknown>): boolean {
  if (type === 'llm.failed' || type === 'tool.blocked' || type === 'command.rejected') return true;
  if (type === 'run.finished') return data.outcome === 'failed';
  if (type === 'agent.context_reset') return true;
  return false;
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

function stamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Render one scalar/string field as a labelled row; strings never truncate. */
function FieldRow({ name, value }: { name: string; value: unknown }) {
  if (typeof value === 'string') {
    return (
      <div className="af-row">
        <span className="af-key">{name}</span>
        <pre className="af-text">{value}</pre>
      </div>
    );
  }
  if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return (
      <div className="af-row">
        <span className="af-key">{name}</span>
        <span className="af-scalar">{value === null ? 'null' : String(value)}</span>
      </div>
    );
  }
  if (Array.isArray(value)) {
    return (
      <div className="af-row">
        <span className="af-key">{name}</span>
        <div className="af-list">
          {value.map((item, i) =>
            typeof item === 'object' && item !== null ? (
              <div key={i} className="af-item">
                <span className="af-scalar">[{i}]</span>
                <FieldView data={item as Record<string, unknown>} />
              </div>
            ) : (
              <pre key={i} className="af-text">
                {typeof item === 'string' ? item : JSON.stringify(item)}
              </pre>
            ),
          )}
          {value.length === 0 && <span className="af-scalar">(empty)</span>}
        </div>
      </div>
    );
  }
  if (typeof value === 'object') {
    return (
      <div className="af-row">
        <span className="af-key">{name}</span>
        <FieldView data={value as Record<string, unknown>} />
      </div>
    );
  }
  return (
    <div className="af-row">
      <span className="af-key">{name}</span>
      <span className="af-scalar">{String(value)}</span>
    </div>
  );
}

/** Recursive object renderer: nested key/value blocks, no JSON.stringify. */
function FieldView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <span className="af-scalar">(empty object)</span>;
  }
  return (
    <div className="af-object">
      {entries.map(([key, value]) => (
        <FieldRow key={key} name={key} value={value} />
      ))}
    </div>
  );
}

const EventCard = memo(function EventCard({ event }: { event: EventEnvelope }) {
  const alert = isAlert(event.type, event.data);
  const summary = (() => {
    const d = event.data;
    const candidate =
      d.summary ?? d.message ?? d.content ?? d.result_summary ?? d.note ?? d.reason ?? d.error ?? d.objective ?? d.tool_name;
    if (typeof candidate === 'string' && candidate.length > 0) {
      const oneLine = candidate.split('\n')[0];
      return oneLine.length > 140 ? oneLine.slice(0, 140) + '…' : oneLine;
    }
    return '';
  })();
  return (
    <details className={`audit-card ${alert ? 'alert' : ''}`}>
      <summary>
        <span className="ac-time">{stamp(event.created_at)}</span>
        <span className="ac-seq">#{event.session_seq ?? event.seq}</span>
        <span className={`ac-type ${event.type.split('.')[0]}`}>{event.type}</span>
        {summary && <span className="ac-summary">{summary}</span>}
        {event.run_id && <span className="ac-run">run {shortId(event.run_id)}</span>}
      </summary>
      <div className="ac-body">
        <FieldView data={event.data} />
        <div className="ac-meta">
          <span>event_id {event.event_id}</span>
          <span>seq {event.seq}</span>
          {event.session_seq != null && <span>session_seq {event.session_seq}</span>}
          {event.run_id && <span>run_id {event.run_id}</span>}
        </div>
      </div>
    </details>
  );
});

export default function AuditLog({ agentId, projectId, liveEvents, onError }: AuditLogProps) {
  // Lazily fetched pages, oldest → newest.  The live SSE window (from the
  // parent) is merged on the newest end; only one page ever renders.
  const [loaded, setLoaded] = useState<EventEnvelope[] | null>(null);
  const [hasOlder, setHasOlder] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [view, setView] = useState<'tools' | 'system'>('tools');
  const [query, setQuery] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  // Initial page only — bounded request, no full-history fetch.
  useEffect(() => {
    if (!agentId) {
      setLoaded([]);
      return;
    }
    let cancelled = false;
    setLoaded(null);
    setPageIndex(0);
    api
      .eventsPage(agentId, { limit: PAGE_SIZE })
      .then((page) => {
        if (!cancelled) {
          setLoaded(page);
          setHasOlder(page.length >= PAGE_SIZE);
        }
      })
      .catch((e) => {
        if (!cancelled) onError(e);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, reloadKey]);

  const merged = useMemo(() => {
    if (loaded === null) return null;
    const byId = new Map(loaded.map((e) => [e.event_id, e]));
    for (const e of liveEvents) {
      if (!byId.has(e.event_id)) byId.set(e.event_id, e);
    }
    return [...byId.values()].sort(
      (a, b) => (a.session_seq ?? 0) - (b.session_seq ?? 0) || a.seq - b.seq,
    );
  }, [loaded, liveEvents]);

  const oldestSeq = useMemo(() => {
    let min = Number.POSITIVE_INFINITY;
    for (const e of merged ?? []) min = Math.min(min, e.session_seq ?? 0);
    return Number.isFinite(min) ? min : null;
  }, [merged]);

  const loadOlder = useCallback(async () => {
    if (!agentId || loadingOlder || oldestSeq === null) return;
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(agentId, { before: oldestSeq, limit: PAGE_SIZE });
      if (page.length < PAGE_SIZE) setHasOlder(false);
      setLoaded((prev) => {
        const base = prev ?? [];
        const known = new Set(base.map((e) => e.event_id));
        for (const e of liveEvents) known.add(e.event_id);
        const fresh = page.filter((e) => !known.has(e.event_id));
        return [...fresh, ...base];
      });
    } catch (e) {
      onError(e);
    } finally {
      setLoadingOlder(false);
    }
  }, [agentId, loadingOlder, oldestSeq, liveEvents, onError]);

  // Search index built only while a filter is active (stringifying the whole
  // loaded set on every live event would be wasteful otherwise).
  const searchMap = useMemo(() => {
    if (!query.trim() || merged === null) return null;
    return new Map(
      merged.map((e) => [e.event_id, (e.type + '\n' + JSON.stringify(e.data)).toLowerCase()]),
    );
  }, [merged, query]);

  const { toolCount, systemCount } = useMemo(() => {
    let tools = 0;
    let system = 0;
    for (const e of merged ?? []) {
      if (isToolActivity(e.type)) tools += 1;
      else system += 1;
    }
    return { toolCount: tools, systemCount: system };
  }, [merged]);

  if (!agentId) {
    return <div className="empty-hint">Select an agent to inspect its audit log.</div>;
  }
  if (merged === null) {
    return <div className="empty-hint">Loading audit log…</div>;
  }

  const totalPages = Math.max(1, Math.ceil(merged.length / PAGE_SIZE));
  const clampedIndex = Math.min(pageIndex, totalPages - 1);
  const pageStart = Math.max(0, merged.length - (clampedIndex + 1) * PAGE_SIZE);
  const pageEnd = merged.length - clampedIndex * PAGE_SIZE;
  const q = query.trim().toLowerCase();
  const visible = merged
    .slice(pageStart, pageEnd)
    .filter(
      (e) =>
        !q ||
        e.type.toLowerCase().includes(q) ||
        (searchMap?.get(e.event_id) ?? '').includes(q),
    );
  const atLastLoadedPage = clampedIndex >= totalPages - 1;

  return (
    <div className="audit-log">
      <div className="audit-toolbar">
        <div className="audit-seg">
          <button
            className={`audit-seg-btn ${view === 'tools' ? 'active' : ''}`}
            onClick={() => setView('tools')}
          >
            Tool activity <span className="ac-count">{toolCount}</span>
          </button>
          <button
            className={`audit-seg-btn ${view === 'system' ? 'active' : ''}`}
            onClick={() => setView('system')}
          >
            System events <span className="ac-count">{systemCount}</span>
          </button>
        </div>
        <button
          className="btn ghost sm"
          onClick={() => {
            setPageIndex(0);
            setReloadKey((k) => k + 1);
          }}
          title="Reload the newest page"
        >
          reload
        </button>
        {projectId && (
          <a
            className="btn ghost sm"
            href={api.projectTranscriptUrl(projectId)}
            download
            title="Download the full project transcript as Markdown — every event with complete payloads (messages, thinking chains, tool arguments/results, compaction and context-tree snapshots)"
          >
            ↓ full log
          </a>
        )}
      </div>
      <input
        className="input audit-search"
        placeholder="Filter by type or content…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="audit-pager">
        <button
          className="btn ghost sm"
          disabled={clampedIndex === 0}
          onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
        >
          ‹ newer
        </button>
        <span className="audit-page-info">
          page {clampedIndex + 1} / {totalPages}
          {hasOlder && atLastLoadedPage ? '+' : ''} · {merged.length} loaded
        </span>
        <button
          className="btn ghost sm"
          disabled={atLastLoadedPage && !hasOlder}
          onClick={() => setPageIndex((p) => p + 1)}
        >
          older ›
        </button>
        {clampedIndex > 0 && (
          <button className="btn ghost sm" onClick={() => setPageIndex(0)}>
            latest
          </button>
        )}
      </div>
      {atLastLoadedPage && hasOlder && (
        <button className="btn outline sm" onClick={loadOlder} disabled={loadingOlder}>
          {loadingOlder ? 'Loading…' : `Load ${PAGE_SIZE} older events`}
        </button>
      )}
      {visible.length === 0 ? (
        <div className="empty-hint">
          {query
            ? 'No events match the filter on this page.'
            : view === 'tools'
              ? 'No tool activity yet.'
              : 'No system events yet.'}
        </div>
      ) : (
        visible
          .filter((e) => isToolActivity(e.type) === (view === 'tools'))
          .map((event) => <EventCard key={event.event_id} event={event} />)
      )}
    </div>
  );
}
