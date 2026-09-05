/**
 * AttentionDock — floating stack of pending approvals / ask_user prompts
 * from projects OTHER than the one currently open (the active project is
 * already covered by the Inspector tabs and the composer ask-banner).
 *
 * Each card is actionable in place: approvals get Approve/Deny buttons,
 * interactions a reply textarea — no project switch required.  A jump
 * button focuses the owning project/agent for deeper inspection.  The
 * header carries the desktop-notification opt-in (the permission request
 * needs a user gesture, so it cannot fire from a polling callback).
 */

import { useState } from 'react';
import type { PendingAttention } from './attention';

export type NotifPermission = NotificationPermission | 'unsupported';

interface AttentionDockProps {
  items: PendingAttention[];
  notifPermission: NotifPermission;
  onEnableNotifications: () => void;
  onJump: (item: PendingAttention) => void;
  onDecide: (item: PendingAttention, decision: 'approve' | 'deny') => Promise<void>;
  onRespond: (item: PendingAttention, response: string) => Promise<void>;
}

function ApprovalCard({
  item,
  onJump,
  onDecide,
}: {
  item: PendingAttention;
  onJump: (item: PendingAttention) => void;
  onDecide: (item: PendingAttention, decision: 'approve' | 'deny') => Promise<void>;
}) {
  const [busy, setBusy] = useState<'approve' | 'deny' | null>(null);
  const decide = async (decision: 'approve' | 'deny') => {
    if (busy) return;
    setBusy(decision);
    try {
      await onDecide(item, decision);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="attention-card approval">
      <div className="attention-card-head">
        <span className="attention-kind">⚠ approval</span>
        <span className="attention-project">{item.projectName}</span>
        <button
          type="button"
          className="btn ghost sm attention-jump"
          title="Open this project and agent"
          onClick={() => onJump(item)}
        >
          jump →
        </button>
      </div>
      <div className="attention-body">
        <b>{item.title}</b> wants to run <span className="mono-path">{item.body}</span>
        {item.toolCallId && (
          <span className="attention-correlation" title={item.executionId ? `program ${item.executionId}` : undefined}>
            {' '}· call {item.toolCallId}
          </span>
        )}
      </div>
      <div className="attention-actions">
        <button className="btn green sm" disabled={busy !== null} onClick={() => void decide('approve')}>
          {busy === 'approve' ? 'Approving…' : '✓ Approve'}
        </button>
        <button className="btn yellow sm" disabled={busy !== null} onClick={() => void decide('deny')}>
          {busy === 'deny' ? 'Denying…' : '✕ Deny'}
        </button>
      </div>
    </div>
  );
}

function InteractionCard({
  item,
  onJump,
  onRespond,
}: {
  item: PendingAttention;
  onJump: (item: PendingAttention) => void;
  onRespond: (item: PendingAttention, response: string) => Promise<void>;
}) {
  const [response, setResponse] = useState('');
  const [sending, setSending] = useState(false);
  const send = async () => {
    const trimmed = response.trim();
    if (!trimmed || sending) return;
    setSending(true);
    try {
      await onRespond(item, trimmed);
      setResponse('');
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="attention-card interaction">
      <div className="attention-card-head">
        <span className="attention-kind">? question</span>
        <span className="attention-project">{item.projectName}</span>
        <button
          type="button"
          className="btn ghost sm attention-jump"
          title="Open this project and agent"
          onClick={() => onJump(item)}
        >
          jump →
        </button>
      </div>
      <div className="attention-body">
        <b>{item.title}</b> asks: {item.body}
        {item.toolCallId && (
          <span className="attention-correlation" title={item.executionId ? `program ${item.executionId}` : undefined}>
            {' '}· call {item.toolCallId}
          </span>
        )}
      </div>
      <div className="attention-actions">
        <textarea
          className="input attention-reply"
          rows={2}
          placeholder="Reply here (Enter to send, Shift+Enter for newline)…"
          value={response}
          disabled={sending}
          onChange={(e) => setResponse(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button className="btn green sm" disabled={sending || !response.trim()} onClick={() => void send()}>
          {sending ? 'Sending…' : 'Send ↵'}
        </button>
      </div>
    </div>
  );
}

export default function AttentionDock({
  items,
  notifPermission,
  onEnableNotifications,
  onJump,
  onDecide,
  onRespond,
}: AttentionDockProps) {
  const [collapsed, setCollapsed] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="attention-dock">
      <div className="attention-dock-head">
        <button
          type="button"
          className="attention-dock-toggle"
          title={collapsed ? 'Expand' : 'Collapse'}
          onClick={() => setCollapsed((v) => !v)}
        >
          {collapsed ? '▸' : '▾'}
        </button>
        <span className="attention-dock-title">
          {`${items.length} request${items.length > 1 ? 's' : ''} from other projects`}
        </span>
        {notifPermission === 'default' && (
          <button
            type="button"
            className="btn ghost sm"
            title="Enable desktop notifications for new approval/question requests"
            onClick={onEnableNotifications}
          >
            🔔 enable alerts
          </button>
        )}
        {notifPermission === 'granted' && <span className="attention-notif-state on">🔔 on</span>}
        {notifPermission === 'denied' && (
          <span className="attention-notif-state" title="Desktop notifications are blocked in browser settings">
            🔔 blocked
          </span>
        )}
      </div>
      {!collapsed &&
        items.map((item) =>
          item.kind === 'approval' ? (
            <ApprovalCard key={item.key} item={item} onJump={onJump} onDecide={onDecide} />
          ) : (
            <InteractionCard key={item.key} item={item} onJump={onJump} onRespond={onRespond} />
          ),
        )}
    </div>
  );
}
