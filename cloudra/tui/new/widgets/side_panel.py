"""可收起侧栏：Agent 列表 + 对话列表。

- Agent 区：当前对话内出现过的 agent（主 Agent + 各子 Agent），
  选中后聊天区只显示该 agent 的输出，输入也会定向插入它的运行上下文。
- 对话区：所有持久对话，点击切换；首项为「新建对话」。
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

_STATE_ICONS = {
    "queued": "◌",
    "running": "●",
    "waiting": "◎",
    "cancel_requested": "◐",
}
_ACTIVE_STATES = set(_STATE_ICONS)


def _session_suffix(agent_id: str | None, session_id: str | None) -> str:
    """从 session_id 提取实例后缀（如 a-1_task42 → task42），用于区分同角色并行实例。"""
    if not agent_id or not session_id or session_id == agent_id:
        return ""
    prefix = f"{agent_id}_"
    if session_id.startswith(prefix):
        return session_id[len(prefix):]
    return session_id


@dataclass(frozen=True)
class _RowSpec:
    key: str | None
    text: str
    agent_id: str | None = None


class SidePanel(Vertical):
    """Agent / 对话双区侧栏；默认隐藏，Ctrl+B 或 /agents 切换。"""

    class AgentSelected(Message):
        """用户选中了某个 Agent 实例（session_id 为 None = 全部）。

        同角色并行实例（swarm）按 session_id 区分：session_id 是行键，
        agent_id 是角色 id（多个实例可能相同）。
        """

        def __init__(
            self,
            session_id: str | None,
            agent_id: str | None,
            label: str,
        ) -> None:
            super().__init__()
            self.session_id = session_id
            self.agent_id = agent_id
            self.label = label

    class ConversationSelected(Message):
        """用户点击了某个对话。"""

        def __init__(self, conversation_id: str) -> None:
            super().__init__()
            self.conversation_id = conversation_id

    class NewConversationRequested(Message):
        """用户点击了「新建对话」。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._agent_items: dict[str | None, ListItem] = {}
        self._conv_items: dict[str | None, ListItem] = {}
        self._last_plan: str | None = None
        self._last_dag: str | None = None

    def compose(self):
        yield Static("Agent", classes="side-title")
        yield ListView(id="agent-list")
        yield Static("对话", classes="side-title")
        yield ListView(id="conv-list")
        yield Static("计划", classes="side-title")
        yield Static("（暂无计划）", id="plan-view", markup=False)
        yield Static("DAG", classes="side-title")
        yield Static("standard（无 DAG）", id="dag-view", markup=False)

    # ------------------------------------------------------------------
    # 数据填充
    # ------------------------------------------------------------------

    def set_agents(self, agents: list[dict], selected: str | None = None) -> None:
        """重建 Agent 列表。

        agents: [{"agent_id": "a-0", "session_id": "a-0_run_x", "name": "coordinator",
                  "state": "running"}]
        首项固定为「全部」。行键为 session_id（同角色并行实例各占一行）；
        selected 也按 session_id 匹配，尽量保持在原来的实例上。
        """
        agent_list = self.query_one("#agent-list", ListView)
        specs: list[_RowSpec] = [_RowSpec(None, "全部")]
        for agent in agents:
            agent_id = agent.get("agent_id")
            # 无 session_id 的旧调用方退化为按 agent_id 键控（单实例）
            session_id = agent.get("session_id") or agent_id
            state = agent.get("state") or ""
            icon = _STATE_ICONS.get(state, "○")
            name = agent.get("name") or agent_id
            suffix = _session_suffix(agent_id, session_id)
            label = f"{name} ({agent_id}·{suffix})" if suffix else f"{name} ({agent_id})"
            active = " 运行中" if state in _ACTIVE_STATES else ""
            specs.append(
                _RowSpec(session_id, f"{icon} {label}{active}", agent_id=agent_id)
            )
        self._reconcile(agent_list, specs, self._agent_items, selected, "agent_id")

    def set_conversations(
        self, convs: list[dict], current_id: str | None
    ) -> None:
        """重建对话列表；首项为「新建对话」。"""
        conv_list = self.query_one("#conv-list", ListView)
        specs: list[_RowSpec] = [_RowSpec("__new__", "＋ 新建对话")]
        for conv in convs:
            cid = conv.get("id", "?")
            state = conv.get("state", "?")
            last = (conv.get("last_active") or "")[5:16].replace("T", " ")
            marker = " ← 当前" if cid == current_id else ""
            specs.append(_RowSpec(cid, f"{cid[-12:]}  {state}  {last}{marker}"))
        self._reconcile(conv_list, specs, self._conv_items, current_id, "conv_id")

    def set_plan(self, text: str) -> None:
        """更新「计划」区文本（目标锚点 + todo 清单 + token 用量）。"""
        plan = text or "（暂无计划）"
        if plan == self._last_plan:
            return
        self._last_plan = plan
        self.query_one("#plan-view", Static).update(plan)

    def set_dag(self, text: str) -> None:
        """更新「DAG」区文本（模式、双图 revision、frontier、阻塞/缺口计数）。"""
        dag = text or "standard（无 DAG）"
        if dag == self._last_dag:
            return
        self._last_dag = dag
        self.query_one("#dag-view", Static).update(dag)

    def agent_item(self, key: str | None) -> ListItem | None:
        """Return the existing ListItem for row ``key`` (session_id) if present."""
        for item in self.query_one("#agent-list", ListView).children:
            if getattr(item, "row_key", None) == key:
                return item
        return None

    @staticmethod
    def _make_item(spec: _RowSpec, id_attr: str) -> ListItem:
        item = ListItem(Label(spec.text))
        item.row_key = spec.key
        item.agent_id = spec.agent_id
        setattr(item, id_attr, spec.key)
        return item

    def _reconcile(
        self,
        list_view: ListView,
        specs: list[_RowSpec],
        cache: dict[str | None, ListItem],
        selected: str | None,
        id_attr: str,
    ) -> None:
        """Keep rows with stable keys and only rebuild when the key order changes."""
        incoming = [spec.key for spec in specs]
        current = [getattr(item, "row_key", None) for item in list_view.children]
        if incoming != current:
            # Structural rebuild: create fresh items; old ones may have been destroyed.
            items = [self._make_item(spec, id_attr) for spec in specs]
            list_view.index = None
            list_view.clear()
            list_view.extend(items)
        else:
            for index, spec in enumerate(specs):
                item = list_view.children[index]
                label = item.query_one(Label)
                if str(label.content) != spec.text:
                    label.update(spec.text)

        highlight_index = 0
        for index, spec in enumerate(specs):
            if selected is not None and spec.key == selected:
                highlight_index = index
                break
        if list_view.children:
            list_view.index = highlight_index

    # ------------------------------------------------------------------
    # 选择事件
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if event.list_view.id == "agent-list":
            session_id = getattr(item, "row_key", None)
            agent_id = getattr(item, "agent_id", None)
            label = "全部" if session_id is None else item.query_one(Label).content
            self.post_message(self.AgentSelected(session_id, agent_id, str(label).strip()))
        elif event.list_view.id == "conv-list":
            conv_id = getattr(item, "row_key", None)
            if conv_id == "__new__":
                self.post_message(self.NewConversationRequested())
            elif conv_id:
                self.post_message(self.ConversationSelected(conv_id))
