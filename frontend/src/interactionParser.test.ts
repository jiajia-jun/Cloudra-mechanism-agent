import assert from 'node:assert/strict';
import { parseInteractionDetails } from './interactionParser.ts';

// 1. Plain text with default answer pattern
{
  const raw = '请问该反应优化的初始电荷与自旋多重度是否按中性单重态(0, 1)进行？\n\n*(Default: 0 1)*';
  const parsed = parseInteractionDetails(raw);
  assert.equal(parsed.question, '请问该反应优化的初始电荷与自旋多重度是否按中性单重态(0, 1)进行？');
  assert.equal(parsed.defaultAnswer, '0 1');
  assert.deepEqual(parsed.options, []);
  assert.equal(parsed.allowReject, true);
}

// 2. Structured JSON object / string
{
  const raw = JSON.stringify({
    question: 'Which DFT functional should be used for single point refinement?',
    options: ['wb97x-d3/def2-TZVP', 'B3LYP-D3/def2-TZVP', 'M06-2X/def2-TZVP'],
    default_answer: 'wb97x-d3/def2-TZVP',
    allow_reject: false,
  });
  const parsed = parseInteractionDetails(raw);
  assert.equal(parsed.question, 'Which DFT functional should be used for single point refinement?');
  assert.deepEqual(parsed.options, ['wb97x-d3/def2-TZVP', 'B3LYP-D3/def2-TZVP', 'M06-2X/def2-TZVP']);
  assert.equal(parsed.defaultAnswer, 'wb97x-d3/def2-TZVP');
  assert.equal(parsed.allowReject, false);
}

// 3. Plain text with options list and boilerplate stripped
{
  const raw = `Please select an optimization strategy:
Options:
- 1. QST2 with initial guess
- 2. Scan reaction coordinate
- 3. Direct transition state search
[如需拒绝，请输入 '拒绝:<原因>']`;

  const parsed = parseInteractionDetails(raw);
  assert.equal(parsed.question, 'Please select an optimization strategy:');
  assert.equal(parsed.options.length, 3);
  assert.equal(parsed.options[0], '1. QST2 with initial guess');
  assert.equal(parsed.options[1], '2. Scan reaction coordinate');
  assert.equal(parsed.options[2], '3. Direct transition state search');
}

// 4. Fallback on simple string
{
  const raw = 'Are you sure you want to proceed?';
  const parsed = parseInteractionDetails(raw);
  assert.equal(parsed.question, 'Are you sure you want to proceed?');
  assert.equal(parsed.defaultAnswer, undefined);
  assert.deepEqual(parsed.options, []);
}

console.log('interactionParser tests ok');
