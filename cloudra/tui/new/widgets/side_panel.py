"""可收起侧栏：Agent 列表 + 对话列表。

- Agent 区：当前对话内出现过的 agent（主 Agent + 各子 Agent），
  选中后聊天区只显示该 agent 的输出，输入也会定向插入它的运行上下文。
- 对话区：所有持久对话，点击切换；首项为「新建对话」。
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

_STATE_ICONS = {
    "queued": "◌",
    "running": "●",
    "cancel_requested": "◐",
}
_ACTIVE_STATES = set(_STATE_ICONS)


class SidePanel(Vertical):
    """Agent / 对话双区侧栏；默认隐藏，Ctrl+B 或 /agents 切换。"""

    class AgentSelected(Message):
        """用户选中了某个 Agent（None = 全部）。"""

        def __init__(self, agent_id: str | None, label: str) -> None:
            super().__init__()
            self.agent_id = agent_id
            self.label = label

    class ConversationSelected(Message):
        """用户点击了某个对话。"""

        def __init__(self, conversation_id: str) -> None:
            super().__init__()
            self.conversation_id = conversation_id

    class NewConversationRequested(Message):
        """用户点击了「新建对话」。"""

    def compose(self):
        yield Static("Agent", classes="side-title")
        yield ListView(id="agent-list")
        yield Static("对话", classes="side-title")
        yield ListView(id="conv-list")
        yield Static("计划", classes="side-title")
        yield Static("（暂无计划）", id="plan-view")

    # ------------------------------------------------------------------
    # 数据填充
    # ------------------------------------------------------------------

    def set_agents(self, agents: list[dict], selected: str | None = None) -> None:
        """重建 Agent 列表。

        agents: [{"agent_id": "a-0", "name": "coordinator", "state": "running"}]
        首项固定为「全部」。选中项尽量保持在原来的 agent 上。
        """
        agent_list = self.query_one("#agent-list", ListView)
        items: list[ListItem] = [self._agent_item(None, "全部", "")]
        for agent in agents:
            state = agent.get("state") or ""
            icon = _STATE_ICONS.get(state, "○")
            label = f"{agent.get('name') or agent.get('agent_id')} ({agent.get('agent_id')})"
            suffix = " 运行中" if state in _ACTIVE_STATES else ""
            items.append(self._agent_item(agent["agent_id"], f"{icon} {label}", suffix))
        self._replace_items(agent_list, items, target_attr="agent_id", selected=selected)

    def set_conversations(self, convs: list[dict], current_id: str | None) -> None:
        """重建对话列表；首项为「新建对话」。"""
        conv_list = self.query_one("#conv-list", ListView)
        new_item = ListItem(Label("＋ 新建对话"))
        new_item.conv_id = "__new__"
        items: list[ListItem] = [new_item]
        for conv in convs:
            cid = conv.get("id", "?")
            state = conv.get("state", "?")
            last = (conv.get("last_active") or "")[5:16].replace("T", " ")
            marker = " ← 当前" if cid == current_id else ""
            item = ListItem(Label(f"{cid[-12:]}  {state}  {last}{marker}"))
            item.conv_id = cid
            items.append(item)
        self._replace_items(conv_list, items, target_attr="conv_id", selected=current_id)

    def set_plan(self, text: str) -> None:
        """更新「计划」区文本（目标锚点 + todo 清单 + token 用量）。"""
        self.query_one("#plan-view", Static).update(text or "（暂无计划）")

    @staticmethod
    def _agent_item(agent_id: str | None, text: str, suffix: str) -> ListItem:
        item = ListItem(Label(f"{text}{suffix}"))
        item.agent_id = agent_id
        return item

    @staticmethod
    def _replace_items(
        list_view: ListView, items: list[ListItem], *, target_attr: str, selected
    ) -> None:
        list_view.clear()
        highlight_index = 0
        for i, item in enumerate(items):
            list_view.append(item)
            if selected is not None and getattr(item, target_attr, None) == selected:
                highlight_index = i
        if items:
            list_view.index = highlight_index

    # ------------------------------------------------------------------
    # 选择事件
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if event.list_view.id == "agent-list":
            agent_id = getattr(item, "agent_id", None)
            label = "全部" if agent_id is None else item.query_one(Label).content
            self.post_message(self.AgentSelected(agent_id, str(label).strip()))
        elif event.list_view.id == "conv-list":
            conv_id = getattr(item, "conv_id", None)
            if conv_id == "__new__":
                self.post_message(self.NewConversationRequested())
            elif conv_id:
                self.post_message(self.ConversationSelected(conv_id))
