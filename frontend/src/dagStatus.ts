/**
 * Pure DAG status helpers: convert API fields into human-readable labels.
 *
 * The UI must not infer approved/complete from ambiguous or missing fields.
 */

export type ScientificStatus = 'supported' | 'unresolved' | 'out_of_scope' | 'unknown';

export interface DagStatusInput {
  checks?: Record<string, string>;
  reviewState?: string | null;
  deliveryDisposition?: string | null;
  scientificOutcome?: string | null;
  approvalId?: string | null;
  hasContradictions?: boolean;
}

export interface DagStatusLabel {
  label: string;
  tone: 'ok' | 'warn' | 'danger' | 'neutral';
  detail: string;
}

export function dagStatusLabel(input: DagStatusInput): DagStatusLabel {
  const review = input.reviewState ?? null;
  const disposition = input.deliveryDisposition ?? null;
  const scientific = input.scientificOutcome ?? null;
  const approved = Boolean(input.approvalId);

  if (input.hasContradictions) {
    return { label: 'unresolved contradiction', tone: 'danger', detail: 'Refuting evidence is registered and has not been resolved.' };
  }
  if (review === 'waiting_review' || review === 'queued') {
    return { label: 'review in progress', tone: 'warn', detail: 'The delivery/evidence is waiting for Supervisor review.' };
  }
  if (disposition === 'partial' && approved) {
    return { label: 'approved partial', tone: 'warn', detail: 'Partial delivery is approved; remaining gaps are still recorded.' };
  }
  if (disposition === 'partial') {
    return { label: 'partial delivery', tone: 'warn', detail: 'The run finished with unresolved scientific gaps.' };
  }
  if (scientific === 'method_limited') {
    return { label: 'method limited', tone: 'warn', detail: 'The conclusion is limited by the available method scope.' };
  }
  if (disposition === 'complete' && approved) {
    return { label: 'approved complete', tone: 'ok', detail: 'Complete delivery approved.' };
  }
  if (disposition === 'complete') {
    return { label: 'complete', tone: 'ok', detail: 'Delivery completed.' };
  }
  const checks = input.checks ?? {};
  const missing = Object.entries(checks)
    .filter(([, v]) => v === 'missing')
    .map(([k]) => k);
  if (missing.length) {
    return { label: 'checks pending', tone: 'warn', detail: `Missing checks: ${missing.join(', ')}` };
  }
  if (Object.keys(checks).length === 0 && disposition === null) {
    return { label: 'legacy unknown', tone: 'neutral', detail: 'No protocol v2 status fields are available.' };
  }
  return { label: 'unknown', tone: 'neutral', detail: 'No explicit status was provided.' };
}
