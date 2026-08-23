# 插件契约（plugins）

本文是 Cloudra 通用插件机制的契约文档，面向要写插件（GraphRAG 知识图谱、自定义
触发器、外部分析等）的使用者。实现：`cloudra/runtime_v2/plugins.py`（注册/装载/挂接）、
`cloudra/runtime_v2/knowledge.py`（图书馆层协议）。面向开发者的模块地图见根目录
`AGENTS.md`。

## 设计边界（先读）

- **核心不回写插件存储——无自演化**。核心不会把 DAG 结论、hub 帖子、run 摘要自动
  沉淀进任何知识库；插件的存储维护（建图、更新、淘汰）是插件自己的事，用
  `on_event` 或外部调度驱动。这是刻意的：消融实验只需"接插件 vs 不接"一组对照。
- **插件崩不坏核心**。`search` 抛异常只记日志并跳过；`on_event` 抛异常被事件总线
  隔离；装载（import）失败只记日志、不阻塞启动。
- **注入与唤醒是两件事**。`context.inject` 只注入提示（agent 下一轮自然看到）；
  要让沉睡的 agent 立刻行动，用 `agent.message`。

## 插件定义

插件 = 一个带 `name` 属性的 Python 对象。所有 hook 都可选，能力由实现了哪些 hook
决定：

```python
class MyPlugin:
    name = "my-plugin"

    def setup(self, core) -> None: ...            # 可选，attach 时调一次
    def on_event(self, envelope) -> None: ...     # 可选，订阅全量事件
    def search(self, query, *, limit=5): ...      # 可选，成为图书馆 provider
```

### `setup(core)` — 可选

attach 时调用一次，参数是 `RuntimeCore` 实例。可以 sync 或 async（async 会被
调度为任务）。典型用途：持有 `CommandBus(core)` 以便后续注入；读取 `core.agents` /
`core.projects` 活状态。attach 发生在 store/restore 之前，**restore 回填的历史事件
不会重放给插件**——`on_event` 只收 attach 之后的新事件。

### `on_event(envelope)` — 可选

订阅事件总线（`EventHub`）的**全量**发布，包括 `llm.chunk` 这类瞬态事件——按需
过滤 `envelope.type`。sync 实现自动 offload 到工作线程（不卡事件循环），async 实现
直接 await。`envelope` 字段：`type / stream / project_id / session_id / run_id / seq /
session_seq / data / created_at / event_id`。

这是插件的**通用反应面**：关键节点触发（如 `run.finished`、
`context.handover_updated`、`tool.finished` 特定工具）、自建索引、统计分析都挂这里。

### `search(query, *, limit)` — 可选（图书馆 provider）

实现了 `search` 的插件自动成为 AgentHub 图书馆 provider：agent 每次调 `agent_hub`
的 `search` 动作，所有 provider 都会被查询，命中随同一工具结果返回（summary 渲染
等级/出处/证伪标记，完整字典在 `data["library"]`）。sync 实现同样 offload 到工作线程。

返回值：`KnowledgeEntry` 或同字段 dict 的列表：

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `title` | str | （必填） | 条目标题 |
| `content` | str | （必填） | 条目正文（summary 截断展示，data 给全文） |
| `evidence_level` | str | `"L0"` | `L0` 文献知识 / `L1` 已验证计算结论 / `L2` 模型假设 |
| `source` | str | `""` | 出处指针（DOI、项目/run id、artifact id……），保证可追溯 |
| `falsified` | bool | `False` | 已证伪标记：**保留但降权**，不删除 |
| `score` | float | `0.0` | provider 自己的相关度，同级内排序用 |

合并排序规则：`L1 > L0 > L2`，同级内未证伪在前、再按 `score` 降序；非法
`evidence_level` 归一为 `L0`；`title` 与 `content` 都空的条目被丢弃。返回条带
`provider` 字段（插件名）。

## 注册方式（三选一）

**1. 声明式（推荐）**——`config.yaml`：

```yaml
plugins:
  - "my_package.my_module:plugin"      # attr 是插件实例
  - "my_package.my_module:get_plugin"  # attr 是无参工厂
  - "my_package.my_module"             # 省略 attr 时按约定找 plugin / get_plugin
```

应用启动（`create_default_v2_app`）时 import 并注册、attach；单个失败不影响其余。

**2. 进程内**——嵌入场景/测试：

```python
from cloudra.runtime_v2.plugins import register_plugin, attach_plugins

register_plugin(MyPlugin())
attach_plugins(core)   # 挂到某个 RuntimeCore
```

`register_plugin` 按身份去重；`clear_plugins()` 清空（测试隔离用，会连带清空图书馆
provider 注册表）。

**3. 进程外**——不注册任何东西，直接走 HTTP（适合独立服务/其他语言）：

- 注入：`POST /api/v2/agents/{session_id}/context/inject`，
  body `{"kind": "pin"|"unpin"|"push", "key": "...", "content": "..."}`
- 消息/唤醒：`POST /api/v2/agents/{session_id}/messages`
- 事件流：`GET /api/v2/projects/{project_id}/stream`（SSE，全量事件实时推送）

## 注入语义（`context.inject`）

| kind | 行为 | 事件 | 生命周期 |
| --- | --- | --- | --- |
| `pin` | 常驻提示，同 key 覆盖，每轮渲染 | `context.pin_set` | 直到 unpin/覆盖；跨进程存活（restore 重建） |
| `unpin` | 摘除常驻提示 | `context.pin_cleared` | — |
| `push` | 一次性提示，下一轮渲染一次即销毁 | `context.injected` | 下一轮；进程死亡即失（事件留档） |

渲染位置：每轮 LLM 请求消息列表**末尾**的 system 消息（recency 区）。写时去重：
相同内容重复 pin 不产生新事件。注入**不唤醒** agent。

## 最小示例

图书馆 provider（GraphRAG 钩子面）：

```python
# my_graphrag.py
class MyGraphPlugin:
    name = "my-graphrag"

    def search(self, query, *, limit=5):
        # 查自己的图谱存储（sqlite/向量库/远程服务均可；sync 会自动上工作线程）
        return [
            {
                "title": "HFIP 中醌骨架形成的已验证 TS",
                "content": "IRC 确认，能垒 18.3 kcal/mol（xTB），详见 run run_9f2…",
                "evidence_level": "L1",
                "source": "project prj_xxx / run_9f2",
                "score": 0.87,
            }
        ]

plugin = MyGraphPlugin()
```

事件驱动的被动注入（关键节点触发）：

```python
# my_trigger.py
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.schemas import Command

class KeyNodeTrigger:
    name = "keynode-trigger"

    def setup(self, core):
        self._bus = CommandBus(core)

    async def on_event(self, envelope):
        # 例：机理草稿提案工具被调用时，给该 agent 推一条图书馆推荐
        if envelope.type == "tool.started" and envelope.data.get("tool_name") == "dag_propose_mechanism":
            hint = self.lookup(envelope.data.get("arguments_summary"))
            if hint:
                await self._bus.execute(Command(
                    type="context.inject",
                    target={"session_id": envelope.session_id},
                    payload={"kind": "push", "content": f"[Library] {hint}"},
                ))

    def lookup(self, args): ...

plugin = KeyNodeTrigger()
```

## 测试与审计

- 注入与插件相关行为全部有事件（`context.pin_set/pin_cleared/injected`、
  `tool.started/finished`），项目级完整转录 `GET /api/v2/projects/{id}/transcript`
  会渲染这些事件，消融诊断可直接统计。
- 测试隔离：`clear_plugins()` / `clear_knowledge_providers()`；参考
  `tests/test_runtime_v2_plugins.py`、`tests/test_runtime_v2_knowledge.py`。
