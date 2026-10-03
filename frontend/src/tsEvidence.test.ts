import assert from 'node:assert/strict';
import { hasSaddleEvidence } from './tsEvidence.ts';

const supported = {
  evidence_level: 'saddle_supported',
  stages: ['ts_opt', 'frequency'].map(kind => ({ kind, status: 'supported' })),
};
assert.equal(hasSaddleEvidence(supported), true);
assert.equal(hasSaddleEvidence({ ...supported, evidence_level: 'endpoint_supported' }), true);
assert.equal(hasSaddleEvidence({ ...supported, evidence_level: 'proposed' }), false);
assert.equal(hasSaddleEvidence({ ...supported, evidence_vetoed: true }), false);
assert.equal(hasSaddleEvidence({ ...supported, stages: [supported.stages[0]] }), false);
assert.equal(hasSaddleEvidence({ ...supported, stages: [{ kind: 'ts_guess', status: 'supported' }] }), false);
assert.equal(hasSaddleEvidence({ ...supported, stages: [{ kind: 'ts_opt', status: 'supported' }, { kind: 'frequency', status: 'rejected' }] }), false);
assert.equal(hasSaddleEvidence({ saddle_supported: true }), false);
assert.equal(hasSaddleEvidence({}), false);
console.log('TS evidence display regression tests passed');
