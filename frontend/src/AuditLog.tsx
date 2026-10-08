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

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { boundEventPage, eventMatchesQuery, mergeAndTrimLiveEvents } from './eventWindow';
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

const EventCard = memo(function EventCard({ event, agentId, onError }: {
  event: EventEnvelope; agentId: string; onError: (e: unknown) => void;
}) {
  const [detail, setDetail] = useState<EventEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
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
    <details ref={detailsRef} className={`audit-card ${alert ? 'alert' : ''}`} onToggle={(event) => {
      if (!event.currentTarget.open) setDetail(null);
    }}>
      <summary>
        <span className="ac-time">{stamp(event.created_at)}</span>
        <span className="ac-seq">#{event.session_seq ?? event.seq}</span>
        <span className={`ac-type ${event.type.split('.')[0]}`}>{event.type}</span>
        {summary && <span className="ac-summary">{summary}</span>}
        {event.run_id && <span className="ac-run">run {shortId(event.run_id)}</span>}
      </summary>
      <div className="ac-body">
        {Boolean(event.data._payload_omitted) && !detail && (
          <button className="btn outline sm" disabled={loading} onClick={() => {
            setLoading(true);
            api.eventDetail(agentId, event.event_id).then((full) => {
              if (detailsRef.current?.open) setDetail(full);
            }).catch(onError).finally(() => setLoading(false));
          }}>{loading ? 'Loading…' : 'Load full event payload'}</button>
        )}
        <FieldView data={detail?.data ?? event.data} />
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
  // Retain only the displayed page. Older/newer navigation fetches by cursor.
  const [loaded, setLoaded] = useState<EventEnvelope[] | null>(null);
  const [hasOlder, setHasOlder] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [isLatest, setIsLatest] = useState(true);
  const requestVersion = useRef(0);
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
    ++requestVersion.current;
    setLoaded(null);
    setIsLatest(true);
    setLoadingOlder(false);
    api
      .eventsPage(agentId, { limit: PAGE_SIZE })
      .then((page) => {
        if (!cancelled) {
          const bounded = boundEventPage(page, PAGE_SIZE);
          setLoaded(bounded);
          setHasOlder(page.length >= PAGE_SIZE || bounded.length < page.length);
        }
      })
      .catch((e) => {
        if (!cancelled) onError(e);
      });
    return () => {
      cancelled = true;
      ++requestVersion.current;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, reloadKey]);

  const merged = useMemo(() => {
    if (loaded === null) return null;
    if (!isLatest) return loaded;
    const newest = loaded.at(-1)?.session_seq ?? 0;
    return mergeAndTrimLiveEvents(loaded, liveEvents.filter(
      (event) => event.session_id === agentId && (event.session_seq ?? 0) > newest,
    ), PAGE_SIZE).live;
  }, [loaded, liveEvents, isLatest, agentId]);

  const oldestSeq = useMemo(() => {
    let min = Number.POSITIVE_INFINITY;
    for (const e of merged ?? []) min = Math.min(min, e.session_seq ?? 0);
    return Number.isFinite(min) ? min : null;
  }, [merged]);

  const loadPage = useCallback(async (direction: 'older' | 'newer') => {
    if (!agentId || loadingOlder || oldestSeq === null) return;
    const newestSeq = merged?.at(-1)?.session_seq ?? 0;
    const version = ++requestVersion.current;
    setLoadingOlder(true);
    try {
      const page = await api.eventsPage(agentId, direction === 'older'
        ? { before: oldestSeq, limit: PAGE_SIZE }
        : { after: newestSeq, tail: false, limit: PAGE_SIZE });
      if (version !== requestVersion.current) return;
      if (!page.length) {
        if (direction === 'older') setHasOlder(false);
        else setReloadKey((key) => key + 1);
        return;
      }
      const bounded = boundEventPage(page, PAGE_SIZE, direction === 'older' ? 'newest' : 'oldest');
      setLoaded(bounded);
      setIsLatest(false);
      setHasOlder(direction === 'newer' || page.length >= PAGE_SIZE || bounded.length < page.length);
    } catch (e) {
      onError(e);
    } finally {
      if (version === requestVersion.current) setLoadingOlder(false);
    }
  }, [agentId, loadingOlder, oldestSeq, merged, onError]);

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

  const q = query.trim().toLowerCase();
  const visible = merged.filter((event) => !q || eventMatchesQuery(event, q));
  const canLoadOlder = hasOlder || (isLatest && (oldestSeq ?? 0) > 1);

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
          disabled={isLatest || loadingOlder}
          onClick={() => void loadPage('newer')}
        >
          ‹ newer
        </button>
        <span className="audit-page-info">
          #{oldestSeq ?? 0}–{merged.at(-1)?.session_seq ?? 0} · {merged.length} events · {isLatest ? 'latest' : 'history'}
        </span>
        <button
          className="btn ghost sm"
          disabled={!canLoadOlder || loadingOlder}
          onClick={() => void loadPage('older')}
        >
          older ›
        </button>
        {!isLatest && (
          <button className="btn ghost sm" onClick={() => setReloadKey((key) => key + 1)}>
            latest
          </button>
        )}
      </div>
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
          .map((event) => <EventCard key={event.event_id} event={event} agentId={agentId} onError={onError} />)
      )}
    </div>
  );
}
