import assert from 'node:assert/strict';
import { failureNote } from './failureKind.ts';

// 每个分类都必须给出「下一步」，且不解析 error 文本。
for (const kind of [
  'provider_permanent',
  'provider_transient_exhausted',
  'event_persistence',
  'pipeline_internal',
  'completion_no_progress',
  'runtime_interrupted',
]) {
  const note = failureNote({ outcome: 'failed', error: 'raw text that must not be parsed', failure_kind: kind });
  assert.ok(note, `missing note for ${kind}`);
  assert.ok(note.text.length > 0);
}

assert.equal(failureNote({ outcome: 'failed', failure_kind: 'provider_permanent' })?.level, 'error');
assert.equal(failureNote({ outcome: 'failed', failure_kind: 'runtime_interrupted' })?.level, 'warn');

// 成功、缺分类、未知分类：一律不猜（不显示失败的下一步）。
assert.equal(failureNote({ outcome: 'succeeded', failure_kind: null }), null);
assert.equal(failureNote({ outcome: 'failed' }), null);
assert.equal(failureNote({ outcome: 'failed', failure_kind: 'brand_new_kind' }), null);
assert.equal(failureNote(null), null);

console.log('failureKind tests ok');
