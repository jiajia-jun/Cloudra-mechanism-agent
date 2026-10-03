export interface PendingInteractionItem {
  interaction_id?: string | number;
  id?: string | number;
  session_id?: string;
  agent_id?: string;
  prompt?: unknown;
  message?: unknown;
  question?: unknown;
  options?: unknown;
  default_answer?: unknown;
  allow_reject?: unknown;
  created_at?: string;
  [key: string]: unknown;
}

export interface PendingApprovalItem {
  id?: string | number;
  session_id?: string;
  agent_name?: string;
  tool_name?: string;
  details?: string;
  risk_summary?: string;
  candidate_diff?: string;
  tool_call_id?: string;
  execution_id?: string;
  state?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface ParsedInteraction {
  question: string;
  defaultAnswer?: string;
  options: string[];
  allowReject: boolean;
}

/**
 * Parses raw interaction payloads (JSON strings, structured objects, or raw CLI prompts)
 * into a clean question text, default value, choices list, and reject flag.
 */
export function parseInteractionDetails(raw: unknown): ParsedInteraction {
  let question = '';
  let defaultAnswer: string | undefined = undefined;
  let options: string[] = [];
  let allowReject = true;

  if (typeof raw === 'object' && raw !== null) {
    const obj = raw as Record<string, unknown>;
    question = String(obj.question ?? obj.prompt ?? obj.message ?? '');
    if (obj.default_answer !== undefined && obj.default_answer !== null) {
      defaultAnswer = String(obj.default_answer);
    }
    if (Array.isArray(obj.options)) {
      options = obj.options.map(String).map((s) => s.trim()).filter(Boolean);
    }
    if (obj.allow_reject !== undefined) {
      allowReject = Boolean(obj.allow_reject);
    }
  } else if (typeof raw === 'string') {
    let text = raw.trim();
    // 1. Try parsing JSON string first
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === 'object') {
        return parseInteractionDetails(parsed);
      }
    } catch {
      // Continue with string parsing
    }

    // 2. Extract default answer pattern: *(Default: ...)* or (Default: ...)
    const defMatch = text.match(/\*?\(Default:\s*(.+?)\)\*?$/i);
    if (defMatch) {
      defaultAnswer = defMatch[1].trim();
      text = text.substring(0, defMatch.index).trim();
    }

    // 3. Strip CLI reject instruction boilerplate if present: [如需拒绝...] or [如要拒绝...]
    const rejectNoticeMatch = text.match(/\[(?:如需拒绝|如要拒绝|如需撤销|如需跳过|如需放弃).*?\]/i);
    if (rejectNoticeMatch) {
      text = text.replace(rejectNoticeMatch[0], '').trim();
    }

    // 4. Extract bullet or numbered options if present
    const lines = text.split('\n');
    const optionLines: string[] = [];
    const qLines: string[] = [];
    let inOptions = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (/^(?:options|choices|可选项|选项)\s*[:：]/i.test(trimmed)) {
        inOptions = true;
        continue;
      }
      if (inOptions) {
        const itemMatch = trimmed.match(/^(?:[-*•]|\d+[.)])\s+(.+)$/);
        if (itemMatch) {
          optionLines.push(itemMatch[1].trim());
          continue;
        }
      }
      qLines.push(line);
    }

    if (optionLines.length > 0) {
      options = optionLines;
      question = qLines.join('\n').trim();
    } else {
      question = text;
    }
  } else if (raw !== undefined && raw !== null) {
    question = String(raw);
  }

  return {
    question: question || 'Agent is requesting your confirmation or answer.',
    defaultAnswer,
    options,
    allowReject,
  };
}
