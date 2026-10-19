"""Guidance stage: behavioral steering via pinned context notices.

通道纪律：操作级修正进工具结果（跟随单次调用），行为级引导进 pin 的
常驻上下文通知（跨轮/跨 run/跨重启可见；NoticeManager 按键幂等去重，
重复 pin 不产生新消息、免费去抖）。

引导只警告；YOLO 开启时，直接 TS/IRC 与 shell 提交另由既有审批官按意图判断。

引导项：
- TS/PES 准备与分子计算提交 → 物理条件、模型边界与坐标耦合的思考提醒；
- submit_compute_job 提交 TS/IRC 类作业 → ts_prepare SOP 提示（含 QST
  禁令复述）；按声明引擎复用原生输入解析，只检查 Agent 提交的文件，
  在线程中完成读取与识别；读不出或无法识别时不提示，不修改调度准入；
- Coordinator 亲自提交正式计算 → 派单提醒（原 delegation_guard 从工具
  结果前置文案迁入）；
- bash 写文件/手写坐标 → 结构化工具提醒（原 bash_habit_guard/coord_guard
  的结果前置警告迁入）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os

from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, PolicyResult, ToolCall, ToolResult
from cloudra.tools.core.bash_habit_guard import bash_file_write_warning
from cloudra.tools.core.coord_guard import handwritten_coord_warning
from cloudra.tools.core.ts_workflow_guard import inspect_ts_operation

_PIN_TS_SOP = "guidance-ts-sop"
_PIN_TS_WORKFLOW = "guidance-ts-workflow"
_PIN_PHYSICAL_THINKING = "guidance-physical-thinking"
_PIN_DELEGATE = "guidance-delegate-compute"
_PIN_BASH_WRITE = "guidance-bash-file-write"
_PIN_BASH_COORDS = "guidance-handwritten-coords"
_PIN_REFLECTION = "guidance-scientific-reflection:"

_TS_WORKFLOW_NOTICE = (
    "[Warning: possible TS workflow bypass] This operation prepares or executes TS/IRC work outside ts_process. "
    "For formal solving and verification, inspect and repair the same ts_prepare/ts_resume run. "
    "Do not replace a blocked process with manual jobs or another script to avoid its missing inputs or scientific checks. "
    "Exploratory trials, capability probes, diagnosis and evidence-backed reruns remain valid; "
    "a manually completed calculation still needs the full TS/frequency/IRC evidence chain."
)

_TS_NOTICE = (
    "[Guidance] This looks like a TS/IRC job. For formal TS solving and complete "
    "verification, use the ts_prepare process (build → map → assemble → guess → validate → submit → "
    "refine, autonomously; if it stops blocked, fix the named declaration and "
    "ts_resume). QST2/QST3 are banned; the ceiling is mapped interpolation/NEB, "
    "with explicit grouped inputs: reaction, calculations, conformers, guess, ts_optimization, verification, execution. Scan uses guess.kind=scan with guess.calculation/scans/freeze; scan and formal methods are independently selected. Complete calculations use engine, one-token method, explicit basis_set (empty when unused), keywords and native settings. Stages may explicitly select {ref: name} from input.calculations. "
    "Use that process for formal TS/IRC work rather than manually chaining the jobs. "
    "Call ts_prepare once per path. Successful jobs automatically advance without an agent call. Use ts_inspect to read state, actual atom tables, methods, evidence and next required inputs. Revise the same run with ts_resume(run_id, changes, reason). Calculation patches retain omitted settings; engine/method/basis changes use {replace: complete_configuration}, and changing a profile reference uses {replace: {ref: name}}. changes={} restarts the same declared inputs; change the guess or scan to test another hypothesis, or explicitly provide a last geometry for continuation. Previous attempts are retained automatically. "
    "Use ts_stop(run_id, reason) to stop automatic advancement and request safe cancellation of that run's jobs. "
    "Standalone exploratory scans remain valid for unknown endpoints. Direct TS/IRC submissions are "
    "for exploratory trials or capability probes only. Return candidates through "
    "guess={kind:provided,xyz_path,evidence_refs}; eligible existing IRC uses verification.irc_log. "
    "If the process blocks, inspect and correct the named declaration or report the tool limitation; "
    "do not bypass formal verification through bash or direct engine execution. "
    "Choose IRC extent by the remaining uncertainty and cost, not a fixed point "
    "count. Weigh further tracing against unconstrained optimization of both "
    "current outer frames. A first-order saddle, bidirectional IRC interval "
    "evidence, and frequency-verified endpoint minima with the intended identities "
    "can establish verified connectivity without IRC itself converging. Endpoint "
    "optimization alone is insufficient; extend a direction when its assignment "
    "or connection remains unresolved. Report unsupported native IRC settings as a "
    "workflow limitation so the tool can be repaired."
)
_PHYSICAL_THINKING_NOTICE = (
    "[Guidance] At your next planning decision, before further calculations: "
    "identify the stated conditions (solvent/water, acid/base partners, counterions, "
    "temperature/concentration where relevant) and what remains unknown; compare them "
    "with what your molecular model represents or omits and how that could affect "
    "the result. Form plausible mechanism hypotheses and identify the participants, "
    "then consider coordinate coupling and preorganization before choosing a path. "
    "Use available semiempirical PES exploration within the user's current calculation "
    "requirements and budget to test those hypotheses. Only active Benchmark projects use MethodPolicy "
    "to restrict methods and bases, according to that task's actual policy; "
    "ordinary research projects have no default method/basis whitelist. Do not infer "
    "method restrictions from global configuration, examples or past tasks. Inspect the structures actually observed "
    "and use them to choose a meaningful next attempt. Keep unknown conditions "
    "explicit and model/method changes within the user's authorized scope."
)
_DELEGATE_NOTICE = (
    "[Guidance] You are the Coordinator submitting compute yourself. Quick "
    "checks are fine; formal or long QM jobs belong to the small_mol / dft / md "
    "sub-agents — dispatch with file paths, goals, and acceptance criteria."
)
_BASH_WRITE_NOTICE = (
    "[Guidance] bash is not for creating or editing files — use write/edit; "
    "coordinates come from smiles_to_mol / format_converter / "
    "internal_coordinates / qm_input_writer outputs, never hand-written."
)
_BASH_COORDS_NOTICE = (
    "[Guidance] Hand-written coordinate blocks in shell commands are not a "
    "structure source — use smiles_to_mol / format_converter / "
    "internal_coordinates (or ts_guess/qm_input_writer) instead."
)
_REFLECTION_CAUSES = {
    "scan": "The parsed scan found no internal peak.",
    "verify": "Structured TS verification failed.",
    "path": "The xTB path refinement exhausted its cycle ceiling.",
}
_REFLECTION_ADVICE = (
    "Check the source and relevant skills, then choose a distinguishing test of pose, reaction centres, "
    "a tool-generated guess or the step hypothesis; an observation is not a proven cause. "
    "Update PROCESS.md with evidence paths and share changed step hypotheses with the Coordinator."
)


def _pin_reflection(notices: NoticeManager, agent_id: str, key: str, content: str) -> None:
    """Keep only the latest scientific reflection; other guidance and tasks are untouched."""
    for previous in list(notices._pins.get(agent_id, {})):
        if previous.startswith(_PIN_REFLECTION) and previous != key:
            notices.unpin(agent_id, previous)
    notices.pin(agent_id, key=key, content=content)


def guide_ts_process(notices: NoticeManager | None, agent_id: str, data: dict) -> None:
    """One current hint per agent; only the matching run can retract it."""
    run_id = data.get("run_id")
    if notices is None or not isinstance(run_id, str) or not run_id:
        return
    notices.pin(agent_id, key=_PIN_TS_SOP, content=_TS_NOTICE)
    key = _PIN_REFLECTION + "ts-process:" + run_id
    verdict = data.get("result") or {}
    blocked = data.get("blocked") or {}
    candidate = (data.get("status") == "ended" and verdict.get("verified") is False
                 and verdict.get("outcome") in ("candidate_only", "search_failed"))
    wrong_mode = data.get("status") == "blocked" and blocked.get("failure_class") == "wrong_mode"
    failed_attempt = data.get("failed_attempt") or {}
    nonconverged = (data.get("status") == "blocked" and failed_attempt.get("purpose") == "ts_opt"
                    and failed_attempt.get("failure_class") == "nonconvergence")
    if not candidate and not wrong_mode and not nonconverged:
        if data.get("status") in ("running", "waiting", "stopped") or verdict.get("verified") is True:
            notices.unpin(agent_id, key)
        return
    attempt = failed_attempt if wrong_mode or nonconverged else {}
    paths = verdict.get('evidence_refs') or attempt.get('evidence_refs') or []
    source = attempt.get('log_path') or data.get('details_path') or next(iter(paths), None) or data.get('run_dir')
    source = f"Source: {source}" if source else f"Inspect TS run {run_id}"
    if nonconverged:
        content = (
            "[Guidance] This TS optimization did not converge; failure of this guess does not prove "
            f"that the reaction has no TS ({source}). Inspect actual geometry and relevant skills, "
            "then use structure/path tools to change the guess or search before drawing a mechanism conclusion."
        )
    else:
        content = f"[Guidance] The target TS step remains unverified; {source}. {_REFLECTION_ADVICE}"
    _pin_reflection(notices, agent_id, key, content)

class GuidanceStage:
    name = "guidance"

    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        notices = ctx.notices
        if notices is not None and self._needs_physical_thinking(call):
            notices.pin(
                ctx.agent.id,
                key=_PIN_PHYSICAL_THINKING,
                content=_PHYSICAL_THINKING_NOTICE,
            )
        if notices is not None and call.name == "ts_guess" and self._needs_physical_thinking(call):
            notices.pin(ctx.agent.id, key=_PIN_TS_SOP, content=_TS_NOTICE)
        if notices is not None and call.name == "submit_compute_job" and getattr(ctx.agent, "role_id", "") == "coordinator":
            notices.pin(ctx.agent.id, key=_PIN_DELEGATE, content=_DELEGATE_NOTICE)
        if notices is not None and call.name == "bash":
            self._guide_bash(ctx, call, notices)

        operation = {}
        job_type = call.arguments.get('job_type', 'gaussian')
        if call.name in {"qm_input_writer", "write", "edit", "bash", "submit_compute_job"} and not (
                call.name == "submit_compute_job" and (not isinstance(job_type, str)
                or job_type not in {'gaussian', 'orca', 'shell'})):
            operation = await asyncio.to_thread(inspect_ts_operation, call.name, call.arguments, ctx.workspace_dir)
        native_ts = bool(operation.get('ts_inputs'))
        known_ts = notices is not None and notices.pin_content(ctx.agent.id, _PIN_TS_SOP) is not None
        # 命中只说明有绕过的可能：先提醒，不能据此禁用提交或诊断脚本。
        possible_bypass = native_ts or bool(known_ts and operation.get('scripts') and operation.get('direct_execution'))
        warning = ''
        if possible_bypass:
            sources = ', '.join(item['path'] for item in operation.get('ts_inputs', []))
            message = f"{_TS_WORKFLOW_NOTICE}\nObserved operation: {call.name}" + (f"; TS/IRC inputs: {sources}" if sources else '')
            if notices is None or notices.pin_content(ctx.agent.id, _PIN_TS_WORKFLOW) != message:
                warning = message
            if notices is not None:
                notices.pin(ctx.agent.id, key=_PIN_TS_SOP, content=_TS_NOTICE)
                notices.pin(ctx.agent.id, key=_PIN_TS_WORKFLOW, content=message)

        # bash/write/edit 已在执行前调用同一个审批官；这里只补直接提交，避免重复审批。
        from cloudra.infra.yolo_guard import YoloGuard, is_yolo_enabled

        if (call.name == 'submit_compute_job' and (native_ts or call.arguments.get('job_type') == 'shell')
                and (ctx.settings.yolo or is_yolo_enabled())):
            approved, reason = await YoloGuard().judge(
                call.name, call.arguments, ctx.agent, None,
                risk_summary='Direct compute submission: distinguish a legitimate trial/diagnosis from bypassing formal TS verification.',
                workspace_dir=ctx.workspace_dir,
                event_log=notices._event_log if notices is not None else None,
            )
            if not approved:
                message = reason or 'YOLO review rejected this operation; inspect and repair the TS workflow or choose a justified diagnostic.'
                if notices is not None:
                    notices.pin(ctx.agent.id, key=_PIN_TS_WORKFLOW,
                                content='[YOLO workflow review] The current submission was rejected. '
                                        'Address the returned reason; switching to bash, Python, SSH or another tool does not resolve it.')
                return PolicyResult.block(message)
        if warning:
            return PolicyResult.warn(warning)
        return PolicyResult.allow()

    async def after_tool(self, ctx: PipelineContext, call: ToolCall, result: ToolResult) -> None:
        if ctx.notices is None or result.error is not None:
            return None
        data = result.data
        if not isinstance(data, dict):
            return None
        if call.name in ("ts_prepare", "ts_resume", "ts_inspect", "ts_stop"):
            if result.is_success:
                guide_ts_process(ctx.notices, ctx.agent.id, data)
            return None
        if call.name != "ts_guess":
            return None
        mode = call.arguments.get("mode")
        confirmed = False
        if mode == "scan_parse" or (mode == "scan" and call.arguments.get("log_path")):
            failure = "scan"
            confirmed = result.is_success and data.get('scan_has_internal_peak') is True and data.get('candidate_unavailable') is False
            if not confirmed and not (result.is_success and data.get("scan_has_internal_peak") is False
                                       and data.get("candidate_unavailable") is False):
                return None
        elif mode == "verify":
            failure = "verify"
            confirmed = result.is_success and data.get('verification_status') == 'pass'
            if not confirmed and not (result.is_success and data.get("verification_status") == "fail"):
                return None
        elif mode == "xtb_path":
            failure = "path"
            confirmed = result.is_success and data.get('refinement_termination') == 'converged'
            if not confirmed and not (not result.is_success and data.get("refinement_termination") == "cycles_exhausted"
                                       and data.get("path_termination_reason") == "path_not_converged"):
                return None
        else:
            return None
        key, source = self._reflection_key(ctx, call, data, failure)
        if confirmed:
            ctx.notices.unpin(ctx.agent.id, key)
            return None
        content = (
            f"[Guidance] {_REFLECTION_CAUSES[failure].removesuffix('.')} (source: {source}). "
            f"{_REFLECTION_ADVICE}"
        )
        _pin_reflection(ctx.notices, ctx.agent.id, key, content)
        return None

    async def before_llm(self, ctx: PipelineContext, messages: list[dict]) -> None:
        if ctx.notices is None:
            return None
        keys = [key for key in ctx.notices._pins.get(ctx.agent.id, {}) if key.startswith(_PIN_REFLECTION)]
        if len(keys) > 1:
            # Older resident pins may have been updated after their insertion.
            # Prefer the actual latest pin event, not OrderedDict insertion order.
            updated = [change['key'] for change in ctx.notices._changes.get(ctx.agent.id, [])
                       if change['kind'] == 'pin_set' and change['key'] in keys]
            if not updated and ctx.notices._event_log is not None:
                events = await asyncio.to_thread(ctx.notices._event_log.query_session,
                    ctx.agent.id, types={'context.pin_set'}, limit=None)
                updated = [event.data['key'] for event in events if event.data.get('key') in keys]
            latest = updated[-1] if updated else keys[-1]
            for key in keys:
                if key != latest:
                    ctx.notices.unpin(ctx.agent.id, key)
        for key, content in ((_PIN_TS_SOP, _TS_NOTICE),
                             (_PIN_PHYSICAL_THINKING, _PHYSICAL_THINKING_NOTICE)):
            if ctx.notices.pin_content(ctx.agent.id, key) is not None:
                ctx.notices.pin(ctx.agent.id, key=key, content=content)
        return None

    # ------------------------------------------------------------- 内部

    @staticmethod
    def _reflection_key(
        ctx: PipelineContext, call: ToolCall, data: dict, failure: str,
    ) -> tuple[str, str]:
        if failure == "scan":
            names = ("log_path",)
        elif failure == "verify":
            names = ("freq_log", "irc_log")
        elif isinstance(data.get("images_dir"), str) and data["images_dir"]:
            names = ("images_dir",)
        else:
            names = ("output_dir", "reactant_path", "product_path")
        sources = []
        for name in names:
            value = data.get(name) if name == "images_dir" else call.arguments.get(name)
            if isinstance(value, str) and value:
                source = value if os.path.isabs(value) else os.path.join(ctx.workspace_dir or os.getcwd(), value)
                sources.append((name, os.path.normpath(source)))
        identity = (failure, sources if sources else (ctx.run_id, call.id))
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
        label = ", ".join(f"{name}={path}" for name, path in sources)
        if not label:
            label = f"run_id={ctx.run_id}, call_id={call.id}"
        return _PIN_REFLECTION + digest, label

    @staticmethod
    def _needs_physical_thinking(call: ToolCall) -> bool:
        if call.name in ("ts_prepare", "qm_input_writer"):
            return True
        if call.name == "ts_guess":
            mode = call.arguments.get("mode")
            return mode in ("xtb_path", "interpolate", "scan_prepare") or (
                mode == "scan" and not call.arguments.get("log_path")
            )
        if call.name == "submit_compute_job":
            return call.arguments.get("job_type") in ("gaussian", "orca")
        return False

    def _guide_bash(self, ctx: PipelineContext, call: ToolCall, notices) -> None:
        command = str(call.arguments.get("command") or "")
        if not command:
            return
        if handwritten_coord_warning(command, path=None) is not None:
            notices.pin(ctx.agent.id, key=_PIN_BASH_COORDS, content=_BASH_COORDS_NOTICE)
        elif bash_file_write_warning(command) is not None:
            notices.pin(ctx.agent.id, key=_PIN_BASH_WRITE, content=_BASH_WRITE_NOTICE)
