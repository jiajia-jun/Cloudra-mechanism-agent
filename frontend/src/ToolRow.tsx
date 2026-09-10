import { memo, useState } from 'react';
import type { ToolItem } from './timeline';

function short(text: unknown, max = 80): string {
  const s = typeof text === 'string' ? text : JSON.stringify(text);
  if (!s) return '';
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

/** Lifecycle icon/class for a tool row; legacy rows without a status fall
 * back to the original running/ok mapping unchanged. */
function statusView(item: ToolItem): { icon: string; cls: string } {
  switch (item.status) {
    case 'queued':
      return { icon: '·', cls: 'queued' };
    case 'running':
      return { icon: '▸', cls: 'running' };
    case 'waiting':
      return { icon: '||', cls: 'waiting' };
    case 'blocked':
      return { icon: '!', cls: 'fail' };
    case 'completed':
      return { icon: '✓', cls: 'ok' };
    case 'failed':
    case 'cancelled':
    case 'interrupted':
      return { icon: '✗', cls: 'fail' };
    default:
      break;
  }
  return {
    icon: item.running ? '▸' : item.ok ? '✓' : '✗',
    cls: item.running ? 'running' : item.ok ? 'ok' : 'fail',
  };
}

export function ToolRowView({ item, imageUrl }: { item: ToolItem; imageUrl?: string | null }) {
  const [open, setOpen] = useState(false);
  const { icon, cls } = statusView(item);
  const live = item.running || item.status === 'queued' || item.status === 'waiting';
  return (
    <>
      <div className={`tool-row ${cls}`} onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">{item.name}</span>
        <span className="tool-sep">·</span>
        <span className="tool-summary">
          {live
            ? short(item.argsSummary, 120) || `${item.status ?? 'running'}…`
            : short(item.resultSummary, 200) || (item.ok ? 'done' : 'failed')}
        </span>
        {item.status && item.status !== 'completed' && item.status !== 'failed' && !item.running && (
          <span className="tool-sep">{item.status}</span>
        )}
        {item.durationMs != null && <span className="tool-sep">{item.durationMs}ms</span>}
      </div>
      {imageUrl && !item.running && (
        <a className="tool-image" href={imageUrl} target="_blank" rel="noreferrer" title={item.imagePath ?? 'image output'}>
          <img src={imageUrl} alt={`${item.name} output`} loading="lazy" />
        </a>
      )}
      {open && (
        <div className="tool-detail">
          {item.argsSummary && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Arguments</span>
              <pre className="tool-detail-pre">{item.argsSummary}</pre>
            </div>
          )}
          {item.resultSummary && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Output</span>
              <pre className="tool-detail-pre">{item.resultSummary}</pre>
            </div>
          )}
          {(item.effectState || item.callId) && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Lifecycle</span>
              <pre className="tool-detail-pre">
                {[
                  item.callId ? `call ${item.callId}` : '',
                  item.effectState ? `effect ${item.effectState}` : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </pre>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// Memoized so a tool row re-renders only when its own item reference changes
// (i.e. the persisted timeline rebuilt), not on every streaming token.
export const ToolRow = memo(ToolRowView);
