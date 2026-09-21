# 插件机制与开发指南（Plugins）

本文档介绍 Cloudra 的通用插件机制，说明如何开发和接入自定义插件（例如 GraphRAG 知识图谱、事件监听触发器、外部数据分析与统计等）。

核心实现代码位于：
- `cloudra/runtime_v2/plugins.py`：插件的注册、加载、初始化与事件挂接
- `cloudra/runtime_v2/knowledge.py`：知识库与图书馆检索协议

系统整体架构与代码布局请参考仓库根目录的 [`AGENTS.md`](../AGENTS.md)。

## 设计原则与边界

- **核心数据与插件存储相互独立（无隐式自演化）**：Cloudra 运行时不会自动把 DAG 计算结论、论坛讨论帖或对话运行摘要回写到外部插件的数据库中。插件自身数据的构建、更新和清理完全由插件自主管理（可以通过监听系统事件 `on_event` 或依靠插件自身的外部调度来完成）。这样设计是为了保证科研与消融实验的严谨性：评估时只需对比“接入插件 vs 不接插件”即可，避免系统在后台隐式修改外部知识库而干扰实验结论。
- **故障隔离，插件异常不影响核心运行**：插件在执行 `search` 检索时若抛出异常，系统仅记录警告日志并跳过该插件；`on_event` 监听回调中的异常会被事件总线就地捕获并隔离；模块导入失败同样只记录日志，不会阻断整个系统的启动流程。
- **提示注入与主动唤醒职责分离**：通过 `context.inject` 注入的内容只作为上下文提示提供给模型，Agent 会在进入下一个交互轮次时自然读取；如果需要让当前处于休眠或等待状态的 Agent 立即开始工作，请直接向其发送消息（`agent.message`）。

## 插件接口定义

在 Python 层面，一个插件就是一个具有 `name` 属性的普通对象。所有生命周期与功能钩子（hook）均为可选，插件具备什么能力取决于它实现了哪些方法：

```python
class MyPlugin:
    name = "my-plugin"

    def setup(self, core) -> None: ...            # 可选：系统挂载时调用一次，用于初始化
    def on_event(self, envelope) -> None: ...     # 可选：订阅系统全量事件
    def search(self, query, *, limit=5): ...      # 可选：接入知识库，提供检索能力
```

### 1. `setup(core)`（可选初始化）

在插件被挂载到 `RuntimeCore` 运行时实例时调用一次。支持同步函数或异步协程（如果是 async 函数，系统会将其放入事件循环中调度）。

典型用途：
- 保存 `CommandBus(core)` 实例，以便后续在插件中向系统发起指令；
- 读取 `core.agents` 或 `core.projects` 的当前运行时状态。

注意：挂载操作发生在历史状态加载与回放之前。系统从持久化存储恢复时，历史事件**不会**重复推送给插件，插件的 `on_event` 仅接收挂载之后产生的新事件。

### 2. `on_event(envelope)`（可选事件监听）

订阅事件总线（`EventHub`）派发的**所有事件**，包括流式 token 等瞬态事件（如 `llm.chunk`）。插件可根据 `envelope.type` 过滤关注的事件类型。

如果是同步方法，系统会自动将其分发到后台线程池执行，不会阻塞主事件循环；如果是异步方法则直接 `await`。

`envelope` 事件对象包含以下主要字段：
`type`（事件类型）、`stream`、`project_id`、`session_id`、`run_id`、`seq`、`session_seq`、`data`（事件载荷）、`created_at`、`event_id`。

这是插件监听系统状态变化的主要途径。常见使用场景包括：
- 监听关键生命周期节点（如 `run.finished` 运行结束、`context.handover_updated` 交接状态更新、`tool.finished` 工具调用完成等）；
- 触发自定义的外部索引构建、数据同步或运行时统计分析。

### 3. `search(query, *, limit=5)`（可选知识库检索）

实现了 `search` 方法的插件会自动注册为 AgentHub 的知识源（Provider）。当 Agent 在工具中调用 `agent_hub` 的 `search` 操作时，系统会并发查询所有已注册的知识源，并将检索到的条目随同工具结果一并返回给模型。

在给模型的展示摘要中，会呈现证据等级、出处和证伪标记；完整数据保存在 `data["library"]` 中。如果 `search` 是同步方法，同样会自动放入后台线程池执行以避免阻塞。

`search` 方法需返回 `KnowledgeEntry` 对象列表，或包含相同字段的字典列表：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `title` | str | （必填） | 知识条目的标题 |
| `content` | str | （必填） | 知识条目的正文内容（摘要视图会做截断展示，数据中保留完整文本） |
| `evidence_level` | str | `"L0"` | 证据等级：`L0`（文献常识与背景知识）/ `L1`（经过计算或实验验证的结论）/ `L2`（推测或模型假设） |
| `source` | str | `""` | 来源出处指针（例如 DOI、关联的 project/run ID、artifact ID 等），确保结论可追溯 |
| `falsified` | bool | `False` | 是否已被证伪：**证伪条目会保留在知识库中供模型参考，但排序权重会被大幅降低**，不会直接删除 |
| `score` | float | `0.0` | 插件内部计算的相关度打分，用于同等级条目之间的相对排序 |

**知识合并与排序规则**：
- 严格遵循证据等级优先：`L1 > L0 > L2`；
- 在同一证据等级内，未被证伪的条目排在前面，之后按 `score` 打分降序排列；
- 若传入了未知的 `evidence_level`，系统会自动归一化为 `L0` 处理；
- `title` 与 `content` 均为空的无效条目会被自动过滤；
- 返回给模型的条目中会附带 `provider` 字段标注插件名称。

## 插件注册与接入方式（三选一）

开发者可以根据使用场景选择以下任意一种接入方式：

### 方式一：配置文件声明（推荐）

在 `config.yaml` 中配置插件模块路径：

```yaml
plugins:
  - "my_package.my_module:plugin"      # 指向模块中的插件实例对象
  - "my_package.my_module:get_plugin"  # 指向无参数的工厂函数
  - "my_package.my_module"             # 省略属性名时，默认查找模块中的 plugin 或 get_plugin
```

在系统初始化启动（`create_default_v2_app`）时，运行时会自动导入这些模块、完成注册并挂载。单个插件加载失败不会影响其余插件的正常运行。

### 方式二：Python 进程内编程式注册（适用于测试或嵌入式集成）

```python
from cloudra.runtime_v2.plugins import register_plugin, attach_plugins

register_plugin(MyPlugin())
attach_plugins(core)   # 挂载到指定的 RuntimeCore 实例上
```

- `register_plugin` 会自动根据插件对象的唯一身份进行去重；
- 在测试用例中可以使用 `clear_plugins()` 清空注册表（同时会清理关联的知识源提供方）。

### 方式三：进程外 HTTP / SSE 接入（适用于独立服务或其他语言开发）

如果插件以独立微服务形式运行或由其他编程语言实现，无需在 Python 端注册代码，直接通过 HTTP API 即可与系统交互：

- **注入提示信息**：`POST /api/v2/agents/{session_id}/context/inject`
  请求体：`{"kind": "pin"|"unpin"|"push", "key": "...", "content": "..."}`
- **发送消息并唤醒**：`POST /api/v2/agents/{session_id}/messages`
- **监听实时事件流**：`GET /api/v2/projects/{project_id}/stream`（通过 SSE 接收全量系统事件推送）

## 上下文注入语义（`context.inject`）

| 类型（kind） | 行为说明 | 产生的系统事件 | 生命周期与持久化 |
| --- | --- | --- | --- |
| `pin` | 常驻提示，相同 key 会直接覆盖更新；在 Agent 的每一轮对话中都会渲染给模型 | `context.pin_set` | 持续生效，直到被主动 `unpin` 或覆盖；可跨进程持久化（恢复时从事件投影重建） |
| `unpin` | 移除指定的常驻提示 | `context.pin_cleared` | 立即失效 |
| `push` | 一次性提示，仅在 Agent 的下一轮对话中渲染一次，随后自动消费销毁 | `context.injected` | 仅在下一轮生效；内存中一次性消费，但在事件日志中永久留痕供审计 |

**渲染机制**：
注入的提示会统一附加在每轮发送给模型的 system 消息末尾（利用 recency 效应确保模型能优先注意到最新提示）。系统具备写时去重机制，对同一个 key 连续注入完全相同的内容不会产生冗余事件。注意：单纯注入提示**不会**唤醒处于空闲或等待状态的 Agent。

## 完整代码示例

### 示例一：自定义知识库提供方（如接入 GraphRAG）

```python
# my_graphrag.py
class MyGraphPlugin:
    name = "my-graphrag"

    def search(self, query, *, limit=5):
        # 查询自定义的图数据库、向量索引或外部知识服务
        # 同步函数会自动交由后台线程池执行，不会卡顿事件循环
        return [
            {
                "title": "HFIP 溶剂中醌骨架形成的已验证过渡态",
                "content": "已通过 IRC 计算确认，xTB 能垒为 18.3 kcal/mol，详见计算记录 run_9f2...",
                "evidence_level": "L1",
                "source": "project prj_xxx / run_9f2",
                "score": 0.87,
            }
        ]

plugin = MyGraphPlugin()
```

### 示例二：事件驱动的智能提示触发器

```python
# my_trigger.py
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.schemas import Command

class KeyNodeTrigger:
    name = "keynode-trigger"

    def setup(self, core):
        self._bus = CommandBus(core)

    async def on_event(self, envelope):
        # 示例：当检测到 Agent 调用机理草稿提案工具时，主动向其推送相关的知识参考
        if envelope.type == "tool.started" and envelope.data.get("tool_name") == "dag_propose_mechanism":
            hint = self.lookup(envelope.data.get("arguments_summary"))
            if hint:
                await self._bus.execute(Command(
                    type="context.inject",
                    target={"session_id": envelope.session_id},
                    payload={"kind": "push", "content": f"[知识库参考] {hint}"},
                ))

    def lookup(self, args):
        # 根据参数查询推荐信息
        ...

plugin = KeyNodeTrigger()
```

## 实战：chem-kb 混合知识库（仓库自带）

仓库自带一个完整的双通道知识库插件 `cloudra.knowledge.plugin:plugin`，作为上述协议的参考实现。它把知识卡片语义检索（向量微服务）与知识图谱（本地 SQLite）缝合成单一 provider。

### 数据与约定

- 数据源：`kg_data/`（14.2k 实体 / 10.3k 行级关系，知识卡片洁净版 + 动力学讲义增量抽取）与 `vector_store/`（8,594 卡的 bge-m3 双语向量，17,188 行）。
- 全部条目 `evidence_level="L0"`（文献常识层——博客知识按 L0 对待）、`falsified=false`；`source` 是 `kb:{id}` 指针（不是 URL），条目内顺序按通道原始分近似排序（bm25 与余弦不同量纲，跨通道顺序只是观感；最终排序以图书馆层的 `(level, falsified, -score)` 为准）。

### 部署三步

1. **建库**：`uv run cloudra knowledge import`（从仓库 `kg_data/` 导入 `data_dir/knowledge/chem_kg.db`，幂等可重跑；二次导入计数不变）。
2. **起向量微服务**：`<venv-trans>/bin/python scripts/kg_vec_service.py`（默认 8765 端口；用外部 `.venv-trans` 跑 bge-m3，模型已在本机 HF 缓存时先 `export HF_HUB_OFFLINE=1` 离线加载，启动后台预热约 5-10s 后 `/health` 的 model 字段就绪。服务**不随 cloudra 自启**，停了也不影响 cloudra 运行——语义通道为空时图谱通道补满配额）。
3. **激活插件**：`uv run cloudra knowledge install`（把 spec 幂等写进 config.yaml 的 `plugins` 列表）→ **重启 uvicorn**（插件在 app 启动时加载一次）。

### 配额语义（v9.1）

`search(query, limit=5)` 时语义通道取 `ceil(3/5)=3` 条、图谱通道 `floor(2/5)=2` 条——**结构性保证双通道全带上**：即使语义命中分数再高也挤不掉图谱名额。降级矩阵：微服务停 → KG-only 补满；缺库 → 语义-only 补满（缺库不建库不抛）；双缺 → 空列表。`limit<2` 时两通道各保 1。语义命中会按 `blog_id` 缝合 1~2 条卡内关系（content 里形如 `‖图: A—rel→B` 的行）。

### 零部署兜底（v10：模糊匹配 fallback）

微服务没起也能有基础检索：语义通道不可用或返回不足配额时，provider 用**确定性子串匹配**扫仓库内 `vector_store/cards.jsonl`（8,594 卡）补位卡片槽——**克隆仓库零操作即用**。退化矩阵：

| 微服务 | KG 库 | cards.jsonl | 行为 |
| --- | --- | --- | --- |
| ✓ | ✓ | — | 3 语义 + 2 图谱（满血，模糊层零参与） |
| ✗ | ✓ | ✓ | 3 模糊 + 2 图谱（降级模式双通道叙事仍成立） |
| ✗ | ✓ | ✗ | 5 图谱（KG 补位不变） |
| ✓ | ✗ | — | 5 语义（补位不变） |
| ✗ | ✗ | ✓ | 5 模糊 |
| ✗ | ✗ | ✗ | 空结果 |

要点：

- 模糊条目前缀 **〔卡片·模糊〕**（与〔卡片〕/〔图谱〕并列的诚实标记，agent 可感知降级）；补位触发时打 debug 日志。
- 匹配是**关键词包含**级（token AND、ASCII 大小写不敏感、heading 加权），**无语义泛化**——质量预期低于向量通道，仅作兜底。
- 优先级链固定为 语义 > 模糊 > 图谱补位；模糊层按 card_id 去重，不与语义命中共存于同一条。
- pip 安装场景没有 `vector_store\` 目录：此层零参与，行为与 v9.1 完全一致。

### 双语（v11：英语适配）

- 向量库 `vector_store/cards.jsonl` 每卡两行：同 `card_id` + `"lang":"zh"/"en"`（中文行是唯一事实源，英文行挂在同一把 `kb:{id}` 钥匙上）；`/search` 接受可选 `lang=zh|en`（缺省混合），同 card_id 双行去重（保留高分行，防止同一卡双占 top-k）。
- KG 侧不重抽：实体 `props` 列装载 `{"label_en": ...}`（导入即进 FTS）→ 英文查询自动可搜图谱；混合 provider 对 ASCII 主导查询（≥70% token 为 ASCII）的图谱条目 title 优先 `label_en`（回退 label），content 保留原 label 可溯源。
- 语义/模糊通道自动双语：bge-m3 多语单索引天然让 en 查询优先命中 en 行；模糊层对同卡双行按查询语言偏好去重。
- 增量路径：新卡片 → 翻译（同批管线）→ cards.jsonl 追加 zh+en 两行 → `vector_store/encode.py` 全量重编码（原子覆写）。
- 关系 quote 保持中文（回溯原文）；`《中文标题》` 交叉引用不译（标题是指针）。

### 标签体系与分面检索（v13）

知识库新增受控标签层：8,594 卡按 **方法/软件/问题种类/报错类型** 四维 LLM 打标（词表 `vector_store/tag_vocab.yaml` 人工维护），标签贯通整条检索链——向量服务 `/search` 支持 `domain`/`tags` 过滤、图谱条目携带 `kg_entity_tags` 派生标签并上送关系 `note` 因果解释、provider 按词表 aliases 做确定性**报错签名检测**触发报错优先检索（过滤空自动回退；词表/打标/派生表缺失时自动降级为无过滤，检索语义与 v12 一致）、自动注入的查询从 800 字符 blob 重写为 ≤200 字符的"工具名+短参数+报错窗口"（修复 FTS/模糊通道对 blob 恒空的问题），注入策略改为**失败必注入、成功高分才注入**。部署在建库三步之后追加：`knowledge tag build` → `knowledge tag apply-db`。详见 **docs/KNOWLEDGE_TAGS.md**。

### 卸载

`cloudra knowledge uninstall`（内部走 `remove_plugin`，幂等从 `plugins:` 删掉对应条目），重启生效。

## 测试与审计支持

- **全量事件追溯**：所有的提示注入和插件交互行为都会完整记录到事件日志中（包括 `context.pin_set`、`context.pin_cleared`、`context.injected`、`tool.started` 等）。调用 `GET /api/v2/projects/{id}/transcript` 可以导出项目全量运行记录的 Markdown 文档，便于在消融实验和机制分析中进行量化统计。
- **单元测试隔离**：在编写测试用例时，可调用 `clear_plugins()` 和 `clear_knowledge_providers()` 重置环境状态。具体用法可参考测试套件中的 `tests/test_runtime_v2_plugins.py` 和 `tests/test_runtime_v2_knowledge.py`。
