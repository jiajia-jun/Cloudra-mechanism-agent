import { useState, useEffect, useRef, useMemo } from 'react';
import type { Agent } from './types';
import type { Translations } from './i18n';
import {
  type PendingInteractionItem,
  type PendingApprovalItem,
  parseInteractionDetails,
} from './interactionParser';

export type DecisionItem =
  | { kind: 'interaction'; data: PendingInteractionItem }
  | { kind: 'approval'; data: PendingApprovalItem };

interface InteractionPromptProps {
  interactions: Array<Record<string, unknown>>;
  approvals?: Array<Record<string, unknown>>;
  activeAgent: Agent | null;
  agents: Agent[];
  onRespond: (interactionId: string | number, answer: string) => Promise<void>;
  onDecide?: (approvalId: string | number, decision: 'approve' | 'deny', reason?: string) => Promise<void>;
  onSelectAgent?: (agentId: string) => void;
  onToggleYolo?: (enabled: boolean) => Promise<void>;
  isYolo?: boolean;
  sending: boolean;
  t: Translations;
  isCollapsed?: boolean;
  onToggleCollapse?: (collapsed: boolean) => void;
}

export default function InteractionPrompt({
  interactions,
  approvals = [],
  activeAgent,
  agents,
  onRespond,
  onDecide,
  onSelectAgent,
  onToggleYolo,
  isYolo = false,
  sending,
  t,
  isCollapsed,
  onToggleCollapse,
}: InteractionPromptProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const collapsed = isCollapsed !== undefined ? isCollapsed : internalCollapsed;
  const setCollapsed = (val: boolean) => {
    setInternalCollapsed(val);
    onToggleCollapse?.(val);
  };
  const [forceInlineReply, setForceInlineReply] = useState(false);
  const [answerDraft, setAnswerDraft] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Unify and prioritize decision items (matching active agent first)
  const decisionItems = useMemo<DecisionItem[]>(() => {
    const list: DecisionItem[] = [
      ...interactions.map((ixn) => ({ kind: 'interaction' as const, data: ixn as PendingInteractionItem })),
      ...approvals.map((appr) => ({ kind: 'approval' as const, data: appr as PendingApprovalItem })),
    ];
    if (!activeAgent || list.length <= 1) return list;

    return list.slice().sort((a, b) => {
      const aAgentId = a.kind === 'interaction' ? a.data.agent_id : a.data.agent_name;
      const bAgentId = b.kind === 'interaction' ? b.data.agent_id : b.data.agent_name;
      const aMatch =
        (a.data.session_id && a.data.session_id === activeAgent.id) ||
        (aAgentId && (aAgentId === activeAgent.role_id || aAgentId === activeAgent.display_name));
      const bMatch =
        (b.data.session_id && b.data.session_id === activeAgent.id) ||
        (bAgentId && (bAgentId === activeAgent.role_id || bAgentId === activeAgent.display_name));
      if (aMatch && !bMatch) return -1;
      if (!aMatch && bMatch) return 1;
      return 0;
    });
  }, [interactions, approvals, activeAgent]);

  // Keep index within bounds
  useEffect(() => {
    if (currentIndex >= decisionItems.length) {
      setCurrentIndex(Math.max(0, decisionItems.length - 1));
    }
  }, [decisionItems.length, currentIndex]);

  if (decisionItems.length === 0) {
    return null;
  }

  const currentItem = decisionItems[currentIndex] ?? decisionItems[0];
  const isApproval = currentItem.kind === 'approval';
  const approvalData = isApproval ? (currentItem.data as PendingApprovalItem) : null;
  const interactionData = !isApproval ? (currentItem.data as PendingInteractionItem) : null;

  const itemId = isApproval ? approvalData?.id : (interactionData?.interaction_id ?? interactionData?.id);
  if (!itemId) return null;

  // Resolve asking agent name & object
  const sessionId = currentItem.data.session_id;
  const rawAgentId = isApproval ? approvalData?.agent_name : interactionData?.agent_id;
  const askingAgent =
    agents.find((a) => a.id === sessionId) ||
    agents.find((a) => a.role_id === rawAgentId || a.display_name === rawAgentId);
  const agentDisplayName =
    askingAgent?.display_name || askingAgent?.role_id || String(rawAgentId || 'Agent');

  // Check if current item belongs to active viewed agent
  const isCurrentAgent =
    !activeAgent ||
    (sessionId && sessionId === activeAgent.id) ||
    (rawAgentId && (rawAgentId === activeAgent.role_id || rawAgentId === activeAgent.display_name));

  // Parsed data for interaction
  const parsedInteraction = !isApproval
    ? parseInteractionDetails(interactionData?.prompt ?? interactionData?.message ?? interactionData?.question)
    : null;

  // Handlers for interaction
  const handleSendAnswer = async (responseValue?: string) => {
    if (sending || isApproval) return;
    const finalAnswer = (responseValue !== undefined ? responseValue : answerDraft).trim();
    if (!finalAnswer && !parsedInteraction?.defaultAnswer) return;
    const submission = finalAnswer || parsedInteraction?.defaultAnswer || '';
    await onRespond(itemId, submission);
    setAnswerDraft('');
    setShowRejectInput(false);
    setRejectReason('');
  };

  const handleRejectInteraction = async () => {
    if (sending || isApproval) return;
    const reason = rejectReason.trim();
    const finalReject = reason ? `拒绝: ${reason}` : '拒绝';
    await onRespond(itemId, finalReject);
    setAnswerDraft('');
    setShowRejectInput(false);
    setRejectReason('');
  };

  // Handlers for approval
  const handleApprove = async () => {
    if (sending || !isApproval || !onDecide) return;
    await onDecide(itemId, 'approve');
    setShowRejectInput(false);
    setRejectReason('');
  };

  const handleDeny = async () => {
    if (sending || !isApproval || !onDecide) return;
    const reason = rejectReason.trim();
    await onDecide(itemId, 'deny', reason || 'denied by user');
    setShowRejectInput(false);
    setRejectReason('');
  };

  // If item is for another agent and user hasn't clicked "Reply Here", render an alert ribbon above composer
  if (!isCurrentAgent && !forceInlineReply) {
    if (isApproval && approvalData) {
      const toolName = approvalData.tool_name || 'tool';
      const details = approvalData.details || '';
      return (
        <div className="interaction-dock-banner" data-testid="approval-other-agent-banner">
          <div className="interaction-dock-banner-left">
            <span className="interaction-pulse-beacon" />
            <span className="interaction-banner-badge">{agentDisplayName}</span>
            <span className="approval-tool-tag">{toolName}</span>
            <span className="interaction-banner-text">
              {t.approvalOtherAgentAsking(agentDisplayName, toolName)}: “{details.slice(0, 60)}
              {details.length > 60 ? '…' : ''}”
            </span>
          </div>
          <div className="interaction-dock-banner-actions">
            {askingAgent && onSelectAgent && (
              <button
                type="button"
                className="btn ghost sm interaction-jump-btn"
                onClick={() => onSelectAgent(askingAgent.id)}
              >
                {t.interactionJumpToAgent} →
              </button>
            )}
            <button
              type="button"
              className="btn green sm interaction-reply-here-btn"
              onClick={() => setForceInlineReply(true)}
            >
              {t.approvalApprove}
            </button>
          </div>
        </div>
      );
    }

    if (parsedInteraction) {
      return (
        <div className="interaction-dock-banner" data-testid="interaction-other-agent-banner">
          <div className="interaction-dock-banner-left">
            <span className="interaction-pulse-beacon" />
            <span className="interaction-banner-badge">{agentDisplayName}</span>
            <span className="interaction-banner-text">
              {t.interactionOtherAgentAsking(agentDisplayName)}: “{parsedInteraction.question.slice(0, 70)}
              {parsedInteraction.question.length > 70 ? '…' : ''}”
            </span>
          </div>
          <div className="interaction-dock-banner-actions">
            {askingAgent && onSelectAgent && (
              <button
                type="button"
                className="btn ghost sm interaction-jump-btn"
                onClick={() => onSelectAgent(askingAgent.id)}
              >
                {t.interactionJumpToAgent} →
              </button>
            )}
            <button
              type="button"
              className="btn green sm interaction-reply-here-btn"
              onClick={() => setForceInlineReply(true)}
            >
              {t.interactionAnswerHere}
            </button>
          </div>
        </div>
      );
    }
  }

  // If collapsed, show compact bar with expand toggle
  if (collapsed) {
    const desc = isApproval
      ? `${approvalData?.tool_name ?? 'tool'}: ${approvalData?.details ?? ''}`
      : parsedInteraction?.question ?? '';

    return (
      <div className="interaction-collapsed-bar" data-testid="interaction-collapsed-bar">
        <div className="interaction-collapsed-left">
          <span className="interaction-pulse-beacon" />
          <span className="interaction-agent-tag">{agentDisplayName}</span>
          {isApproval && <span className="approval-tool-tag">{approvalData?.tool_name}</span>}
          <span className="interaction-collapsed-desc">
            {desc.slice(0, 80)}
            {desc.length > 80 ? '…' : ''}
          </span>
        </div>
        <button
          type="button"
          className="btn ghost sm interaction-expand-btn"
          onClick={() => setCollapsed(false)}
        >
          {isApproval ? t.approvalTitle : t.interactionExpand} ↑
        </button>
      </div>
    );
  }

  // =========================================================================
  // APPROVAL CARD
  // =========================================================================
  if (isApproval && approvalData) {
    return (
      <div className="interaction-prompt-window approval-window" data-testid="approval-prompt-window">
        {/* Header */}
        <div className="interaction-window-header">
          <div className="interaction-header-left">
            <span className="interaction-pulse-beacon" />
            <span className="interaction-agent-tag">{agentDisplayName}</span>
            <span className="interaction-window-title">{t.approvalTitle}</span>
            <span className="approval-tool-tag">{approvalData.tool_name}</span>
            <span className="interaction-status-badge">{t.approvalWaiting}</span>
          </div>
          <div className="interaction-header-right">
            {decisionItems.length > 1 && (
              <div className="interaction-pagination">
                <button
                  type="button"
                  className="btn ghost xs pagination-btn"
                  disabled={currentIndex === 0}
                  onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                  title="Previous"
                >
                  ‹
                </button>
                <span className="pagination-label">
                  {currentIndex + 1} / {decisionItems.length}
                </span>
                <button
                  type="button"
                  className="btn ghost xs pagination-btn"
                  disabled={currentIndex >= decisionItems.length - 1}
                  onClick={() => setCurrentIndex((prev) => Math.min(decisionItems.length - 1, prev + 1))}
                  title="Next"
                >
                  ›
                </button>
              </div>
            )}
            <button
              type="button"
              className="btn ghost xs interaction-collapse-toggle"
              title={t.interactionCollapse}
              onClick={() => setCollapsed(true)}
            >
              {t.interactionCollapse} ↓
            </button>
          </div>
        </div>

        {/* Command Body */}
        <div className="approval-body">
          <div className="approval-subtitle">{t.approvalCommandLabel}:</div>
          <div className="approval-command-box">{approvalData.details || approvalData.tool_name}</div>

          {approvalData.risk_summary && (
            <div className="approval-risk-box">
              <span><b>{t.approvalRiskLabel}:</b> {approvalData.risk_summary}</span>
            </div>
          )}

          {approvalData.candidate_diff && (
            <pre className="approval-diff-box">{approvalData.candidate_diff}</pre>
          )}
        </div>

        {/* Denial Reason Panel */}
        {showRejectInput && (
          <div className="interaction-reject-panel">
            <div className="reject-panel-title">{t.approvalDenyPrompt}</div>
            <div className="reject-panel-row">
              <input
                type="text"
                className="input reject-reason-input"
                placeholder={t.approvalDenyDefault}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void handleDeny();
                  }
                }}
                autoFocus
              />
              <button
                type="button"
                className="btn danger sm"
                disabled={sending}
                onClick={() => void handleDeny()}
              >
                {sending ? t.approvalDenying : t.approvalDeny}
              </button>
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => setShowRejectInput(false)}
              >
                {t.interactionCollapse}
              </button>
            </div>
          </div>
        )}

        {/* Actions Footer */}
        <div className="approval-actions-footer">
          <div className="approval-footer-left">
            {onToggleYolo && !isYolo && (
              <button
                type="button"
                className="btn ghost sm yolo-shortcut-btn"
                title="开启 YOLO 模式后将不再提示审批"
                onClick={() => void onToggleYolo(true)}
              >
                ⚡ {t.approvalYoloHint}
              </button>
            )}
          </div>
          <div className="approval-footer-right">
            {!showRejectInput && (
              <button
                type="button"
                className="btn ghost sm interaction-reject-btn"
                disabled={sending}
                onClick={() => setShowRejectInput(true)}
              >
                {t.approvalDeny}
              </button>
            )}
            <button
              type="button"
              className="btn green sm interaction-submit-btn"
              disabled={sending}
              onClick={() => void handleApprove()}
            >
              {sending ? t.approvalApproving : `${t.approvalApprove} ↵`}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // INTERACTION / QUESTION CARD
  // =========================================================================
  if (!parsedInteraction) return null;

  return (
    <div className="interaction-prompt-window" data-testid="interaction-prompt-window">
      {/* Window Header */}
      <div className="interaction-window-header">
        <div className="interaction-header-left">
          <span className="interaction-pulse-beacon" />
          <span className="interaction-agent-tag">{agentDisplayName}</span>
          <span className="interaction-window-title">{t.interactionTitle}</span>
          <span className="interaction-status-badge">{t.interactionWaiting}</span>
        </div>
        <div className="interaction-header-right">
          {decisionItems.length > 1 && (
            <div className="interaction-pagination">
              <button
                type="button"
                className="btn ghost xs pagination-btn"
                disabled={currentIndex === 0}
                onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                title="Previous"
              >
                ‹
              </button>
              <span className="pagination-label">
                {t.interactionMultiplePending(currentIndex + 1, decisionItems.length)}
              </span>
              <button
                type="button"
                className="btn ghost xs pagination-btn"
                disabled={currentIndex >= decisionItems.length - 1}
                onClick={() => setCurrentIndex((prev) => Math.min(decisionItems.length - 1, prev + 1))}
                title="Next"
              >
                ›
              </button>
            </div>
          )}
          <button
            type="button"
            className="btn ghost xs interaction-collapse-toggle"
            title={t.interactionCollapse}
            onClick={() => setCollapsed(true)}
          >
            {t.interactionCollapse} ↓
          </button>
        </div>
      </div>

      {/* Question Content */}
      <div className="interaction-question-body">
        <div className="interaction-question-text">{parsedInteraction.question}</div>
      </div>

      {/* Options & Choices Bar */}
      {(parsedInteraction.defaultAnswer !== undefined ||
        parsedInteraction.options.length > 0 ||
        parsedInteraction.allowReject) && (
        <div className="interaction-choices-bar">
          <span className="interaction-choices-label">{t.interactionQuickOptions}:</span>
          {parsedInteraction.defaultAnswer !== undefined && (
            <button
              type="button"
              className="interaction-chip default-chip"
              title={`${t.interactionUseDefault}: ${parsedInteraction.defaultAnswer}`}
              onClick={() => {
                setAnswerDraft(parsedInteraction.defaultAnswer || '');
                textareaRef.current?.focus();
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>
                {t.interactionDefaultValue}: <b>{parsedInteraction.defaultAnswer}</b>
              </span>
            </button>
          )}

          {parsedInteraction.options.map((opt, idx) => (
            <button
              key={`${idx}-${opt}`}
              type="button"
              className="interaction-chip option-chip"
              onClick={() => {
                setAnswerDraft(opt);
                textareaRef.current?.focus();
              }}
            >
              <span>{opt}</span>
            </button>
          ))}

          {parsedInteraction.allowReject && !showRejectInput && (
            <button
              type="button"
              className="interaction-chip reject-chip"
              onClick={() => setShowRejectInput(true)}
              title={t.interactionReject}
            >
              <span>✕ {t.interactionReject}</span>
            </button>
          )}
        </div>
      )}

      {/* Rejection Sub-bar if user clicked Reject */}
      {showRejectInput && (
        <div className="interaction-reject-panel">
          <div className="reject-panel-title">{t.interactionRejectPrompt}</div>
          <div className="reject-panel-row">
            <input
              type="text"
              className="input reject-reason-input"
              placeholder={t.interactionRejectDefault}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void handleRejectInteraction();
                }
              }}
              autoFocus
            />
            <button
              type="button"
              className="btn danger sm"
              disabled={sending}
              onClick={() => void handleRejectInteraction()}
            >
              {sending ? t.interactionSubmitting : t.interactionReject}
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setShowRejectInput(false)}
            >
              {t.interactionCollapse}
            </button>
          </div>
        </div>
      )}

      {/* Response Input Area */}
      <div className="interaction-input-section">
        <textarea
          ref={textareaRef}
          className="interaction-textarea"
          rows={2}
          placeholder={
            parsedInteraction.defaultAnswer
              ? `${t.interactionPlaceholder} (${t.interactionDefaultValue}: ${parsedInteraction.defaultAnswer})`
              : t.interactionPlaceholder
          }
          value={answerDraft}
          disabled={sending}
          onChange={(e) => setAnswerDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void handleSendAnswer();
            }
          }}
          autoFocus
        />

        <div className="interaction-actions-footer">
          <div className="interaction-footer-left">
            <span className="interaction-keyboard-hint">
              Enter {t.interactionSubmit} · Shift+Enter 换行
            </span>
          </div>
          <div className="interaction-footer-right">
            {parsedInteraction.allowReject && !showRejectInput && (
              <button
                type="button"
                className="btn ghost sm interaction-reject-btn"
                disabled={sending}
                onClick={() => setShowRejectInput(true)}
              >
                {t.interactionReject}
              </button>
            )}
            <button
              type="button"
              className="btn green sm interaction-submit-btn"
              disabled={sending || (!answerDraft.trim() && parsedInteraction.defaultAnswer === undefined)}
              onClick={() => void handleSendAnswer()}
            >
              {sending ? t.interactionSubmitting : `${t.interactionSubmit} ↵`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
