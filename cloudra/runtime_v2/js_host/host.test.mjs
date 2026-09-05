/**
 * Real-interpreter tests for the bounded QuickJS host (node --test).
 *
 * Each test spawns `node host.mjs`, speaks protocol version 1 over stdio
 * and asserts frame-level behavior: language support, absent host globals,
 * the tool bridge envelope, evaluation/output/call quotas, promise misuse
 * detection and error location reporting.  No network access is used.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import readline from 'node:readline';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HOST = path.join(path.dirname(fileURLToPath(import.meta.url)), 'host.mjs');
const FRAME_TIMEOUT_MS = 8000;

class HostSession {
  constructor() {
    this.child = spawn('node', [HOST], { stdio: ['pipe', 'pipe', 'pipe'] });
    this.stderr = '';
    this.child.stderr.on('data', (chunk) => {
      this.stderr += chunk;
    });
    this.frames = [];
    this.waiters = [];
    const rl = readline.createInterface({ input: this.child.stdout, terminal: false });
    rl.on('line', (line) => {
      const frame = JSON.parse(line);
      if (this.waiters.length > 0) this.waiters.shift()(frame);
      else this.frames.push(frame);
    });
    this.exited = new Promise((resolve) => this.child.on('exit', resolve));
  }

  static async start({ code, tools = [], limits = {}, executionId = 'test-exec' }) {
    const session = new HostSession();
    const ready = await session.nextFrame();
    assert.deepEqual(ready, { type: 'ready', version: 1 });
    session.send({
      type: 'start',
      version: 1,
      execution_id: executionId,
      code,
      tools,
      limits,
    });
    return session;
  }

  send(frame) {
    this.child.stdin.write(`${JSON.stringify(frame)}\n`);
  }

  nextFrame(timeoutMs = FRAME_TIMEOUT_MS) {
    if (this.frames.length > 0) return Promise.resolve(this.frames.shift());
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`timed out waiting for a host frame; stderr: ${this.stderr}`)),
        timeoutMs,
      );
      this.waiters.push((frame) => {
        clearTimeout(timer);
        resolve(frame);
      });
    });
  }

  /**
   * Collect frames until the single finished frame.  `onToolCall(frame)`
   * returns the reply frame to send (default: echo envelope echoing the
   * arguments as data).
   */
  async collect({ onToolCall } = {}) {
    const seen = { toolCalls: [], outputs: [], finished: null };
    for (;;) {
      const frame = await this.nextFrame();
      if (frame.type === 'tool_call') {
        seen.toolCalls.push(frame);
        const reply = onToolCall
          ? onToolCall(frame)
          : {
              type: 'tool_result',
              request_id: frame.request_id,
              result: {
                call_id: `tc-${frame.request_id}`,
                is_success: true,
                summary: 'ok',
                data: frame.arguments,
                duration_ms: 1,
              },
            };
        if (reply) this.send(reply);
      } else if (frame.type === 'output') {
        seen.outputs.push(frame.value);
      } else if (frame.type === 'finished') {
        seen.finished = frame;
        break;
      } else {
        throw new Error(`unexpected frame: ${JSON.stringify(frame)}`);
      }
    }
    this.child.stdin.end();
    const exitCode = await this.exited;
    assert.equal(exitCode, 0, `host must exit 0 for program outcomes; stderr: ${this.stderr}`);
    return seen;
  }
}

test('standard language works and host globals are absent', async () => {
  const session = await HostSession.start({
    code: [
      'text([1, 2, 3].map(x => x * 2));',
      'text([typeof process, typeof require, typeof fetch]);',
      "text(({}).constructor.constructor('return typeof process')());",
    ].join('\n'),
  });
  const { outputs, finished } = await session.collect();
  assert.deepEqual(outputs, [[2, 4, 6], ['undefined', 'undefined', 'undefined'], 'undefined']);
  assert.equal(finished.status, 'completed');
});

test('tool bridge returns the documented envelope', async () => {
  const session = await HostSession.start({
    code: 'const r = await tools.echo({value: 7}); text(r.data.value);',
    tools: ['echo'],
  });
  const { toolCalls, outputs, finished } = await session.collect();
  assert.equal(toolCalls.length, 1);
  assert.deepEqual(toolCalls[0].arguments, { value: 7 });
  assert.deepEqual(outputs, [7]);
  assert.equal(finished.status, 'completed');
});

test('serial dependency chain resolves distinct requests in order', async () => {
  const session = await HostSession.start({
    code: [
      'const first = await tools.echo({value: 3});',
      'const second = await tools.echo({value: first.data.value + 1});',
      'text(second.data.value);',
    ].join('\n'),
    tools: ['echo'],
  });
  const { toolCalls, outputs, finished } = await session.collect();
  assert.deepEqual(toolCalls.map((f) => f.request_id), ['r1', 'r2']);
  assert.deepEqual(toolCalls[1].arguments, { value: 4 });
  assert.deepEqual(outputs, [4]);
  assert.equal(finished.status, 'completed');
});

test('replies may settle out of request order', async () => {
  const session = await HostSession.start({
    code: [
      "const pa = tools.echo({v: 'a'});",
      "const pb = tools.echo({v: 'b'});",
      'const ra = await pa;',
      'const rb = await pb;',
      'text([ra.data.v, rb.data.v]);',
    ].join('\n'),
    tools: ['echo'],
  });
  const replies = new Map();
  const { outputs, finished } = await session.collect({
    onToolCall: (frame) => {
      replies.set(frame.request_id, {
        type: 'tool_result',
        request_id: frame.request_id,
        result: {
          call_id: `tc-${frame.request_id}`,
          is_success: true,
          summary: 'ok',
          data: { v: frame.arguments.v },
          duration_ms: 1,
        },
      });
      if (replies.size === 2) {
        setImmediate(() => {
          session.send(replies.get('r2'));
          session.send(replies.get('r1'));
        });
      }
      return null;
    },
  });
  assert.deepEqual(outputs, [['a', 'b']]);
  assert.equal(finished.status, 'completed');
});

test('infinite loop is interrupted by the evaluation budget', { timeout: 15000 }, async () => {
  const session = await HostSession.start({ code: 'while (true) {}', limits: { eval_ms: 200 } });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'eval_time_exceeded');
});

test('detached microtask loop consumes the guest budget', { timeout: 15000 }, async () => {
  const session = await HostSession.start({
    code: 'function again() { Promise.resolve().then(again); } again();',
    limits: { eval_ms: 200 },
  });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'eval_time_exceeded');
});

test('uncaught guest error fails with source location', async () => {
  const session = await HostSession.start({
    code: 'const a = 1;\nconst b = 2;\nthrow new Error("boom");',
  });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'guest_error');
  assert.equal(finished.error.message, 'boom');
  assert.equal(finished.error.line, 3);
});

test('module loader is disabled', async () => {
  const session = await HostSession.start({ code: 'const fs = await import("node:fs");' });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'guest_error');
});

test('heap limit fails with out_of_memory', { timeout: 15000 }, async () => {
  const session = await HostSession.start({
    code: 'const s = []; while (true) s.push(new Array(100000).fill(1));',
    limits: { heap_bytes: 8 * 1024 * 1024, eval_ms: 60000 },
  });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'out_of_memory');
});

test('permanently pending promise without tools is unresolved_promise', async () => {
  const session = await HostSession.start({
    code: 'await new Promise(() => {});',
    limits: { eval_ms: 2000 },
  });
  const { finished } = await session.collect();
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'unresolved_promise');
});

test('unawaited tool call at top-level settle is a failure', async () => {
  const session = await HostSession.start({
    code: 'tools.echo({value: 1});',
    tools: ['echo'],
  });
  const { toolCalls, finished } = await session.collect();
  assert.equal(toolCalls.length, 1);
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'unawaited_tool_calls');
});

test('tool request budget is terminal and catching cannot grant more calls', async () => {
  const session = await HostSession.start({
    code: [
      'let caught = 0;',
      'for (let i = 0; i < 5; i++) {',
      '  try { await tools.echo({i}); } catch (e) { caught++; }',
      '}',
      'text(caught);',
    ].join('\n'),
    tools: ['echo'],
    limits: { tool_requests: 2 },
  });
  const { toolCalls, outputs, finished } = await session.collect();
  assert.equal(toolCalls.length, 2);
  assert.deepEqual(outputs, []);
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'tool_request_limit_exceeded');
});

test('pending request budget is enforced before acceptance', async () => {
  const session = await HostSession.start({
    code: 'tools.echo({a: 1});\ntools.echo({a: 2});',
    tools: ['echo'],
    limits: { pending_requests: 1 },
  });
  const { toolCalls, finished } = await session.collect();
  assert.equal(toolCalls.length, 1);
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'too_many_pending_requests');
});

test('oversized arguments are rejected before dispatch', async () => {
  const session = await HostSession.start({
    code: "await tools.echo({data: 'x'.repeat(100)});",
    tools: ['echo'],
    limits: { argument_bytes: 16 },
  });
  const { toolCalls, finished } = await session.collect();
  assert.equal(toolCalls.length, 0);
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'argument_too_large');
});

test('output entry and byte budgets are enforced', async () => {
  const byCount = await HostSession.start({
    code: 'text(1); text(2); text(3);',
    limits: { output_entries: 2 },
  });
  const countRun = await byCount.collect();
  assert.deepEqual(countRun.outputs, [1, 2]);
  assert.equal(countRun.finished.status, 'failed');
  assert.equal(countRun.finished.error.code, 'output_limit_exceeded');

  const byBytes = await HostSession.start({
    code: "text('x'.repeat(100));",
    limits: { output_bytes: 50 },
  });
  const byteRun = await byBytes.collect();
  assert.deepEqual(byteRun.outputs, []);
  assert.equal(byteRun.finished.status, 'failed');
  assert.equal(byteRun.finished.error.code, 'output_limit_exceeded');
});

test('tool_error rejects with a catchable ToolCallError', async () => {
  const session = await HostSession.start({
    code: [
      'try { await tools.echo({}); text("no-throw"); }',
      'catch (e) { text([e.name, e.code, e.call_id, e.effect_state]); }',
    ].join('\n'),
    tools: ['echo'],
  });
  const { outputs, finished } = await session.collect({
    onToolCall: (frame) => ({
      type: 'tool_error',
      request_id: frame.request_id,
      error: { code: 'policy_blocked', message: 'denied', call_id: 'tc-1', effect_state: 'not_started' },
    }),
  });
  assert.deepEqual(outputs, [['ToolCallError', 'policy_blocked', 'tc-1', 'not_started']]);
  assert.equal(finished.status, 'completed');
});

test('unknown reply request_id is a protocol error', async () => {
  const session = await HostSession.start({
    code: 'await tools.echo({value: 1});',
    tools: ['echo'],
  });
  const { finished } = await session.collect({
    onToolCall: () => ({
      type: 'tool_result',
      request_id: 'r999',
      result: { call_id: 'tc', is_success: true, summary: 'ok', data: {}, duration_ms: 1 },
    }),
  });
  assert.equal(finished.status, 'failed');
  assert.equal(finished.error.code, 'protocol_error');
});

test('host rejects a wrong protocol version with nonzero exit', async () => {
  const session = new HostSession();
  const ready = await session.nextFrame();
  assert.deepEqual(ready, { type: 'ready', version: 1 });
  session.send({ type: 'start', version: 2, execution_id: 'x', code: '', tools: [], limits: {} });
  const finished = await session.nextFrame();
  assert.equal(finished.type, 'finished');
  assert.equal(finished.status, 'failed');
  session.child.stdin.end();
  const exitCode = await session.exited;
  assert.equal(exitCode, 1);
});
