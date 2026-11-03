# 外部 MCP 工具接入设计

状态：用户已确认，已实现并通过相关模块验证，待 PR 审阅。

## 目标与已确认的选择

Cloudra 作为 MCP 客户端，接入外部服务发布的工具。用户继续用自然语言交代任务，Agent 按任务选择工具；任务界面不增加领域选择。

用户已确认：

- 同时支持本地 stdio 进程与远程 Streamable HTTP。
- 外部工具逐个进入现有工具目录，继续使用已有的工具过滤、按需文档和执行生命周期。

这是跨目录、协议投影和执行入口的接入改动，需要相关模块的回归验证；不改变化学方法或科学验收标准。

## 接法比较

1. **逐工具注入（用户已选）**：外部声明在共同目录适配一次，传统调用、JavaScript 调用、文档和执行使用相同定义。初次改动涉及目录的本地类绑定，但之后新增 MCP 服务只需改连接配置。
2. **统一 MCP 网关（未采用）**：只注册一个查询／调用工具，Agent 再传服务名、工具名和参数。改动较小，但外部工具没有进入既有逐工具过滤与契约加载机制。

不为这次接入另建 Python 插件框架。现有 `plugins` 的知识检索和事件 hook 继续承担原职责；MCP 是向共同工具目录供给外部声明和调用器的连接来源。

## 接入前的代码限制与迁移范围

| 位置 | 当前限制 | 本次调整 |
| --- | --- | --- |
| `cloudra/tools/__init__.py:20–60` | `ToolEntry` 绑定本地 `Tool` 类与 Pydantic 输入输出类 | 共同条目支持原始 JSON Schema；本地类只留在本地适配处 |
| `cloudra/tools/__init__.py:85–128` | 只加载固定 manifest，进程缓存 | 保留内置发现缓存；外部条目与连接归应用实例持有 |
| `cloudra/runtime_v2/adapters.py:47–58` | 生成声明时实例化本地工具 | 从共同条目读取声明 |
| `cloudra/runtime_v2/adapters.py:1082–1195` | 执行时直接实例化、验证 Pydantic 类型 | 保留本地行为；外部调用使用 MCP 适配器，公共准入和结果持久化共用 |
| `cloudra/runtime_v2/tool_catalog.py:334–353` | 只认识 `model_json_schema()` | 统一读取条目的 JSON Schema，复用既有声明渲染 |
| `cloudra/tools/documentation.py:66–87` | 文档版本依赖 Pydantic schema 类 | 目录、文档和版本摘要使用同一份声明 |
| `cloudra/tools/capabilities.py:19–21、67、97` | 语义投影直接读取固定 manifest | 投影从同一目录获得元数据，内置语义仍由已有登记定义提供 |
| `cloudra/dag/supervisor_tools.py:248–269` | 受限执行器也直接依赖本地工具类 | 检查并迁移公共声明读取；MCP 不自动取得 Supervisor 资格 |
| `cloudra/runtime_v2/agent_host.py:379–403` | 创建 Agent 时展开 `*` 并保存工具列表 | 启动发现先完成，新 Agent 使用合并后的目录 |

当前插件登记入口的完整代码如下，尚未提供工具登记 hook：

```python
# cloudra/runtime_v2/plugins.py:49–58
def register_plugin(plugin: Any) -> None:
    """Register a plugin instance (idempotent by identity)."""
    if not getattr(plugin, "name", None):
        raise TypeError(f"plugin {plugin!r} has no name")
    if any(existing is plugin for existing in _plugins):
        return
    _plugins.append(plugin)
    # Capability detection: a plugin with search() is also a library provider.
    if hasattr(plugin, "search"):
        register_knowledge_provider(plugin)
```

它调用的知识源登记完整代码为：

```python
# cloudra/runtime_v2/knowledge.py:86–89
def register_knowledge_provider(provider: KnowledgeProvider) -> None:
    if not hasattr(provider, "search"):
        raise TypeError(f"knowledge provider {provider!r} has no search()")
    _providers.append(provider)
```

## 配置接口

新增一个运维配置 `mcp_servers`，默认空字典。键是本机配置中稳定的服务标识；每个值为下面两种连接声明之一。

| 字段 | 类型 | 必填／默认 | 含义 |
| --- | --- | --- | --- |
| `command` | `str` | stdio 必填 | 本地进程命令，与 `url` 互斥 |
| `args` | `list[str]` | stdio 可选，`[]` | 命令参数 |
| `env` | `dict[str, str]` | stdio 可选，`{}` | 显式传给子进程的环境变量 |
| `cwd` | `str \| None` | stdio 可选，`None` | 子进程工作目录 |
| `url` | `str` | HTTP 必填 | MCP Streamable HTTP 地址，与 `command` 互斥 |
| `headers` | `dict[str, str]` | HTTP 可选，`{}` | HTTP 鉴权等请求头 |
| `permissions` | 现有 `PermissionSet` | 两类连接均可选，默认要求 `read`、`script` | 本机操作者为该服务工具声明的权限需求，复用既有权限检查 |

`permissions` 复用现有字段：`read/write/manage/script/destructive` 均为布尔值；默认 `read=True, script=True`，其余为 `False`。远端工具的注解不负责授予本地权限。配置不包含科学阈值或领域选择。

配置示例：

```yaml
mcp_servers:
  local_lab:
    command: python
    args: ["/absolute/path/lab_mcp_server.py"]
  remote_lab:
    url: https://lab.example.org/mcp
    headers:
      Authorization: "Bearer <由操作者填写的令牌>"
```

用 Pydantic 模型验证两种连接的字段和互斥关系。配置错误明确指出服务与字段。凭据不出现在工具 schema、模型上下文或配置展示接口中。

首版支持 HTTP 预配置请求头；不增加交互式 OAuth 流程。

## 权威目录与适配边界

共同目录条目提供：工具公开名称、简述、完整说明、输入 JSON Schema、返回数据 JSON Schema、现有权限与 DAG 元数据，以及可等待的调用入口。

- 内置工具：由现有 manifest 和 Pydantic 类生成目录条目，Pydantic 输入验证、工具构造、`safe_call` 和输出类型检查保持在本地适配处。
- MCP 工具：从 SDK 返回的类型化声明生成目录条目，保留外部原始 JSON Schema，不手写 JSON Schema 到 Pydantic 的转换器，也不把它套成只支持固定字段的本地 object schema。
- schema 投影、目录简述、按需文档、文档摘要和执行路由使用相同条目。删除这些调用方重复的 schema 类型判断。
- 应用实例持有外部目录与连接，避免两个 core 或测试实例误用彼此的连接。内置模块发现缓存可以继续共用。
- 外部名称由程序映射为合法、稳定、唯一的 `mcp__服务__工具` 形式；内部保存原始工具名，调用服务时使用原名。同名或映射冲突明确报错，不能覆盖本地工具。名称转换与摘要均由程序负责，Agent 不维护。

实现者可以决定最少的内部方法名和数据类型，但不能另建通用插件框架、并行工具目录或第二套执行生命周期。

## 启动、调用与关闭路径

实现路径：

1. 应用创建时读取并验证 `mcp_servers`，构造应用所拥有的目录与 MCP 连接管理对象。
2. 应用异步 lifespan 启动时，为每个服务创建独立的连接所有者任务，用官方 SDK 打开连接并分页读取 `tools/list`。每个 SDK 上下文由同一个任务打开、关闭；单个服务断线的取消不会传播到应用生命周期。工具发现完成后才接受新 Agent 的执行请求。
3. 每个远端工具适配为共同目录条目。新建 Agent 按现有角色策略展开工具列表，不增加领域参数。
4. 模型看到经过现有过滤的工具目录；JavaScript 模式通过现有 `get_tool_docs` 加载契约；传统模式读取同一份输入 schema。
5. 实际调用继续进入现有 `InvocationService`，按原顺序进行策略检查、登记请求和开始事件，再由共同目录分派到本地适配器或 MCP 调用器。
6. MCP 调用器按内部映射把原始工具名和 JSON 参数交给 SDK `call_tool`。本地用 Pydantic 校验 MCP 定义和 JSON 参数载体，外部参数的完整业务 schema 由服务端校验；不猜测、丢弃或自动改写字段。
7. 结果转换成现有 `ToolResult`，交回相同的结果持久化、后处理和模型反馈流程。MCP 业务错误映射为失败结果；连接中断等异常沿现有未知效果错误路径处理，不自动重试工具执行。
8. 关闭时先等本 core 的 Agent 执行退出，再由同一异步所有者关闭 MCP 连接及其拥有的 stdio 服务进程。异步上下文的打开与关闭由同一生命周期任务持有；不按一次工具调用反复拉起服务器。Cloudra 不主动终止量子化学作业。

配置在启动时生效。首版不做运行中配置热更新；恢复的既有 Agent 保留其持久化工具列表，新建 Agent 使用新的目录。目录变化不暗中修改既有能力快照。

旧能力列表中的 MCP 工具若已不在当前目录，公共投影隐藏该工具，已加载文档同步失效；原生工具仍可正常使用。

## 结果、失败与科学证据

- `ToolResult.data` 保留 MCP 内容块、结构化内容和业务错误标志；不把远端完整结果压成一段字符串。字段命名选定后，两种传输共用同一个转换函数。
- MCP 的 `outputSchema` 约束结构化内容，不等同于完整 MCP 结果 envelope。目录中面向 JS 的返回 schema 必须描述 Cloudra 实际返回的 envelope，并把远端输出 schema 放在结构化内容字段内。
- 文字内容进入现有结果摘要；图片内容按现有产物机制适配。其它内容块原样保留为结构化数据，不能伪造本机文件路径，也不能静默删除。
- 单个服务连接或发现失败时，明确记录服务名与原因，该服务不注入工具；其余已配置服务及内置工具继续可用。显式配置了 MCP 而未安装 SDK 时直接指出安装方式。
- 外部工具默认为普通业务工具：可记录、无本地科学事实派生器、无 Supervisor 资格。远端说明和注解不自动产生科学验收事实。
- MCP 不携带 Cloudra 的计算意图或证据适配契约，因此本次不声称外部计算工具自动受内置 QM 意图识别、计算方法约束或 `dag_compute_entry` 语义覆盖；科学事实仍须通过现有真实证据路径建立。接入不会修改现有科学验收标准。

## 依赖与验证

使用官方 `mcp` Python SDK 当前稳定 v2 系列（依赖限定 `>=2,<3`）。提供 `mcp` 安装 extra，`all` 包含它；未配置 MCP 的安装不强制引入 SDK。HTTP 的鉴权和连接由 SDK 支持的异步 HTTP 客户端提供。

只运行相关检查：`compileall` → `ruff` → 工具目录、协议投影、按需文档、权限、MCP 生命周期和相关场景测试，不跑全套。

关键行为用例共用，按 stdio／HTTP 参数化：

- 同一个工具经发现后在目录、传统 schema、JS 声明、按需文档中一致，参数必填、默认值和嵌套定义保留。
- 经两种传输调用相同工具，结构化结果、内容块和业务失败的公共结果一致。
- 参数错误、连接失败、重名、禁止权限均清楚失败，不误调本地同名控制工具，不重复执行已发出的调用。
- 真正启动一个轻量本地 MCP fixture，分别回放 stdio 和回环 HTTP，验证发现、调用与收尾；无需真实第三方服务或 API Key。
- 新 Agent 可见、旧 Agent 能力快照保持原语义；两个应用实例的外部目录与连接互不污染。
- 回归既有内置工具，特别是 Pydantic 严格输入、权限判断、Supervisor 受限入口和结果落库。

## 官方资料

验证记录：改动的 21 个 Python 文件通过 compileall、Ruff；283 项相关测试通过，包括真实 stdio／HTTP fixture、慢调用、断线隔离、权限与审批、旧会话恢复和两种 Agent 调用协议。未运行全套测试或真实量子化学计算。

- [MCP 工具协议](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)：外部工具声明、发现和调用，名称仅在单个服务内唯一。
- [官方 Python SDK 客户端](https://py.sdk.modelcontextprotocol.io/client/)：类型化的工具列表、分页和调用结果。
- [官方 SDK 连接方式](https://py.sdk.modelcontextprotocol.io/client/transports/)：stdio 与 Streamable HTTP 共用异步客户端生命周期。
- [官方 SDK 安装说明](https://py.sdk.modelcontextprotocol.io/get-started/installation/)：当前稳定版本为 v2，项目 Python 版本要求满足 SDK 要求。
