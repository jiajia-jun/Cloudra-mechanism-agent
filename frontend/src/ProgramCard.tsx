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

export function ProgramCardView({
  item,
  childImageUrl,
}: {
  item: ProgramItem;
  childImageUrl?: (child: ToolItem) => string | null;
}) {
  const [open, setOpen] = useState(false);
  const completed = item.children.filter((child) => child.status === 'completed').length;
  const failed = item.children.filter(
    (child) => child.status != null && !['completed', 'queued', 'running', 'waiting'].includes(child.status),
  ).length;
  const waiting = item.children.find((child) => child.status === 'waiting');
  const icon = STATUS_ICON[item.status] ?? '?';
  const cls = item.status === 'running' ? 'running' : item.status === 'completed' ? 'ok' : item.status === 'unknown' ? 'queued' : 'fail';
  const errorLine =
    item.error && typeof item.error.line === 'number' && item.source
      ? Math.min(Math.max(1, item.error.line), item.source.split('\n').length)
      : null;
  return (
    <div className={`program-card ${cls}`}>
      <div className="tool-row program-head" onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">JavaScript program</span>
        <span className="tool-sep">·</span>
        <span className="tool-summary">
          {item.status === 'running'
            ? `running… ${completed}/${item.children.length} calls completed`
            : `${item.status} · ${completed}/${item.children.length} calls completed${failed > 0 ? ` · ${failed} failed` : ''}`}
        </span>
        {item.sourceHash && <span className="tool-sep">sha {item.sourceHash.slice(0, 8)}</span>}
      </div>
      {waiting && (
        <div className="program-waiting">
          ⏸ <code>{waiting.name}</code> is waiting for approval — see the approvals tab
        </div>
      )}
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
          {item.children.length > 0 && (
            <div className="program-children">
              {item.children.map((child) => (
                <ToolRow key={child.id} item={child} imageUrl={childImageUrl ? childImageUrl(child) : null} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const ProgramCard = memo(ProgramCardView);
