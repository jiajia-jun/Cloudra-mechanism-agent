"""AgentRunner: one async task per running AgentSession.

The runner owns the loop around TurnPipeline.  Commands only mutate state or
deliver inbox messages; execution concurrency lives here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from cloudra.runtime_v2.schemas import AgentSession, AgentState

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

logger = logging.getLogger("runtime_v2.agent_runner")


class AgentRunner:
    def __init__(self, core: "RuntimeCore", pipeline: "TurnPipeline") -> None:
        self.core = core
        self.pipeline = pipeline
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ public

    def schedule(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return
        agent = self.core.require_agent(session_id)
        if agent.state is AgentState.RUNNING and task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(agent), name=f"agent:{session_id}")
        self._tasks[session_id] = task
        task.add_done_callback(lambda _done: self._tasks.pop(session_id, None))

    async def cancel(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    # ------------------------------------------------------------------ private

    async def _run(self, agent: AgentSession) -> None:
        core = self.core
        try:
            if agent.current_run is not None and agent.state in {
                AgentState.WAITING_INPUT,
                AgentState.WAITING_APPROVAL,
            }:
                run_id = agent.current_run.run_id
                core.agent_host.resume(agent)
            elif agent.current_run is not None and agent.state is AgentState.RUNNING:
                # The command layer already started/resumed this run and only
                # scheduled the task afterwards.
                run_id = agent.current_run.run_id
            else:
                run_id = core.agent_host.start_run(agent)
            history: list[dict] = []
            while agent.state is AgentState.RUNNING:
                before = len(core.event_log)
                inbox_messages = self._drain_inbox(agent)
                if not history and not inbox_messages:
                    inbox = core.mailbox.ensure_inbox(agent.id)
                    message = await inbox.get()
                    inbox_messages.append(message)
                try:
                    project = core.require_project(agent.project_id)
                    outcome = await self.pipeline.run_turn(
                        agent=agent,
                        run_id=run_id,
                        settings=agent.settings.model_copy(deep=True),
                        capabilities=agent.capabilities,
                        inbox_messages=inbox_messages,
                        history=history,
                        workspace_dir=project.workspace_dir,
                    )
                finally:
                    await self._publish_new_events(before)
                self._append_history(history, inbox_messages, outcome)
                if outcome.decision == "stop":
                    core.agent_host.finish_run(agent, outcome="succeeded")
                    break
                if outcome.decision in {"wait_input", "wait_approval"}:
                    core.agent_host.transition(
                        agent,
                        (
                            AgentState.WAITING_INPUT
                            if outcome.decision == "wait_input"
                            else AgentState.WAITING_APPROVAL
                        ),
                        reason=outcome.decision,
                        run_id=run_id,
                    )
                    break
                # "continue" (including blocked-tool feedback) loops again
        except asyncio.CancelledError:
            # Command handler already transitioned the agent and emitted
            # agent.cancelled after host.cancel().
            raise
        except Exception as exc:  # pipeline crash becomes a durable failure
            logger.exception("agent %s pipeline failed", agent.id)
            if agent.state is AgentState.RUNNING:
                core.agent_host.finish_run(agent, outcome="failed", error=str(exc))

    def _drain_inbox(self, agent: AgentSession) -> list[dict]:
        inbox = self.core.mailbox.inbox(agent.id)
        if inbox is None:
            return []
        messages = []
        while True:
            try:
                messages.append(inbox.get_nowait())
            except asyncio.QueueEmpty:
                return messages

    @staticmethod
    def _append_history(history: list[dict], inbox_messages: list[dict], outcome) -> None:
        for item in inbox_messages:
            history.append({"role": "user", "content": item.get("content", "")})
        if outcome.content:
            history.append({"role": "assistant", "content": outcome.content})
        for call, result in outcome.tool_exchanges:
            history.append(
                {
                    "role": "assistant",
                    "content": f"[tool] {call.name}",
                    "tool_call_id": call.id,
                }
            )
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result.summary,
                }
            )
        if outcome.blocked_call is not None:
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": outcome.blocked_call.id,
                    "content": outcome.message or "blocked by policy",
                }
            )

    async def _publish_new_events(self, before: int) -> None:
        for event in list(self.core.event_log)[before:]:
            await self.core.event_hub.publish(event)
