/**
 * QuickJS-WASM sandbox for one bounded guest program.
 *
 * One Sandbox = one fresh runtime + context (no cross-program state).  The
 * guest sees a null-prototype frozen `tools` object and `text(value)`; no
 * filesystem, network, Node globals, module loader, timers or event
 * appenders.  Every guest/host crossing is a JSON string clone — host
 * object or Promise references never enter the guest.
 *
 * Evaluation budget: the host measures wall time of the initial evaluation
 * and every microtask pump (never tool waits) and asks QuickJS to interrupt
 * once the cumulative budget is spent.  All handles are disposed in
 * `dispose()`; host callbacks reject once the program is terminal.
 */

import { getQuickJS } from 'quickjs-emscripten';

/** Guest prelude: builds `tools` / `text` over the two native functions,
 * then erases the native globals.  Evaluated as a separate global script so
 * the program module keeps its original line numbers. */
export const GUEST_PRELUDE = `(() => {
  const callNative = globalThis.__cloudra_tool_call__;
  const textNative = globalThis.__cloudra_text__;
  const toolNamesJson = globalThis.__cloudra_tool_names__;
  delete globalThis.__cloudra_tool_call__;
  delete globalThis.__cloudra_text__;
  delete globalThis.__cloudra_tool_names__;

  class ToolCallError extends Error {
    constructor(info) {
      super(typeof info.message === 'string' ? info.message : 'tool call failed');
      this.name = 'ToolCallError';
      this.code = typeof info.code === 'string' ? info.code : 'tool_error';
      this.call_id = info.call_id ?? null;
      this.tool_name = info.tool_name ?? null;
      this.effect_state = info.effect_state ?? null;
      this.raw_result_event_id = info.raw_result_event_id ?? null;
      if (typeof info.line === 'number') this.line = info.line;
      if (typeof info.column === 'number') this.column = info.column;
    }
  }

  const tools = Object.create(null);
  for (const name of JSON.parse(toolNamesJson)) {
    tools[name] = (args) => callNative(name, JSON.stringify(args === undefined ? {} : args)).then(
      (raw) => JSON.parse(raw),
      (raw) => {
        let info;
        try { info = JSON.parse(raw); } catch { info = { message: String(raw) }; }
        throw new ToolCallError(info);
      },
    );
  }
  Object.freeze(tools);
  const guestTools = new Proxy(tools, {
    get(target, name) {
      if (['stop', 'ask_user', 'schedule', 'js_exec'].includes(name)) {
        throw new ToolCallError({code: 'direct_only_in_guest', tool_name: name,
          effect_state: 'not_started',
          message: name + ' requires a top-level tool call after this program returns.'});
      }
      return target[name];
    },
  });
  Object.defineProperty(globalThis, 'tools', {
    value: guestTools, writable: false, enumerable: false, configurable: false,
  });
  Object.defineProperty(globalThis, 'text', {
    value: (value) => textNative(JSON.stringify(value === undefined ? null : value)),
    writable: false, enumerable: false, configurable: false,
  });
})();`;

export class Sandbox {
  /**
   * @param {object} options
   * @param {object} options.limits snake_case limits from the start frame.
   * @param {string[]} options.tools guest-callable tool names.
   * @param {(name: string, argsJson: string, bridge: {resolve: (json: string) => void, reject: (json: string) => void}) => void} options.onToolCall
   * @param {(json: string) => void} options.onText
   * @param {() => boolean} options.isTerminal host terminal flag: once true,
   *   evaluation is interrupted and native callbacks keep rejecting.
   */
  static async create({ limits, tools, onToolCall, onText, isTerminal }) {
    const QuickJS = await getQuickJS();
    const runtime = QuickJS.newRuntime();
    runtime.setMemoryLimit(limits.heap_bytes);
    runtime.setMaxStackSize(limits.stack_bytes);
    const sandbox = new Sandbox(runtime, limits, isTerminal);
    sandbox._install(onToolCall, onText, tools);
    return sandbox;
  }

  constructor(runtime, limits, isTerminal) {
    this.runtime = runtime;
    this.context = runtime.newContext();
    this.limits = limits;
    this.isTerminal = isTerminal;
    this.evalMsUsed = 0;
    this._segmentStart = 0;
    this._moduleHandle = null;
    this._settled = false;
    this._settledResult = null;
    this._disposed = false;
    runtime.setInterruptHandler(() => this._shouldInterrupt());
  }

  _shouldInterrupt() {
    if (this.isTerminal()) return true;
    const spent = this.evalMsUsed + (Date.now() - this._segmentStart);
    return spent >= this.limits.eval_ms;
  }

  _install(onToolCall, onText, tools) {
    const ctx = this.context;
    const callFn = ctx.newFunction('__cloudra_tool_call__', (nameHandle, argsHandle) => {
      const name = ctx.getString(nameHandle);
      const argsJson = ctx.getString(argsHandle);
      const deferred = ctx.newPromise();
      const bridge = {
        resolve: (json) => {
          const handle = ctx.newString(json);
          try { deferred.resolve(handle); } finally { handle.dispose(); }
        },
        reject: (json) => {
          const handle = ctx.newString(json);
          try { deferred.reject(handle); } finally { handle.dispose(); }
        },
      };
      try {
        onToolCall(name, argsJson, bridge);
      } catch {
        bridge.reject(JSON.stringify({ code: 'host_error', message: 'tool bridge failure' }));
      }
      return deferred.handle;
    });
    ctx.setProp(ctx.global, '__cloudra_tool_call__', callFn);
    callFn.dispose();

    const textFn = ctx.newFunction('__cloudra_text__', (valueHandle) => {
      onText(ctx.getString(valueHandle));
      return ctx.undefined;
    });
    ctx.setProp(ctx.global, '__cloudra_text__', textFn);
    textFn.dispose();

    const namesHandle = ctx.newString(JSON.stringify(tools));
    ctx.setProp(ctx.global, '__cloudra_tool_names__', namesHandle);
    namesHandle.dispose();
  }

  /** Run one timed evaluation segment; waiting time is never counted. */
  _segment(fn) {
    this._segmentStart = Date.now();
    try {
      return fn();
    } finally {
      this.evalMsUsed += Date.now() - this._segmentStart;
    }
  }

  /**
   * Evaluate the prelude then the program as an ES module named
   * `program-<execution_id>.js` (original source line numbers preserved).
   * Returns null on successful start, or a dumped guest error object.
   */
  start(code, filename) {
    const ctx = this.context;
    const prelude = this._segment(() => ctx.evalCode(GUEST_PRELUDE, 'cloudra-prelude.js'));
    if (prelude.error) {
      const dumped = ctx.dump(prelude.error);
      prelude.error.dispose();
      return { phase: 'prelude', error: dumped };
    }
    prelude.value.dispose();
    const result = this._segment(() => ctx.evalCode(code, filename, { type: 'module' }));
    if (result.error) {
      const dumped = ctx.dump(result.error);
      result.error.dispose();
      return { phase: 'evaluate', error: dumped };
    }
    this._moduleHandle = result.value;
    this._trackSettlement();
    return null;
  }

  _trackSettlement() {
    const ctx = this.context;
    ctx.resolvePromise(this._moduleHandle).then((settled) => {
      this._settled = true;
      this._settledResult = settled;
    });
  }

  get settled() {
    return this._settled;
  }

  /** True once the cumulative guest evaluation budget is spent.  The
   * in-engine interrupt handler kills the running job at this boundary, but
   * rejections on floating promise chains are not reported by
   * executePendingJobs — the host must check this after every pump. */
  budgetExceeded() {
    return this.evalMsUsed >= this.limits.eval_ms;
  }

  /** Dump and dispose the settled module result (call once settled). */
  takeSettledResult() {
    const ctx = this.context;
    const settled = this._settledResult;
    this._settledResult = null;
    if (!settled) return null;
    if (settled.error) {
      const dumped = ctx.dump(settled.error);
      settled.error.dispose();
      return { error: dumped };
    }
    settled.value.dispose();
    return { error: null };
  }

  /** Bounded microtask pump; returns {jobs} or {error} (dumped). */
  pump(maxJobs) {
    const ctx = this.context;
    const result = this._segment(() => this.runtime.executePendingJobs(maxJobs));
    if (result.error) {
      const dumped = ctx.dump(result.error);
      result.error.dispose();
      return { jobs: 0, error: dumped };
    }
    return { jobs: result.value, error: null };
  }

  /** Dispose every remaining handle, then context and runtime. */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    if (this._settledResult) {
      const settled = this._settledResult;
      this._settledResult = null;
      if (settled.error) settled.error.dispose();
      else settled.value.dispose();
    }
    if (this._moduleHandle) {
      this._moduleHandle.dispose();
      this._moduleHandle = null;
    }
    this.context.dispose();
    this.runtime.dispose();
  }
}
