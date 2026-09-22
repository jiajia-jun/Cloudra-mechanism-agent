/**
 * 完成依据的展示口径（评审 5.3）：把服务端的 `completion` 投影渲染成标签。
 *
 * 「运行结束」不等于「目标已验证完成」：`succeeded` 只是模型停止输出，只有证据
 * 门禁确认过的结题才允许显示 verified complete。验证等级由服务端从收尾门禁的
 * 结构化 basis 派生（`cloudra/runtime_v2/completion.py`），前端只负责渲染，
 * 不重新推导，也不把未知/缺失的值猜成「已验证完成」。
 */

import type { CompletionSummary } from './types.ts';

export type VerificationLabel = 'verified' | 'partial' | 'unverified';

export interface CompletionChip {
  label: string;
  tone: 'ok' | 'warn' | 'neutral';
  detail: string;
}

export function completionChipFor(
  completion: CompletionSummary | null | undefined,
): CompletionChip | null {
  const label = completion?.verification_label;
  if (label === 'verified') {
    return {
      label: 'verified complete',
      tone: 'ok',
      detail: 'The delivery passed the evidence gate that applies to this run.',
    };
  }
  if (label === 'partial') {
    return {
      label: 'partial delivery',
      tone: 'warn',
      detail: 'The run ended with open gaps; the partial result was recorded or approved.',
    };
  }
  if (label === 'unverified') {
    return {
      label: 'not independently verified',
      tone: 'neutral',
      detail:
        'The run ended on the agent\'s own declaration; no evidence gate verified the result.',
    };
  }
  // 没有收尾依据（还在跑 / 从未收尾 / 未知标签）：什么都不显示，绝不猜。
  return null;
}

/**
 * 状态徽标文案：`succeeded` 只表示这一轮结束了，不表示目标已完成——按评审
 * 要求显示为 ended，验证等级交给完成依据标签表达。
 */
export function stateBadgeText(state: string): string {
  return state === 'succeeded' ? 'ended' : state;
}
