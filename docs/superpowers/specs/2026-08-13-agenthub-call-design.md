# AgentHub directory / call

## Goal

Let agents talk to each other without going through Coordinator as a
switchboard, and without treating a consult as a task delivery. Coordinator
still faces the user and dispatches work with `SubAgentLauncher`. Supervisor
still owns process-graph rules. Peer speech is free, non-blocking, and as
cheap as a phone call: the caller does not write the other agent's prompt.

## Out of scope

- Interrupting an in-flight LLM or tool turn.
- Pinning `[来电]` like Supervisor advice, or harness-rejecting `stop` until
  the call is answered.
- Giving followers `SubAgentLauncher` / `MANAGE`.
- Exclusive locks on compute jobs.
- Binding calls to a hub post, DAG node, or any other pivot. Posts stay an
  optional memo.

## Roles

| Actor | Job |
| :--- | :--- |
| Coordinator | User-facing contact and **task** dispatch (`SubAgentLauncher` / Swarm). |
| Supervisor | Process-graph rules. Unchanged. Not a chat partner. |
| Everyone else | May `directory` / `call` / `post` freely. |

Remove the Coordinator prompt line that forbids direct sub-agent
communication. AgentHub remains the tool; it is not a required hub for the
content of a call.

## Naming

Do not expose the word `query` on this tool. Two different meanings used to
share it:

| Name | Who sees it | Meaning |
| :--- | :--- | :--- |
| `task` | `directory` row | What that session is doing. Maps to the existing `session.query` column; do not rename the column. |
| `message` | `call` argument | What the caller says on the phone. Not a role prompt. |
| `content` | `post` argument | Forum post body (unchanged). |

## Tool surface

Extend existing `agent_hub` (already visible to read-only agents). No new
tool. Two actions:

### `directory`

List sessions in this conversation. Each row:

- `session_id`
- `agent_id`
- role / `agent_type`
- `state` (`running`, `waiting`, `sleeping`, `completed`, `failed`,
  `cancelled`, …)
- `task` — **public**, including Coordinator.

Do not dump another agent's transcript. That stays `get_subagent_report`.

### `call`

| Field | Required | Meaning |
| :--- | :--- | :--- |
| `to` | yes | Target (see resolution below). |
| `message` | yes | What the caller says. |
| `post_id` | no | If set and the post exists, append a one-line pointer. Missing post is ignored, call still happens. |

Returns immediately (`is_wait=False` semantics). Never blocks the caller.

**`to` resolution (no implicit visit):**

- Exact `session_id` present in this conversation → **visit** that session.
- `a-0` or `coordinator` → **visit** the conversation's Coordinator session.
  Never spawn a second Coordinator.
- Exact `agent_id` (`a-4`) or registry class name (`small_mol`) → **spawn** a
  new session of that role, even if another instance is already live.
  Visiting an existing specialist requires its `session_id` from `directory`.

Unknown `to` or empty `message` → fail the tool call with a short message.

## Incoming call (visibility)

No pin. No extra system banner. The callee sees one **`role=user`** message,
same path as a TUI supplement (`append` then `inject_event` with
`event_type=user_message` so `_consume_external_events` dedups and does not
wrap `【hub_message】`).

Harness template (caller only fills `{message}`):

```
【来电】{caller_agent_id} 打给你（session={caller_session_id}）。请第一时间回应这通来电（正文或 agent_hub call/post），不要先查计算、改提醒或 stop。

{message}
```

If `post_id` is present, one extra line: `对照帖子 #{post_id}（主题 …）。`

Do not interrupt the current model turn. The user line is waiting when the
turn ends; waiting/sleeping sessions wake via existing `external_event` /
resume.

## Visit vs spawn

**Visit.** Inject the user-line into that session's context file. If
running/waiting, inject wakes the wait loop. If there is no live runner
(Coordinator `sleeping`, or a follower `waiting`/`completed` without an
executor): Coordinator resumes via the existing append-message resume path
(`submit_async`); a follower resumes the **same** `session_id` via
`_resume_follower_session`. Resume is not a delivery. Context file is
kept for the next call.

**Spawn.** `dispatch_subagent` with `is_wait=False`, inherited
`working_directory` and orchestration mode (`dag_record` under a DAG parent,
same as launcher children). Identity prompt is the stock role prompt. The
`task` shown in `directory` is the caller's `message` verbatim (written into
the session `query` column). Payload flag `origin: "hub_call"` plus
`caller_agent_id` / `caller_session_id`.

## Hang-up vs delivery

`origin=hub_call` sessions are conversations, not work orders:

- `stop` while compute/reminders pending → `waiting`, line stays open.
- `stop` with a clear background → hang up: persist context; inject a
  **`role=user`** note to the **caller** (`【来电结束】… 已挂断`). Do **not**
  send Coordinator the launcher wakeup `子 Agent … 已完成。结论: …`.
- Next `call` to that `session_id` resumes the same context.

Launcher-origin sessions keep today's finalize path (Coordinator wakeup,
delivery/audit). Extra `call` user-lines in that context do not change what
`stop` means for the assigned task.

## Prompts (reuse, don't invent a persona)

- `_AGENT_HUB_GUIDANCE`: document `directory` / `call`; incoming `【来电】`
  is a user message and must be answered first.
- `_REVIVED_AFTER_STOP_NOTICE`: one clause that a `【来电】` user line counts
  as a user ask (already “answer the user first”).
- `coordinator.md`: delete “子 Agent 之间不允许直接通信，信息同步由你负责.”
  Replace with: task dispatch stays yours; peer talk goes through
  `agent_hub` `call`/`post` and is not a delivery.
- Do not rewrite `small_mol.md` / `dft.md` / other role files for this.

## Caps and contention

v1: no spawn cap, no job mutex. `directory` is how agents see who is
computing what. Revisit only if call-spawn storms appear.

## Tests (behavioral)

- `directory` returns Coordinator `task` and follower states.
- `call` to a live session appends exactly one `role=user` `【来电】` line;
  no `【hub_message】` / `【user_message】` system twin.
- `call` to `a-0` visits Coordinator, does not create `a-0` #2.
- `call` to `a-4` while another `a-4` is running creates a new session with
  `origin=hub_call`.
- Spawned call session `stop` (idle) notifies the caller as `role=user` and
  does not write Coordinator “已完成。结论”.
- Launcher child `stop` still wakes Coordinator as today.
- Empty `message` / unknown `to` fail closed.
- Optional `post_id` missing → call still succeeds.

## Implementation notes

Keep logic in `agent_hub.py` plus a thin helper next to
`_subagent_dispatch` / `session_store` resume. Reuse
`ContextManager.append` + `inject_event(user_message)` and
`run_subagent_in_process`. Do not add a second forum tool.
The `agent_hub` input schema must not add a `query` field.
