"""Method-whitelist interception as a runtime_v2 policy stage.

`method_policy.py` only computes verdicts; this stage is the caller that
actually blocks. The benchmark backend appends it to the turn pipeline so the
task's `method_policy` whitelist is enforced at execution time:

- `qm_input_writer` / `submit_compute_job` verdicts come straight from
  `intercept` (structured method field / input-file content).
- bash calls are judged on the QM input *payloads* they write (via
  `intercept`) plus the on-disk inputs they *reference* (`g16 foo.gjf`) via
  `referenced_input_paths` + `check_input_files` — the wiring the
  method_policy module docstring leaves to the caller.

Blocking is never penalized: the block reason is fed back to the agent as
ordinary tool feedback (decision "continue"), so the agent can fall back to a
whitelisted method. One stage instance covers the whole benchmark core —
sub-agents spawned by the benchmark coordinator share the project workspace
and run under the same pipeline.
"""

from __future__ import annotations

from pathlib import Path

from cloudra.benchmark.method_policy import (
    check_input_files,
    intercept,
    referenced_input_paths,
)
from cloudra.benchmark.schema import MethodPolicy
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall


class MethodPolicyStage:
    name = "method_policy"

    def __init__(self, policy: MethodPolicy, base_dir: Path | str | None = None) -> None:
        self.policy = policy
        self._base_dir = Path(base_dir) if base_dir is not None else None

    def _base(self, ctx: PipelineContext) -> Path | None:
        if self._base_dir is not None:
            return self._base_dir
        return Path(ctx.workspace_dir) if ctx.workspace_dir else None

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        base = self._base(ctx)
        verdict = intercept(call.name, call.arguments, self.policy, base_dir=base)
        if not verdict.allowed:
            return PolicyResult.block(f"[method_policy] {verdict.reason}")
        if call.name in ("bash", "bashtools") and "bash" in set(self.policy.intercept_layers):
            command = str(call.arguments.get("command") or call.arguments.get("script") or "")
            refs = []
            for raw in referenced_input_paths(command):
                p = Path(raw)
                refs.append(p if p.is_absolute() or base is None else base / p)
            if refs:
                verdict = check_input_files(refs, self.policy)
                if not verdict.allowed:
                    return PolicyResult.block(f"[method_policy] {verdict.reason}")
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        return None
