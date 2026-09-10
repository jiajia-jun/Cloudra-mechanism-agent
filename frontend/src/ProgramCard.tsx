import { memo, useState } from 'react';
import type { ProgramItem, ToolItem } from './timeline';
import { ToolRow } from './ToolRow';

function fullText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const STATUS_ICON: Record<string, string> = {
  running: '▸',
  completed: '✓',
  failed: '✗',
  cancelled: '✗',
  interrupted: '✗',
  unknown: '?',
};

/** Read-only source panel: escaped text with line numbers, copy + download.
 * The error line is highlighted only when the engine supplied a valid line
 * number inside the original source. */
function SourcePanel({
  source,
  executionId,
  errorLine,
}: {
  source: string;
  executionId: string;
  errorLine: number | null;
}) {
  const [copied, setCopied] = useState(false);
  const lines = source.split('\n');
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  const onDownload = () => {
    const blob = new Blob([source], { type: 'text/javascript' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${executionId}.js`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="program-source">
      <div className="program-source-actions">
        <button className="btn ghost sm" onClick={onCopy}>{copied ? 'copied' : 'copy'}</button>
        <button className="btn ghost sm" onClick={onDownload}>download .js</button>
      </div>
      <pre className="program-code">
        {lines.map((line, index) => (
          <div
            key={index}
            className={`program-code-line${errorLine === index + 1 ? ' error-line' : ''}`}
          >
            <span className="program-lineno">{index + 1}</span>
            <span>{line || ' '}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}

function getProgramSummary(item: ProgramItem): { title: string; summary: string; tag: string } {
  const activeChild =
    item.children.find((c) => c.running || c.status === 'running' || c.status === 'waiting') ??
    item.children[item.children.length - 1];

  if (activeChild) {
    if (activeChild.running || activeChild.status === 'running') {
      return {
        tag: 'JS',
        title: activeChild.name,
        summary: `running: ${activeChild.argsSummary || 'executing…'}`,
      };
    }
    if (activeChild.status === 'waiting') {
      return {
        tag: 'JS',
        title: activeChild.name,
        summary: `waiting for approval: ${activeChild.argsSummary || ''}`,
      };
    }
  }

  if (item.children.length === 1) {
    const c = item.children[0];
    return {
      tag: 'JS',
      title: c.name,
      summary: c.argsSummary ? `${c.argsSummary} (${c.status ?? 'done'})` : (c.resultSummary || c.status || 'done'),
    };
  }

  if (item.children.length > 1) {
    const toolNames = Array.from(new Set(item.children.map((c) => c.name))).join(', ');
    const completed = item.children.filter((c) => c.status === 'completed').length;
    return {
      tag: 'JS',
      title: `${item.children.length} operations`,
      summary: `${completed}/${item.children.length} completed: ${toolNames}`,
    };
  }

  if (item.source) {
    const callMatch = item.source.match(/call\s*\(\s*['"]([a-zA-Z0-9_]+)['"]/);
    if (callMatch) {
      return {
        tag: 'JS',
        title: callMatch[1],
        summary: item.status === 'running' ? `initializing ${callMatch[1]}…` : item.status,
      };
    }
  }

  return {
    tag: 'JS',
    title: 'Script',
    summary: item.status === 'running' ? 'running…' : item.status,
  };
}

export function ProgramCardView({
  item,
  childImageUrl,
}: {
  item: ProgramItem;
  childImageUrl?: (child: ToolItem) => string | null;
}) {
  const [open, setOpen] = useState(false);
  const waiting = item.children.find((child) => child.status === 'waiting');
  const icon = STATUS_ICON[item.status] ?? '?';
  const cls = item.status === 'running' ? 'running' : item.status === 'completed' ? 'ok' : item.status === 'unknown' ? 'queued' : 'fail';
  const errorLine =
    item.error && typeof item.error.line === 'number' && item.source
      ? Math.min(Math.max(1, item.error.line), item.source.split('\n').length)
      : null;

  const headerInfo = getProgramSummary(item);

  return (
    <div className={`program-card ${cls}`}>
      <div className="tool-row program-head" onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{icon}</span>
        <span className="program-tag">{headerInfo.tag}</span>
        <span className="tool-name">{headerInfo.title}</span>
        <span className="tool-sep">·</span>
        <span className="tool-summary">{headerInfo.summary}</span>
        {item.sourceHash && <span className="tool-sep">sha {item.sourceHash.slice(0, 8)}</span>}
        <button
          type="button"
          className="btn ghost sm program-code-toggle"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
          }}
          title="Toggle JavaScript source code and execution output"
        >
          {open ? 'Hide Code' : 'View Code'}
        </button>
      </div>

      {waiting && (
        <div className="program-waiting">
          <span className="badge warning sm" style={{ marginRight: '6px' }}>Review Required</span>
          <code>{waiting.name}</code> is waiting for approval — review in Approvals tab
        </div>
      )}

      {/* Child tool rows are transparent and displayed directly */}
      {item.children.length > 0 && (
        <div className="program-children-direct">
          {item.children.map((child) => (
            <ToolRow key={child.id} item={child} imageUrl={childImageUrl ? childImageUrl(child) : null} />
          ))}
        </div>
      )}

      {/* Collapsible raw JS code & execution details */}
      {open && (
        <div className="program-body">
          {item.source != null ? (
            <SourcePanel source={item.source} executionId={item.executionId} errorLine={errorLine} />
          ) : (
            <div className="program-no-source">source unavailable — the program.submitted event is outside the loaded history</div>
          )}
          {item.outputs.length > 0 && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Outputs</span>
              {item.outputs.map((value, index) => (
                <pre key={index} className="tool-detail-pre">{fullText(value)}</pre>
              ))}
            </div>
          )}
          {item.error && (
            <div className="tool-detail-section">
              <span className="tool-detail-label">Error</span>
              <pre className="tool-detail-pre">
                {[
                  item.error.code,
                  item.error.message,
                  item.error.line ? `line ${String(item.error.line)}` : '',
                  item.error.call_id ? `call ${String(item.error.call_id)}` : '',
                ]
                  .filter(Boolean)
                  .join(' — ')}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const ProgramCard = memo(ProgramCardView);
