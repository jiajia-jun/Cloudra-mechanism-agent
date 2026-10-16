"""Unified per-session context injection for the v2 turn pipeline.

Two channels (call surface unchanged):

- ``pin(session_id, key, content)`` / ``unpin``: idempotent-by-key resident
  injections (goal anchor, DAG projection, supervisor advice).  Re-pinning
  identical content is a no-op — no event, no change record, no message.
- ``push(session_id, content)``: one-shot hint.

Consumption model（计划 2026-09-13-harness-cache-continuity Task 3）：
从「每轮重建快照」改为「未应用变更按顺序追加」。每个变更先落事件
（``context.pin_set`` / ``context.pin_cleared`` / ``context.injected``），
变更身份即事件的 per-session 序号（``session_seq``）。``TurnPipeline``
每轮调 ``collect_batch`` 取回自消费游标以来的变更批次——批次立即 park
为 pending：LLM 重试拿到同一批已准备消息，绝不再次 drain 出不同请求。
消费游标与消息正文一起写入 ``context.appended``；apply_event 同时应用
正文和游标。持久化边界之前退出，恢复后批次仍待消费；之后退出，正文
与游标同时恢复：不重复、不丢失。

上下文边界（``fresh=True``：run 起点、compact 重装、无前缀 owner 时的空
history）：当前 pin 状态全量渲染 + 未消费 push，游标推进到全部已表达
变更。同上下文内（``fresh=False``）只渲染增量：pin 更新渲染为标明替代
关系的更新消息，unpin 渲染为撤销说明。

Event sourcing: ``restore_from`` 重放事件日志重建 pin 当前状态、变更日志
与消费游标；游标之后的变更（从未进入任何上下文）跨重启保持 pending
（不丢失）。已消费的 push 不重投——它的消息由会话上下文投影恢复。
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Callable

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.schemas import EventEnvelope

RESEARCH_OBSERVATION_PIN_KEY = "supervisor-research-observation"


class NoticeManager:
    def __init__(self) -> None:
        self._pins: dict[str, OrderedDict[str, str]] = defaultdict(OrderedDict)
        # 变更日志：session_id -> [{seq, kind, key, content, is_update?}]，
        # seq 是变更事件的 session_seq（未挂事件日志时为本地递增序号）。
        self._changes: dict[str, list[dict]] = defaultdict(list)
        # 消费游标：session_id -> 已进入上下文的最后一个变更 seq。
        self._consumed: dict[str, int] = {}
        # 已准备未确认的批次：session_id -> (messages, through_seq)。
        self._pending_batches: dict[str, tuple[list[dict], int]] = {}
        self._local_seqs: dict[str, int] = defaultdict(int)
        self._event_log: EventLog | None = None
        self._project_of: Callable[[str], str | None] | None = None

    def prune_sessions(self, session_ids: set[str]) -> None:
        """Discard every notice projection for sessions removed by a tombstone."""
        for mapping in (
            self._pins, self._changes, self._consumed, self._pending_batches, self._local_seqs,
        ):
            for session_id in mapping.keys() - session_ids:
                mapping.pop(session_id)

    def attach(
        self,
        event_log: EventLog,
        project_of: Callable[[str], str | None],
    ) -> None:
        """Wire persistence: pin/push changes become events.

        ``project_of`` resolves a session id to its project id (events are
        project-scoped); returning None skips the event (in-memory only).
        """
        self._event_log = event_log
        self._project_of = project_of

    def _emit(self, type: str, session_id: str, data: dict):
        if self._event_log is None or self._project_of is None:
            return None
        project_id = self._project_of(session_id)
        if project_id is None:
            return None
        return self._event_log.append(
            type,
            stream="agent",
            project_id=project_id,
            session_id=session_id,
            data=data,
        )

    def _record_change(self, session_id: str, envelope, change: dict) -> None:
        seq = getattr(envelope, "session_seq", None) if envelope is not None else None
        if seq is None:
            seq = self._local_seqs[session_id] + 1
        self._local_seqs[session_id] = seq
        self._changes[session_id].append({**change, "seq": seq})

    def snapshot(self) -> dict:
        """Current pins and unconsumed notices, never the full notice history."""
        return {
            "pins": {sid: dict(pins) for sid, pins in self._pins.items()},
            "changes": {sid: [dict(change) for change in changes]
                        for sid, changes in self._changes.items() if changes},
            "cursors": dict(self._consumed),
        }

    def restore(self, payload: dict) -> None:
        self._pins = defaultdict(OrderedDict, {
            sid: OrderedDict(pins) for sid, pins in payload.get("pins", {}).items()
        })
        self._changes = defaultdict(list, {
            sid: [dict(change) for change in changes]
            for sid, changes in payload.get("changes", {}).items()
        })
        self._consumed = dict(payload.get("cursors", {}))
        self._pending_batches.clear()
        self._local_seqs = defaultdict(int, self._consumed)
        for sid, changes in self._changes.items():
            self._local_seqs[sid] = max(self._local_seqs[sid], max(
                (change["seq"] for change in changes), default=0,
            ))

    def apply(self, event: EventEnvelope) -> None:
        """Apply one notice fact; live pin/push methods already apply their own."""
        session_id = event.session_id
        if session_id is None:
            return
        if event.type == "context.appended":
            if event.data.get("notices_through") is not None:
                self.apply_consumed(session_id, int(event.data["notices_through"]))
            return
        if event.type not in {"context.pin_set", "context.pin_cleared", "context.injected"}:
            return
        seq = event.session_seq or 0
        if seq <= self._local_seqs[session_id]:
            return
        self._local_seqs[session_id] = seq
        if event.type == "context.pin_set":
            key = str(event.data.get("key") or "")
            if not key:
                return
            content = str(event.data.get("content") or "")
            pins = self._pins[session_id]
            self._changes[session_id].append({
                "seq": seq, "kind": "pin_set", "key": key,
                "content": content, "is_update": key in pins,
            })
            pins[key] = content
        elif event.type == "context.pin_cleared":
            key = str(event.data.get("key") or "")
            pins = self._pins.get(session_id)
            if pins is None or key not in pins:
                return
            pins.pop(key)
            if not pins:
                self._pins.pop(session_id)
            self._changes[session_id].append({
                "seq": seq, "kind": "pin_cleared", "key": key, "content": "",
            })
        elif event.type == "context.injected":
            content = str(event.data.get("content") or "")
            if content:
                self._changes[session_id].append({
                    "seq": seq, "kind": "push", "key": "", "content": content,
                })

    def restore_from(self, event_log: EventLog) -> None:
        """Rebuild on a snapshot cache miss using the same event fold."""
        self.restore({})
        for event in event_log.iter_events(types={
            "context.pin_set", "context.pin_cleared", "context.injected", "context.appended",
        }):
            self.apply(event)
        for session_id, seq in event_log.high_session_watermarks.items():
            self._local_seqs[session_id] = max(self._local_seqs[session_id], seq)

    def pin(self, session_id: str, key: str, content: str) -> None:
        text = content if content is not None else ""
        pins = self._pins[session_id]
        # Dedup: stages re-pin identical content every turn; only actual
        # changes are worth an event, a change record and a message.
        if pins.get(key) == text:
            return
        envelope = self._emit("context.pin_set", session_id, {"key": key, "content": text})
        self._record_change(
            session_id,
            envelope,
            {
                "kind": "pin_set",
                "key": key,
                "content": text,
                "is_update": key in pins,
            },
        )
        pins[key] = text

    def pin_content(self, session_id: str, key: str) -> str | None:
        """当前 pin 内容（无则 None）：一次性告警按内容指纹去重的读取口。

        pin 由事件投影恢复（restore_from），跨重启比较依然成立——内容不变
        就不应重复投递配套的一次性消息。
        """
        return self._pins.get(session_id, {}).get(key)

    def pin_is_consumed(self, session_id: str, key: str) -> bool:
        """Whether the current pin has entered context, using the existing consumption cursor."""
        cursor = self._consumed.get(session_id, 0)
        return self.pin_content(session_id, key) is not None and not any(
            change["key"] == key and change["seq"] > cursor
            for change in self._changes.get(session_id, [])
        )

    def unpin(self, session_id: str, key: str) -> None:
        pins = self._pins.get(session_id)
        if pins is None or key not in pins:
            return
        envelope = self._emit("context.pin_cleared", session_id, {"key": key})
        pins.pop(key, None)
        if not pins:
            self._pins.pop(session_id, None)
        self._record_change(
            session_id, envelope, {"kind": "pin_cleared", "key": key, "content": ""}
        )

    def push(self, session_id: str, content: str) -> None:
        if content:
            envelope = self._emit("context.injected", session_id, {"content": content})
            self._record_change(
                session_id, envelope, {"kind": "push", "key": "", "content": content}
            )

    def render_current(self, session_id: str) -> list[dict]:
        """当前 pin 状态的纯渲染（compact 重建上下文头部用）：不 park 批次、
        不动游标。未消费的 push 不在这里——它们走正常的增量批次通道。"""
        return [
            {"role": "system", "content": content}
            for content in self._pins.get(session_id, {}).values()
            if content
        ]

    # ------------------------------------------------------- consumption

    @staticmethod
    def _render_change(change: dict) -> dict:
        kind = change["kind"]
        if kind == "pin_set":
            if change.get("is_update"):
                return {
                    "role": "system",
                    "content": (
                        f"[Updated context notice: {change['key']}]\n\n"
                        f"This replaces the earlier notice pinned as "
                        f"'{change['key']}' above:\n\n{change['content']}"
                    ),
                }
            return {"role": "system", "content": change["content"]}
        if kind == "pin_cleared":
            return {
                "role": "system",
                "content": (
                    f"[Context notice retracted: {change['key']}]\n\n"
                    f"The earlier notice pinned as '{change['key']}' above is "
                    "retracted; do not follow it."
                ),
            }
        return {"role": "system", "content": change["content"]}

    def collect_batch(self, session_id: str, *, fresh: bool) -> list[dict]:
        """本轮要追加进上下文的通知批次（不推进消费游标）。

        批次立即 park 为 pending：未确认前再次调用（LLM 重试）原样返回
        同一批，绝不重新 drain 出不同请求。``fresh=True`` 是新上下文边界：
        丢弃可能残留的过期 pending 批次（其覆盖的变更游标未推进，会被
        下面的全量渲染重新覆盖），渲染当前 pin 状态 + 未消费 push。
        """
        pending = self._pending_batches.get(session_id)
        if pending is not None and pending[0] and not fresh:
            # 上一批非空且未确认（LLM 重试/崩溃）：同一批已准备消息原样返回。
            # 空批次不锁定：什么都没发出去，新到达的变更可以立刻进下一批。
            return [dict(message) for message in pending[0]]
        cursor = self._consumed.get(session_id, 0)
        changes = self._changes.get(session_id, [])
        if fresh:
            messages = [
                {"role": "system", "content": content}
                for content in self._pins.get(session_id, {}).values()
                if content
            ]
            messages.extend(
                {"role": "system", "content": change["content"]}
                for change in changes
                if change["kind"] == "push"
                and change["seq"] > cursor
                and change["content"]
            )
            # 当前 pin 状态已表达全部 pin 变更：游标推进到最大变更序号。
            through = max((change["seq"] for change in changes), default=cursor)
        else:
            pending_changes = [change for change in changes if change["seq"] > cursor]
            reflection_prefix = "guidance-scientific-reflection:"
            groups = (
                [change for change in pending_changes if change["key"].startswith(reflection_prefix)],
                [change for change in pending_changes if change["key"] == RESEARCH_OBSERVATION_PIN_KEY],
            )
            pins = self._pins.get(session_id, {})
            latest_messages = {}
            for updates in groups:
                if not updates:
                    continue
                first_by_key = {}
                for change in updates:
                    first_by_key.setdefault(change["key"], change)
                was_delivered = any(change["kind"] == "pin_cleared" or change.get("is_update")
                                    for change in first_by_key.values())
                current = next((change for change in reversed(updates)
                                if change["kind"] == "pin_set" and change["key"] in pins
                                and change["content"] == pins[change["key"]]), None)
                is_reflection = updates[-1]["key"].startswith(reflection_prefix)
                if current is not None:
                    if is_reflection:
                        content = current["content"]
                        if was_delivered:
                            content = "This replaces the earlier scientific reflection:\n\n" + content
                        message = {"role": "system", "content": content}
                    else:
                        message = self._render_change({**current, "is_update": was_delivered})
                elif was_delivered:
                    if is_reflection:
                        message = {"role": "system", "content": "[Scientific reflection retracted] The earlier scientific guidance is no longer current."}
                    else:
                        message = self._render_change(updates[-1])
                else:
                    continue
                latest_messages[updates[-1]["seq"]] = message
            messages = []
            for change in pending_changes:
                if (change["key"].startswith(reflection_prefix)
                        or change["key"] == RESEARCH_OBSERVATION_PIN_KEY):
                    message = latest_messages.get(change["seq"])
                    if message is None:
                        continue
                else:
                    message = self._render_change(change)
                if message["content"]:
                    messages.append(message)
            through = max((change["seq"] for change in pending_changes), default=cursor)
        self._pending_batches[session_id] = (messages, through)
        return [dict(message) for message in messages]

    def pending_batch(self, session_id: str) -> tuple[list[dict], int | None]:
        """Read the prepared messages and cursor without acknowledging them."""
        pending = self._pending_batches.get(session_id)
        if pending is None:
            return [], None
        messages, through = pending
        if not messages and through <= self._consumed.get(session_id, 0):
            return [], None
        return [dict(message) for message in messages], through

    def apply_consumed(self, session_id: str, through: int) -> None:
        """Apply the cursor carried by the same event as the context messages."""
        cursor = max(through, self._consumed.get(session_id, 0))
        self._consumed[session_id] = cursor
        pending = self._pending_batches.get(session_id)
        if pending is not None and pending[1] <= cursor:
            self._pending_batches.pop(session_id)
        self._changes[session_id] = [
            change for change in self._changes.get(session_id, [])
            if change["seq"] > cursor
        ]

    def confirm_consumed(self, session_id: str) -> list[dict]:
        """Compatibility helper for in-memory callers; durable callers use ContextBroker."""
        messages, through = self.pending_batch(session_id)
        if through is not None:
            self.apply_consumed(session_id, through)
        return messages
