"""Method-whitelist interception as a runtime_v2 policy stage.

`runtime_v2/method_policy.py` only computes verdicts; this stage is the caller
that actually blocks. Policy supply comes in two forms:

- Explicit policy (benchmark backend): `MethodPolicyStage(task.method_policy,
  base_dir=sandbox)` — one stage instance covers the whole benchmark core.
- Core projection: `MethodPolicyStage(core=core)` resolves the policy only
  for projects carrying `ProjectSettings.benchmark_task_id`. Ordinary projects
  are never intercepted, even when a stored method policy is present.
  `default_stages(core)` wires this form.

Otherwise the interception semantics are identical:

- `qm_input_writer` / `submit_compute_job` verdicts come straight from
  `intercept` (structured method field / input-file content).
- bash calls are judged on the QM input *payloads* they write (via
  `intercept`) plus the on-disk inputs they *reference* (`g16 foo.gjf`) via
  `referenced_input_paths` + `check_input_files` — the wiring the
  method_policy module docstring leaves to the caller.

Blocking is never penalized: the block reason is fed back to the agent as
ordinary tool feedback (decision "continue"), so the agent can fall back to a
whitelisted method. `base_dir` defaults to `ctx.workspace_dir`.
"""

from __future__ import annotations

import json
from pathlib import Path

from cloudra.runtime_v2.method_policy import (
    check_input_files,
    intercept,
    referenced_input_paths,
)
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall
from cloudra.runtime_v2.schemas import MethodPolicy


class MethodPolicyStage:
    name = "method_policy"

    def __init__(
        self,
        policy: MethodPolicy | None = None,
        base_dir: Path | str | None = None,
        core=None,
    ) -> None:
        self._policy = policy
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._core = core

    def _resolve_policy(self, ctx: PipelineContext) -> MethodPolicy | None:
        # 显式 policy（benchmark）优先；否则从 core 的项目投影取——事件溯源
        # 状态，不是 stage 私有簿记，重启重放后判定可复现。
        if self._policy is not None:
            return self._policy
        if self._core is None:
            return None
        project = self._core.projects.get(ctx.agent.project_id)
        if project is None or project.settings.benchmark_task_id is None:
            return None
        if project.settings.method_policy is None:
            raise ValueError("Benchmark project is missing its MethodPolicy")
        return project.settings.method_policy

    def _base(self, ctx: PipelineContext) -> Path | None:
        if self._base_dir is not None:
            return self._base_dir
        return Path(ctx.workspace_dir) if ctx.workspace_dir else None

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        import asyncio

        policy = self._resolve_policy(ctx)
        if policy is None:
            return PolicyResult.allow()
        base = self._base(ctx)
        verdict = await asyncio.to_thread(intercept, call.name, call.arguments, policy, base_dir=base)
        if not verdict.allowed:
            return PolicyResult.block(f"[method_policy] {verdict.reason}")
        if call.name == "bash" and "bash" in set(policy.intercept_layers):
            command = str(call.arguments.get("command") or call.arguments.get("script") or "")
            refs = []
            for raw in referenced_input_paths(command):
                p = Path(raw)
                refs.append(p if p.is_absolute() or base is None else base / p)
            if refs:
                verdict = await asyncio.to_thread(check_input_files, refs, policy)
                if not verdict.allowed:
                    return PolicyResult.block(f"[method_policy] {verdict.reason}")
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result) -> None:
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        policy = self._resolve_policy(ctx)
        scope = dict(project_id=ctx.agent.project_id, active=policy is not None,
                     allowed_methods=list(policy.allowed_methods) if policy is not None else [])
        content = (
            '[Current MethodPolicy scope]\n' + json.dumps(scope, ensure_ascii=False, sort_keys=True) + '\n'
            'MethodPolicy is a whitelist for the current Benchmark task only. '
            'When active=false, this project has no method/basis whitelist: follow the current user\'s '
            'calculation requirements, budget and available software. Benchmark defaults, examples, '
            'stored inactive settings and past rejection messages do not create a policy for this request. '
            'When active=true, use the actual allowed_methods above. If a required calculation conflicts '
            'with them, report that task/policy mismatch instead of automatically changing its method.'
        )
        if ctx.notices is not None:
            ctx.notices.pin(ctx.agent.id, 'method-policy-scope', content)
        else:
            messages.append(dict(role='system', content=content))
