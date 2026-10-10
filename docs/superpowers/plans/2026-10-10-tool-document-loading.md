# Tool Document Loading Implementation Plan

状态：七项任务完成，独立审阅三项重要问题已用失败测试复现并修正；尚未合并、推送或部署。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持 LLM 与语义筛选两种初始文档选择方式，保留全部可用工具简介并按需读取详细契约。

**Architecture:** 注册表提供简介，现有 schema 渲染器生成详情。默认选择复用主 Agent 有效 LLM 配置；Jev 与 HTTP Reranker 分别适配、统一产出合法名称列表。选择记录走会话事件投影，原 capabilities 继续控制执行。

**Tech Stack:** Python >= 3.11、POSIX、Pydantic v2、asyncio、现有 LLMClient、httpx.AsyncClient、React/TypeScript、pytest 场景与 Playwright。

**Spec:** [已确认需求](../specs/2026-10-10-tool-document-loading-design.md)

## Global Constraints

- 默认 `llm`，无需选择模型槽位或新 API；语义模式支持 Jev 和已部署的标准 rerank 服务。
- 本期降低默认 JavaScript 文档量；显式 traditional 保持原 schema 投影。
- 选择只影响预加载，不覆盖 capabilities；完整能力简介和读取入口保留。
- 首次真实任务选择一次；工具轮次、审批恢复、后台唤醒和普通重启不重选；显式 context_reset 是新边界。
- 契约来自真实 Pydantic 模型；名单与结构校验不用正则。异步操作不得同步读盘、查 SQLite 或请求网络。
- 不增工具类别子 Agent、通用 provider 插件、向量库或模型下载管理，不改科学输入、验收和计算保活规则。
- 仅改列出的文件并保留无关材料；执行前按 using-git-worktrees 技能准备隔离环境。
- 每任务改完代码先 `uv run python -m compileall -q cloudra tests`，再 `uv run ruff check cloudra tests`，最后运行任务列出的聚焦测试；不跑本地全套测试。

## Review Focus

1. 图片/结构化输入保留任务文本与图片标记，不用 UI 摘要或父会话代替；Tasks 4–5。
2. 主请求失败、取消或中断后，不重复选择、不丢任务；Task 5。
3. 窄 capabilities、只读 Supervisor 可读合法说明，隐藏工具不泄露；Task 2。
4. 折叠详情保留名称/version，用户引用相似文字不被误删；Task 6。
5. 切后端、清凭据的错误明确呈现，不静默换策略；Tasks 3、7。

## File Structure

新增 `cloudra/tools/documentation.py` 管说明模型和生成；`cloudra/tools/Skilltool/get_tool_docs.py` 管只读入口；`cloudra/runtime_v2/tool_selection.py` 管选择策略与结果。现有 registry、adapter、context/event、compaction、配置 API 和全局设置 UI 的挂接分别列在下方任务。

本期仅全局配置选择策略与语义连接，在首次选择时取快照。Agent 自己的模型覆盖继续参与有效 LLM 设置解析；不增加每 Agent 的筛选连接配置。

### Task 1: 工具简介与真实文档来源

**Files:** Modify `cloudra/tools/registry.py`、`cloudra/tools/__init__.py`、`cloudra/runtime_v2/tool_catalog.py`；Create `cloudra/tools/documentation.py`、`tests/test_tool_documentation.py`。

**Interfaces:**
- ToolRegistration/ToolEntry 增加 `summary: str` 与 `skill_references: tuple[tuple[str, str], ...]`，参考元组为现有 get_skill 的 skill_name/reference。
- 严格模型：`ToolCapabilitySummary(name, summary)`；`ToolDocReference(skill_name, reference)`；`ToolDocument(name, revision, content, references: tuple[ToolDocReference, ...])`，其他字段为字符串。
- `validate_tool_names(value: Any, *, allowed_names: Collection[str]) -> tuple[str, ...]`。
- `tool_capability_summaries(names: Sequence[str], *, entries: Sequence[ToolEntry]) -> tuple[ToolCapabilitySummary, ...]`。
- `render_tool_declaration(entry: ToolEntry) -> str`，从现有循环提取；`build_tool_documents(names: Sequence[str], *, allowed_names: Collection[str], entries: Sequence[ToolEntry]) -> tuple[ToolDocument, ...]`。

- [x] **Step 1: 写失败测试。** 用三个真实 Pydantic 假 entry 验证简介无完整类型、详情保留条件字段和编号、源契约变化使 revision 改变。非法类型/未知名/越权名整体失败，重复名稳定去重、空数组合法：

```python
assert validate_tool_names(["read", "read"], allowed_names={"read"}) == ("read",)
assert validate_tool_names([], allowed_names={"read"}) == ()
with pytest.raises(ValueError):
    validate_tool_names(["read", "hidden"], allowed_names={"read"})
```

- [x] **Step 2: 测试应因新接口不存在而失败。** `uv run pytest -q tests/test_tool_documentation.py`。
- [x] **Step 3: 实现接口，补齐所有真实登记简介。** 禁止截断长说明生成简介。完整声明复用现有渲染，避免再次模式过滤丢失合法 DAG 字段；revision 用确定性 JSON/hash。统一例子展示 `await tools.NAME(args)`、is_success 和显式输出，args 来自任务声明，不增加化学方法默认。
- [x] **Step 4: 验证零失败。** `uv run pytest -q tests/test_tool_documentation.py tests/test_tool_registry.py tests/test_runtime_v2_tool_catalog.py`，保留现有 tuple、union 和条件约束测试。
- [x] **Step 5: 提交。** `feat: add source-backed tool documentation`。

### Task 2: 文档入口与简短 JS 协议

**Files:** Create `cloudra/tools/Skilltool/get_tool_docs.py`、`tests/test_get_tool_docs.py`；Modify `cloudra/tools/registry.py`、`cloudra/runtime_v2/tool_catalog.py`、`cloudra/runtime_v2/adapters.py`、`cloudra/runtime_v2/agent_host.py`。

**Interfaces:**
- 输入 `GetToolDocs_input_schema(names: list[StrictStr])`；输出 is_success/message/documents，documents 为 list[ToolDocument]。
- `_LegacyAgentBridge._runtime_agent` 仅供该工具获取当前 Agent 视图；不序列化给模型。工具解析授权集合后，通过 to_thread 调 Task 1 生成器。
- `tool_capability_manifest(agent: AgentSession, tool_names: Iterable[str]) -> str` 沿原角色/模式/配置/视觉过滤并稳定排序。
- javascript_instructions 仅保留基础协议、ToolResponse、get_tool_docs 契约和全部合法简介；其他业务完整类型按需读取。

- [x] **Step 1: 写失败测试。** JS 有全部合法简介、无复杂业务类型；Supervisor 可读自己的合法说明而不能读隐藏生产工具。越权请求整体失败，无 READ 拒绝，empty 选择保留读取入口。
- [x] **Step 2: 验证新增行为失败。** `uv run pytest -q tests/test_get_tool_docs.py tests/test_runtime_v2_tool_catalog.py`。
- [x] **Step 3: 注册只读入口。** dag_observe=False、supervisor_access=skill_read。可读 Agent 增加 get_tool_docs 基础能力，业务名单不变；明确禁止基础入口时拒绝启用本特性。沿正常 InvocationService/LegacyToolExecutor 校验，不设绕过执行器的专用调用。
- [x] **Step 4: 验证零失败。** `uv run pytest -q tests/test_get_tool_docs.py tests/test_runtime_v2_tool_catalog.py tests/test_runtime_v2_adapters.py`。通过 executor 读取并调用未预载工具，断言 guest 权限不变；traditional 和直接控制路由继续通过。
- [x] **Step 5: 提交。** `feat: load tool contracts on demand`。

### Task 3: 全局配置与读写 API

**Files:** Modify `cloudra/infra/config.py`、`cloudra/services/api_v2/models.py`、`cloudra/services/api_v2/routers/runtime.py`；Test `tests/test_config_mutate.py`、`tests/test_runtime_v2_core.py`。

**Interfaces:**
- `CloudraConfig.tool_document_loading: ToolDocumentLoadingConfig`，strategy=llm|semantic（默认 llm），semantic_backend=jev|reranker（默认 jev）。
- Jev 段：endpoint/model/key/min_probability/max_tools；Reranker 段：endpoint/model/key/min_score/max_tools。max_tools 可省略；边界是启用该语义后端的必需配置，不填未经验证的默认阈值。概率范围 [0,1]，分数有限，数量为正整数；Reranker 允许空 key。
- GET `/api/v2/runtime/config` 增加脱敏段；PATCH `/api/v2/runtime/config/tool-document-loading` 使用 ToolDocumentLoadingPatch。省略 key 保留，空字符串清除，响应仅给 key_set。

- [x] **Step 1: 写失败测试。** 默认 llm、两个后端 YAML 往返、缺必需配置、非法分数、并发与脱敏。清除正在使用的必要 key 必须同时切回 llm，否则整次更新失败。
- [x] **Step 2: 验证新增字段/端点失败。** `uv run pytest -q tests/test_config_mutate.py tests/test_runtime_v2_core.py -k 'tool_document_loading or runtime_config'`。
- [x] **Step 3: 实现配置与 API。** YAML 显式解析新段，非法值不被广泛 except 吞掉；在线程中整段合并、重验，再经 mutate_config 保存。复用原 YAML 序列化，不增 LLM 槽位。
- [x] **Step 4: 验证零失败。** 重跑 Step 2 及 `uv run pytest -q tests/test_no_sync_on_loop.py`。
- [x] **Step 5: 提交。** `feat: configure tool document selection`。

### Task 4: 默认 LLM 与语义后端

**Files:** Create `cloudra/runtime_v2/tool_selection.py`、`tests/test_runtime_v2_tool_selection.py`；Modify `cloudra/runtime_v2/adapters.py`、`cloudra/runtime_v2/turn_pipeline.py` 的 LLMProvider、`tests/agent_scenarios.py` 的 ScriptedProvider；Test `tests/test_runtime_v2_adapters.py`。

**Interfaces:**
- ToolSelectionResult：status=selected|empty|failed、names: tuple[str,...]、source=llm|jev|reranker、catalog_revision、error_code、usage: dict[str,int]、duration_ms。
- `async ToolDocumentSelector.select(*, agent: AgentSession, task_messages: list[dict], resolved_settings: RuntimeSettings, candidates: tuple[ToolCapabilitySummary,...], config: ToolDocumentLoadingConfig) -> ToolSelectionResult`；具体类由 TurnPipeline 调用，不增 provider 注册层。
- `async LLMProvider.select_tool_names(self, agent: AgentSession, messages: list[dict[str,Any]], *, resolved_settings: RuntimeSettings) -> LLMResponse`。
- 真实和 ScriptedProvider 实现新增选择方法。选择使用主 provider 的 resolve_effective_settings 解析副本；主请求沿用既有有效配置解析，不扩展 complete 的调用协议，也不另设模型槽位。

- [x] **Step 1: 写失败测试。** 捕获 adapter 请求，验证选择继承当前 Agent 的有效 model/base_url/key；选择无 tools/搜索/父会话。代码围栏、未知名、tool_calls 失败，[] 为 empty；图片输入保留任务文本和图片标记。
- [x] **Step 2: 验证新接口失败。** `uv run pytest -q tests/test_runtime_v2_tool_selection.py tests/test_runtime_v2_adapters.py -k 'tool_selection or selection_client'`。
- [x] **Step 3: 实现无工具选择请求。** 复用 _make_client、超时、额度记账、usage、finally close；json.loads 后使用 Task 1 校验，记 kind=tool_selection。不用普通 complete(tools=[])，它仍可能投影 js_exec；不执行返回调用或修复重问。
- [x] **Step 4: 实现 HTTP 并用 MockTransport 验证。** Jev 为 state/model/questions，每工具一个 Noul，instructions 含简介，答案完整且概率合法。rerank 为 model/query/documents，results 含 index/relevance_score；索引完整、唯一、合法，分数有限。分别按各自边界筛选，同分保留原顺序，最后应用 max_tools；不把分数转成校准概率。
- [x] **Step 5: 验证零失败。** `uv run pytest -q tests/test_runtime_v2_tool_selection.py tests/test_runtime_v2_adapters.py tests/test_no_sync_on_loop.py`。覆盖超时、认证、JSON、缺答案、重复/越界索引、NaN、多选与全不相关；llm 不建语义 client，取消传播并收尾连接/记账，不换后端。
- [x] **Step 6: 提交。** `feat: select initial tool documents with configured models`。

rerank 字段依据 [vLLM 官方示例](https://docs.vllm.ai/en/v0.17.1/examples/pooling/score/)。配置使用完整 endpoint，支持已部署服务的 /rerank 或 /v1/rerank 地址，不猜测路径。

### Task 5: 首次任务挂接与持久恢复

**Files:** Modify `cloudra/runtime_v2/core.py`、`cloudra/runtime_v2/events.py`、`cloudra/runtime_v2/apply.py`、`cloudra/runtime_v2/turn_pipeline.py`、`cloudra/runtime_v2/adapters.py`；Test `tests/test_runtime_v2_runner.py`、`tests/test_runtime_v2_persistence.py`、`tests/test_runtime_v2_context_cache.py`、`tests/test_agent_scenarios.py`。

**Interfaces:**
- ToolSelectionRecord 在 tool_selection.py 定义：status=started|selected|empty|failed、selection_id/source/catalog_revision/task_message_ids/names/error_code/usage/duration_ms；started 无结果名单。
- `async ContextBroker.record_tool_selection(*, agent: AgentSession, run_id: str, record: ToolSelectionRecord, messages: list[dict]) -> None`。
- 新事件 tool_documents.selection_started/selection_finished；经 _persist_then_apply 写入 prefix_meta[tool_selection]。finished 同时追加文档或失败说明；owner 的恢复/snapshot/current_prefix/adopt 传递记录。

- [x] **Step 1: 写失败场景。** 空会话零选择，首条实际输入一次，后续任务不重选；不用 current_task。selected/empty/failed 能恢复；started 中断恢复为明确 failed，不重复请求。
- [x] **Step 2: 验证新事件/集成行为失败。** `uv run pytest -q tests/test_agent_scenarios.py tests/test_runtime_v2_runner.py tests/test_runtime_v2_persistence.py -k 'tool_documents or tool_selection'`。
- [x] **Step 3: 在 commit_input 后挂接。** 原任务和基础前缀先持久化；仅 JS、有真实 input_user_messages、无选择记录时运行。网络前存 started，结果和消息原子保存，再从 broker 读取主请求 messages，媒体解析在后；不用 context_fresh/run 轮次判定首次。
- [x] **Step 4: 同步 owner 与恢复。** snapshot 保留最新选择记录；详情是带来源/名称/version 的追加消息，不计入 prefix_len。持久化失败不发主请求；started 恢复仅记中断失败，靠读取入口继续。
- [x] **Step 5: 验证幂等与零失败。** 扩展 test_retry_reuses_identical_prepared_request、test_message_reopen_preserves_session_context、test_restored_session_context_is_reused_byte_identical；审批/唤醒不重复选择或详情，capabilities/计算账本不变。重跑 Step 2 及 `uv run pytest -q tests/test_runtime_v2_context_cache.py tests/test_no_sync_on_loop.py`。
- [x] **Step 6: 提交。** `feat: persist initial tool document selection per context`。

### Task 6: 文档版本与上下文折叠

**Files:** Modify `cloudra/runtime_v2/adapters.py`、`cloudra/runtime_v2/agent_runner.py`、`cloudra/runtime_v2/compaction.py`；Test `tests/test_runtime_v2_compaction_integrity.py`、`tests/test_runtime_v2_context_cache.py`、`tests/test_get_tool_docs.py`。

**Interfaces:** compact_context 摘要前把宿主标记的详情变成名称/version/重读指引，保留消息位置/数量和原 history 的版本守卫。current_prefix 只重建短目录、基础协议与动态快照，保留选择记录、不补回详情。

- [x] **Step 1: 写失败测试。** 摘要输入无详情 schema、仍有名称/version；用户相似文字保留。折叠后不重选，重新读取返回最新契约，变更说明明确替代旧版。
- [x] **Step 2: 验证详情残留或元数据丢失。** `uv run pytest -q tests/test_runtime_v2_compaction_integrity.py tests/test_runtime_v2_context_cache.py tests/test_get_tool_docs.py -k 'tool_document or tool_selection or version_guard'`。
- [x] **Step 3: 实现来源识别。** 初始包与真实 get_tool_docs 结果均由宿主标记，仅按来源/类型折叠，不猜正文。context_reset 清记录并允许重新首次选择；普通 restore 保留。
- [x] **Step 4: 验证零失败。** 重跑 Step 2 与异步守卫，保留 test_install_compacted_version_guard_abandons_stale_candidate 的竞态保护。
- [x] **Step 5: 提交。** `fix: retain tool discovery across context compaction`。

### Task 7: 设置界面与实际效果验收

**Files:** Modify `frontend/src/GlobalConfig.tsx`、`frontend/src/types.ts`、`frontend/src/api.ts`、`README.md`、`scripts/README.md`；Create `frontend/e2e/tool-document-loading.spec.ts`、`scripts/benchmarks/tool_document_selection.py`、`tests/test_tool_document_selection_report.py`。

**Interfaces:** UI 对齐 Task 3 GET/PATCH；显示现有模型/语义筛选，后者展开两个后端的连接及独立规则。效果脚本仅调用选择模型、读取契约，不执行科学工具；输入固定任务和允许名称，输出选择结果、耗时/用量、文档量及漏选/无关项。

- [x] **Step 1: 写失败 e2e。** 用现有 frontend/e2e/fixtures.ts API mock，测默认无新 key、各后端字段、省略 key 保留、清除与切回 llm 原子提交、错误展示和刷新恢复。
- [x] **Step 2: 验证新行为失败。** `npm --prefix frontend run test:e2e -- tool-document-loading.spec.ts`；缺浏览器明确记录环境限制，不运行全套测试或下载模型。
- [x] **Step 3: 实现单一全局设置段和使用说明。** 不在创建页重复连接配置，默认路径不依赖语义服务。
- [x] **Step 4: 写效果脚本和报告测试。** 固定样本含 TS、QM、日志、文献、DAG、图片、多工具和解释请求，允许多种正确组合；测试缺必要工具、无关项、正确组合及服务未验证，运行 `uv run pytest -q tests/test_tool_document_selection_report.py`。真实后端可用时测实际用量/选择，mock 不代表真实效果。
- [x] **Step 5: 整体验证。** 按 Global Constraints 先语法/ruff，再测前述相关文件和异步守卫；执行 `npm --prefix frontend run build`、新 e2e、`git diff --check`。修复新失败并聚焦重测，不改科学流程或 Gold/评分。
- [x] **Step 6: 汇总并提交。** 记录三个来源的真实连接覆盖、文档 token、选择效果和启动成本；验证后再建议语义边界。提交 `feat: expose and validate tool document loading settings`。

## Plan Self Review

Tasks 1–2 覆盖目录/契约/读取，3–4 覆盖配置/策略，5 覆盖首次任务与恢复，6 覆盖版本/折叠，7 覆盖界面/效果。Review Focus 五项都有对应行为测试；接口名称、Pydantic 类型及跨任务依赖一致，无全量文档回退或加载名单授权。

## Execution Handoff

建议 Native：我在当前会话顺序实现，最后由独立审阅者检查整体。七个任务共享 provider、上下文和事件接口，顺序执行减少交接开销。也可选择 Subagent-driven：每任务独立实现与审阅。

实施前审阅本计划并选择执行方式；计划不代表功能已实现或测试已通过。
