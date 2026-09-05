/**
 * Trusted stdio transport for one bounded guest program.
 *
 * Lifecycle: print {type:"ready",version:1} -> read one start frame ->
 * evaluate the program in a fresh QuickJS sandbox -> relay bounded
 * tool_call/output frames -> print exactly one finished frame -> exit.
 *
 * The host owns every QuickJS deferred promise and pumps pending jobs
 * explicitly.  Tool quotas, output quotas and the evaluation budget are
 * enforced before accepting any guest callback; a terminal condition
 * rejects all pending and future native callbacks regardless of guest
 * catches.  Exit code 0 covers all program-level outcomes (completed or
 * failed); nonzero means host/transport failure only.
 */

import readline from 'node:readline';
import { Sandbox } from './sandbox.mjs';

const PROTOCOL_VERSION = 1;
const PUMP_JOB_BUDGET = 256;

const DEFAULT_LIMITS = {
  source_bytes: 64 * 1024,
  argument_bytes: 64 * 1024,
  rpc_line_bytes: 2 * 1024 * 1024,
  tool_result_bytes: 1024 * 1024,
  output_bytes: 64 * 1024,
  output_entries: 256,
  tool_requests: 64,
  pending_requests: 16,
  heap_bytes: 64 * 1024 * 1024,
  stack_bytes: 512 * 1024,
  eval_ms: 5000,
};

function send(frame) {
  process.stdout.write(`${JSON.stringify(frame)}\n`);
}

function fail(message) {
  process.stderr.write(`${message}\n`);
}

function byteLength(text) {
  return Buffer.byteLength(text, 'utf8');
}

function createLineQueue(stream) {
  const buffer = [];
  const waiters = [];
  const rl = readline.createInterface({ input: stream, terminal: false, crlfDelay: Infinity });
  rl.on('line', (line) => {
    if (waiters.length > 0) waiters.shift()(line);
    else buffer.push(line);
  });
  rl.on('close', () => {
    while (waiters.length > 0) waiters.shift()(null);
  });
  return {
    next() {
      if (buffer.length > 0) return Promise.resolve(buffer.shift());
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}

function extractLocation(dumped) {
  if (typeof dumped?.lineNumber === 'number') {
    return {
      line: dumped.lineNumber,
      column: typeof dumped.columnNumber === 'number' ? dumped.columnNumber : undefined,
    };
  }
  const stack = String(dumped?.stack ?? '');
  const match = stack.match(/program-[^\s()]*\.js:(\d+):(\d+)/);
  if (match) return { line: Number(match[1]), column: Number(match[2]) };
  return {};
}

/** Convert a dumped guest error into the sanitized finished.error shape. */
function guestErrorFromDump(dumped) {
  const error = {
    code: typeof dumped?.code === 'string' ? dumped.code : 'guest_error',
    message: String(dumped?.message ?? dumped ?? 'guest error'),
  };
  if (typeof dumped?.call_id === 'string') error.call_id = dumped.call_id;
  if (typeof dumped?.tool_name === 'string') error.tool_name = dumped.tool_name;
  if (typeof dumped?.effect_state === 'string') error.effect_state = dumped.effect_state;
  const { line, column } = extractLocation(dumped);
  if (line !== undefined) {
    error.line = line;
    if (column !== undefined) error.column = column;
  }
  if (error.code === 'guest_error' && dumped?.name === 'InternalError') {
    if (error.message === 'interrupted') error.code = 'eval_time_exceeded';
    else if (error.message.includes('out of memory')) error.code = 'out_of_memory';
  }
  return error;
}

function parseFrame(line, limits) {
  if (byteLength(line) > limits.rpc_line_bytes) {
    throw new Error(`frame exceeds rpc_line_bytes ${limits.rpc_line_bytes}`);
  }
  const frame = JSON.parse(line);
  if (frame === null || typeof frame !== 'object' || Array.isArray(frame)) {
    throw new Error('frame must be a JSON object');
  }
  return frame;
}

function validateStart(frame) {
  if (frame.type !== 'start' || frame.version !== PROTOCOL_VERSION) {
    throw new Error('first frame must be start with version 1');
  }
  if (typeof frame.execution_id !== 'string' || frame.execution_id.length === 0) {
    throw new Error('start.execution_id must be a non-empty string');
  }
  if (typeof frame.code !== 'string') throw new Error('start.code must be a string');
  if (!Array.isArray(frame.tools) || !frame.tools.every((name) => typeof name === 'string' && name)) {
    throw new Error('start.tools must be a list of non-empty strings');
  }
  const limits = { ...DEFAULT_LIMITS, ...(frame.limits ?? {}) };
  if (byteLength(frame.code) > limits.source_bytes) {
    throw new Error(`program source exceeds source_bytes ${limits.source_bytes}`);
  }
  return limits;
}

function validateToolReply(frame, pending) {
  if (frame?.type !== 'tool_result' && frame?.type !== 'tool_error') {
    throw new Error(`expected tool_result/tool_error, got ${frame?.type ?? 'null'}`);
  }
  const requestId = frame.request_id;
  if (typeof requestId !== 'string' || !pending.has(requestId)) {
    throw new Error(`unknown reply request_id ${String(requestId)}`);
  }
  const payloadKey = frame.type === 'tool_result' ? 'result' : 'error';
  if (frame[payloadKey] === null || typeof frame[payloadKey] !== 'object') {
    throw new Error(`${frame.type}.${payloadKey} must be an object`);
  }
  return requestId;
}

async function main() {
  const queue = createLineQueue(process.stdin);
  send({ type: 'ready', version: PROTOCOL_VERSION });

  const startLine = await queue.next();
  if (startLine === null) throw new Error('stdin closed before start frame');
  const startFrame = parseFrame(startLine, DEFAULT_LIMITS);
  const limits = validateStart(startFrame);

  let terminalError = null;
  let finished = false;
  let topLevelSettled = false;
  const pending = new Map(); // request_id -> {name, bridge}
  let totalCalls = 0;
  let requestSeq = 0;
  let outputBytes = 0;
  let outputEntries = 0;

  const rejectPending = (error) => {
    for (const { bridge } of pending.values()) {
      bridge.reject(JSON.stringify(error));
    }
    pending.clear();
  };

  const failTerminal = (error) => {
    if (terminalError) return;
    terminalError = error;
    rejectPending(error);
  };

  const onToolCall = (name, argsJson, bridge) => {
    if (terminalError || finished || topLevelSettled) {
      bridge.reject(JSON.stringify(
        terminalError ?? { code: 'terminated', message: 'program already settled' },
      ));
      return;
    }
    totalCalls += 1;
    if (totalCalls > limits.tool_requests) {
      const error = {
        code: 'tool_request_limit_exceeded',
        message: `program exceeded the ${limits.tool_requests} tool request budget`,
        tool_name: name,
      };
      failTerminal(error);
      bridge.reject(JSON.stringify(error));
      return;
    }
    if (pending.size >= limits.pending_requests) {
      const error = {
        code: 'too_many_pending_requests',
        message: `program has more than ${limits.pending_requests} pending tool requests`,
        tool_name: name,
      };
      failTerminal(error);
      bridge.reject(JSON.stringify(error));
      return;
    }
    if (byteLength(argsJson) > limits.argument_bytes) {
      const error = {
        code: 'argument_too_large',
        message: `tool call arguments exceed argument_bytes ${limits.argument_bytes}`,
        tool_name: name,
      };
      failTerminal(error);
      bridge.reject(JSON.stringify(error));
      return;
    }
    requestSeq += 1;
    const requestId = `r${requestSeq}`;
    pending.set(requestId, { name, bridge });
    send({ type: 'tool_call', request_id: requestId, name, arguments: JSON.parse(argsJson) });
  };

  const onText = (json) => {
    if (terminalError || finished) return;
    outputEntries += 1;
    outputBytes += byteLength(json);
    if (outputEntries > limits.output_entries || outputBytes > limits.output_bytes) {
      failTerminal({
        code: 'output_limit_exceeded',
        message: `program output exceeds the ${limits.output_entries} entries / ${limits.output_bytes} bytes budget`,
      });
      return;
    }
    send({ type: 'output', value: JSON.parse(json) });
  };

  const sandbox = await Sandbox.create({
    limits,
    tools: startFrame.tools,
    onToolCall,
    onText,
    isTerminal: () => terminalError !== null || finished,
  });

  const filename = `program-${startFrame.execution_id}.js`;
  const startError = sandbox.start(startFrame.code, filename);
  if (startError) {
    failTerminal(guestErrorFromDump(startError.error));
  }

  // Main loop: alternate bounded pumps with tool-reply waits.
  while (!startError && !sandbox.settled) {
    const { jobs, error } = sandbox.pump(PUMP_JOB_BUDGET);
    await Promise.resolve(); // let the settlement tracker observe the pump
    if (error) {
      if (!terminalError) failTerminal(guestErrorFromDump(error));
      rejectPending(terminalError);
      continue;
    }
    if (sandbox.budgetExceeded()) {
      failTerminal({
        code: 'eval_time_exceeded',
        message: `guest evaluation budget of ${limits.eval_ms} ms exhausted`,
      });
      break;
    }
    if (sandbox.settled) break;
    if (pending.size === 0) {
      if (jobs === 0) {
        failTerminal({
          code: 'unresolved_promise',
          message: 'the top-level promise never settles and no tool call is outstanding',
        });
        break;
      }
      continue;
    }
    const line = await queue.next();
    if (line === null) throw new Error('stdin closed while tool calls are outstanding');
    try {
      const frame = parseFrame(line, limits);
      const requestId = validateToolReply(frame, pending);
      const entry = pending.get(requestId);
      pending.delete(requestId);
      if (frame.type === 'tool_result') entry.bridge.resolve(JSON.stringify(frame.result));
      else entry.bridge.reject(JSON.stringify(frame.error));
    } catch (err) {
      failTerminal({ code: 'protocol_error', message: String(err.message ?? err) });
    }
  }

  if (sandbox.settled) {
    const { error } = sandbox.takeSettledResult();
    if (error && !terminalError) failTerminal(guestErrorFromDump(error));
  }
  topLevelSettled = true;
  if (!terminalError && pending.size > 0) {
    failTerminal({
      code: 'unawaited_tool_calls',
      message: `program completed with ${pending.size} tool call(s) still outstanding`,
    });
  }
  rejectPending(terminalError ?? { code: 'terminated', message: 'program finished' });

  // Drain leftover guest jobs under the same evaluation budget: detached
  // promise chains consume guest budget and must not outlive settlement.
  while (!terminalError) {
    const { jobs, error } = sandbox.pump(PUMP_JOB_BUDGET);
    if (error) {
      failTerminal(guestErrorFromDump(error));
      break;
    }
    if (sandbox.budgetExceeded()) {
      failTerminal({
        code: 'eval_time_exceeded',
        message: `guest evaluation budget of ${limits.eval_ms} ms exhausted`,
      });
      break;
    }
    if (jobs === 0) break;
    await Promise.resolve();
  }

  // Mark terminal before emitting the single finished frame; late reply
  // frames are ignored from here on (teardown only).
  finished = true;
  const frame = { type: 'finished', status: terminalError ? 'failed' : 'completed' };
  if (terminalError) frame.error = terminalError;
  send(frame);
  sandbox.dispose();
}

main()
  .then(() => {
    process.exit(0);
  })
  .catch((err) => {
    fail(`js_host fatal: ${err?.stack ?? err}`);
    try {
      send({
        type: 'finished',
        status: 'failed',
        error: { code: 'host_error', message: String(err?.message ?? err) },
      });
    } catch {
      // stdout itself is broken; nothing more to do.
    }
    process.exit(1);
  });
