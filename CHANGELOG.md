# Changelog

All notable changes to the Cloudra project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-11-01

### 修复
- 为 Python 3.11–3.13 CI 矩阵安装物种证据与公开 JS 场景实际所需的 RDKit 和 JS 宿主依赖。
- 修复旧运行收尾期间显式重启丢失调度的竞态，并用事件栅栏稳定覆盖该边界。
- 更新前端 E2E 以验证默认 Acid 外观及显式展开的新建项目表单，恢复完整浏览器回归。
- 整理研究辅助脚本的 Python 格式，保留其计算内容与现有全库 Ruff 检查。
- 将可达性来源诊断保留在报告中，避免写入版本化 Benchmark 图；同步 F4 生成器与已提交的 Lewis 加合物参考起点。
- 在几何连通性回退路径复用现有立体化学检查，拒绝与声明构型不符的几何。
- 隔离测试节点容量与缺失 xTB 的 PATH 条件；数值 fixture 使用机器舍入级容差并保留端点精确比较。
- 恢复中英文默认调用协议说明，并让传统协议全链测试通过真实工具交付机制图。

### 正式发布
- 版本从 `0.1.0rc1` 更新为 `0.1.0`。
- 前端默认采用 Acid 风格，保留用户已保存的风格选择。
- 更新中英文项目首页和贡献指南，集中配置、研究数据与复现入口。
- 下方保留此前开发记录；现行评分定义和参考证据限定以 `cloudra/benchmark/README.md` 与 `gold_compute/evidence/REPRODUCE.md` 为准。

### 此前开发记录（2026-09-22 至 2026-10-20）

### 多后端量化计算一致性与底层单源 (Multi-Backend QM Consistency)
- **多后端行为一致性与逻辑单源权威原则**：
  - 确立同一业务含义只维护一套权威实现的工程红线。意图识别、参数校验、单位转换、状态判定与科学验收共用权威单源，各后端（Gaussian / ORCA、本地 / SSH / Slurm）仅负责原生语法、编号与执行机制差异。
  - 严禁在调用入口处分散复制打补丁；发现重复实现必须在本次涉及范围内合并并迁移调用方，共用问题统一在共同入口修复。
- **Gaussian 与 ORCA 原生参数与执行保真**：
  - 保留 Agent 原生声明的量化参数与基组配置（如 def2 族基组拼写规范、CPCM 溶剂化参数），统一输入生成（`qm_input_writer`）、作业提交与执行校验。
  - 修复 Gaussian 优化步数预算（step budgets）与内存/核心数分配策略；严格识别 Gaussian 与 ORCA 的正常终止原生文本标记（如 ORCA `TERMINATED NORMALLY` 与 Gaussian `Normal termination`），避免单纯依赖 cclib 解析导致的误判。
- **IRC 双向端点与方向证明单源统一**：
  - 确立端点优化确证标准：同一个 TS 的真实双向 IRC 末帧经收敛优化至正确的零虚频极小值（0 imaginary modes），即构成物理成立的方向证明；几何区间仅作辅助提示，不否决已成立的端点优化事实。
  - 提取规范化端点证据（canonical endpoints）：修复直接计算作业的端点来源识别，严格保留配对电荷态与自旋多重度，记录量化自洽审计信息。
- **Slurm 与计算作业守卫加固**：
  - 计算作业取消严格走数据库账本标记（`cancel_requested`）与底层文件排他锁（flock）探测，在确认底层进程真正退出前，严禁将持有锁的作业标记为失败。
  - 配置并注入 ORCA MPI 运行环境与集群环境 modules，Slurm 资源校验从脆弱的正则表达式全面重构为显式规则检查。

### 反应机理图 (DAG) 证据交付与科学验收体系
- **科学证据与流程督导分权**：
  - 彻底解耦流程记录与科学验收：阶段绑定或 Supervisor 审阅不能充抵缺失的物理证据。稳定物种极小值必须具备零虚频（0 imaginary modes），过渡态（TS）必须且仅允许一阶鞍点（1 imaginary mode），并绑定不可变的原始日志字节凭据。
  - 移除流程介入配额（intervention quotas），规范退出审计门禁（StopGate），结题时严格审查所有声明边与物种的绑定事实。
- **物种状态与反应拓扑单点维护**：
  - 在全流程保持分子结构的 RDKit Mol 原生状态与原子拓扑对应关系，推断的键级变化仅作建议；修复分离产物（separated products）基于 IRC 端点证据的自动验证。
  - 彻底废弃历史过渡过程模型、`AddLink` 与事件重放垫片，精简数据结构。

### 50 题 Benchmark 体系与 3 级法医评分
- **正式 50 题 Benchmark 题库定版**：
  - 题库结构收敛为 50 道正式基准题：简单（Easy, 20题）、普通（Normal, 10题）、困难（Hard, 10题）、不可达/排阻（Impossible, 10题）；淘汰并替换旧题目（如 NR1, NY3, HI1, HL1 等）。
  - 方法白名单策略严格限制在标有 Benchmark 属性的项目中生效，普通科研探索不再受限。
- **3 级法医评分模型（Forensic Scoring Pipeline）**：
  - 综合得分公式严格执行用户裁定权重：`Composite = 0.1 * Graph + 0.3 * Self-consistency + 0.6 * Accuracy`。
  - **金标准边自洽回捞（Gold-edge Clawback）**：声明命中 Gold 关键反应步但虚频错误或 IRC 跑偏时，自洽性得 0 分并倒扣图结构分。
  - **造假/数据不一致 Fail-Loud 短路**：声明能垒无法从真实日志中闭环推导且与标准答案冲突时，触发短路保护，自洽性与准确度归零。
  - **IMP 负例题目交付判定**：以最终交付事实为准；正确否定不可达通道得满分，错误宣称可达或虚构能垒重罚，探索尝试后正确否定不扣分。
  - 能垒分母统一以对应物种的稳定极小值（稳定中间体）为基准，实际 IRC 拓扑连通与能量参照分别独立记录。
- **Google Drive 证据交付包与原件解耦**：
  - 将 886 份经验证的真实量化输出日志与几何结构归档至 Google Drive 独立交付包（`gold_compute/evidence/DELIVERY.md`），仓库内只保留不可变 SHA-256 校验清单、逐题索引与复现指南（`REPRODUCE.md`），保持代码库轻量。
  - 归档并回放真实 Benchmark 运行中的 ORCA/Gaussian 成功与失败用例（M3, NU3, L1, M17 等），保证打分引擎的确定性。

### 过渡态 (TS) 搜索流水线与化学工具箱强化
- **TS 初猜与质量诊断规范 (`ts-initial-guess` skill)**：
  - 确立过渡态初猜的三级梯队纪律（`ts_prepare` → 映射插值/NEB → 松弛扫描），确立首步熔断机制（first-step circuit breaker）与接受度核算。
  - 新增虚频振动模成分分析（imaginary mode composition）：提取并展示虚模主要移动原子的贡献，严格拦截落在反应中心重原子之外的伪鞍点或软模。
- **计算准备自动化与断点续跑**：
  - `ts_prepare` 支持自动补全遗漏的准备输入并回显动作，具备基于不可变字节指纹的断点恢复机制，无需冗余重跑扫描。
  - 强化内坐标变换中的基团替换功能（`replace_group`），以及基于预算感知的构象筛选。

### Runtime v2 事件驱动内核与通信加固
- **事件计数器与快照解耦**：
  - 事件序列计数器完全独立于私有快照的高水位线，增量流（SSE）恢复严格基于有界窗口重放，彻底修复在多项目交错写入或重启时丢事件的隐患。
  - 新增结构化运行失败分类（`failure_kind`），使“执行过程终止”与“科学目标已验证完成”在状态与 UI 上明确区隔。
- **协作子系统与 Launch Group 事务化**：
  - 规范 Agent 间消息投递的唯一步骤；子 Agent 派发通过 Launch Group 事件持久化，重启时对账恢复且不重复执行。
  - 子 Agent 完成时返回结构化 manifest，明确汇报执行结论与证据归属。
  - 引入离线 Token 估算器与上下文压缩预算控制，避免大上下文下的异常截断。
- **MCP (Model Context Protocol) 工具投影**：
  - 新增 MCP 协议支持，允许外部智能体客户端通过标准 MCP 规范调用 Cloudra 的化学与量化工具箱。
- **知识库 Chem-KB 架构精简**：
  - 全面转向基于知识图谱关键词直接定位并检索完整原文字段的极简模式，剔除旧版离线 BGE 向量微服务的运行时强依赖。
- **工程交规与开源协议变更**：
  - 仓库核心代码开源协议正式由 MIT 变更为 **AGPL-3.0-or-later**（`cloudra/skills/` 保持 MIT）。
  - 更新工程规范与协作指南（`AGENTS.md`），明确“做减法”、“逻辑单源”、“严禁过度工程”与“不向下兼容”的研发原则。

## [0.1.0rc1] - 2026-09-21

首个认真发版的 release candidate。此前 GitHub 上的 `v1.*` Release / tag 已全部撤下（那批构建基本不可用）。本号起重新计版本：runtime_v2 唯一内核、中央 `compute.db`、只验 token 的 API、POSIX-only 运行时。

### 变更
- **API 访问控制只验 token**：`Authorization: Bearer …` 与 `?token=` 等价，不限 HTTP 方法、不验 Host。远程打开启动打印的 `#token=` URL 即可。`CLOUDRA_API_TOKEN=off` 才走回环 Host/client 闸门（挡 DNS rebinding）；非回环绑定拒绝 off。
- live 交付 complete 口径钉死：默认机理草稿边只欠 `ts_opt` + `frequency`（一阶鞍点）；IRC/端点/方向不是结题必要，需要路径证明时才写进该步契约。带 stages 的边不以 `CoverageContract.required_edge_level=endpoint_supported` 为门槛。benchmark 自洽性与 `ts_guess strict` 的 IRC 方向证明不变。
- `dag_guided` 机理草稿对话：Coordinator 的 `rationale` 必须写清 Considered / Observed / Chose（综合过哪些情况、机理推断工具里实际看到什么、图上留下什么及未画通道的取舍）；Supervisor 允许单路径，只在取舍没讲清时退回，不因单路径 reject，也不替 Coordinator 补第二条通道。
- `dft-calculation` skill 重写（基于五路软件最佳实践调研）：TS 初猜三级梯队（ts_prepare → 映射插值/NEB → 一维/二维松弛扫描，扫描从兜底升为正当主力）、**QST2/QST3 硬禁止（上限 NEB）**、「投初猜优于调参」纪律、软模/松散离子-分子复合物不收敛预警与处置阶梯、构象采样强制（单构象能垒=交付阻断）、真空裸离子禁令与溶剂/反离子/标准态规则、伪鞍点识别（虚模位移必须落在反应重原子）、不合理建模黑名单与「该不该算」前置自审；新增 references `ts-search-playbook.md` 与 `modeling-sanity.md`；本地工具优先于 bash 的工作规则全面收紧。
- `flower.enabled` 默认开：mechanism_predict（FlowER 机理假设生成）对模型默认可见，未装环境时调用层 fail-loud 引导 `scripts/setup_flower.sh`；显式置 false 才回退 wire 隐藏 + 执行层硬失败。
- 工具面收敛：`role_allowlist` 工具级角色门槛（registry 声明使用者，wire 投影隐藏 + PermissionStage 硬拦两道防线；化学/QM 工具限 coordinator/small_mol/md/dft/experiment，ir/nmr_processor 为 experiment 专属）；裁撤冗余工具 `web_fetch`（能力由 `browser` 静态回退覆盖）与 `todo_read`（todo 提醒改为内联清单，`todo_write` 每次调用回显全量）；email 工具与收件监听器加总开关 `email.enabled`（默认关，config_gate 隐藏 + 执行层硬失败 + 监听器不启动）。
- 上线前可靠性大重构（beta 不留兼容）：计算执行面三进程拓扑定型——Web 控制面（api_v2）、计算调度守护进程（`cloudra scheduler`，flock 单实例，web 启动时自动 detach 拉起）、知识向量服务（chem-kb 插件安装后自动拉起，`CLOUDRA_KG_VEC=off` 关闭）；进程间状态同步只走 SQLite（WAL）与文件锁。执行面铁律固化：永不 kill 计算进程、存活判定只用 flock 探测、核心链路零输入文件解析（资源量由 agent 提交时显式申请）。
- runtime_v2 函数式内核化：CommandBus 四拍（纯 decider → append+publish+persist → 唯一无守卫 `apply_event` → effect 执行），恢复重放与在线路径共用同一应用器（`test_runtime_v2_replay_equivalence.py` 门禁常驻）；快照降级为节流缓存，按每项目高水位线增量重放（修复旧 seq 高水位在多项目交错下丢事件）；重启恢复时孤儿审批/提问显式落 `approval.expired`/`interaction.expired`；compact 请求走 `compaction.requested` 事件；状态外化契约（事件可推导 vs 刻意易失）固化进各模块 docstring。
- config 子系统重做：磁盘 YAML 是唯一事实源，唯一写入口 `mutate_config(fn)`（flock 排他 + 读磁盘 → 应用 → 原子写回 → 刷新单例），序列化由 `model_dump` 派生；`save()`/`reload_config()`/plugins 磁盘合并 hack 删除；新增 `add_plugin`/`remove_plugin` 与 `cloudra knowledge uninstall`/`status`。
- `compute_jobs` 迁中央 `data_dir/compute.db`（`ComputeDB` + `services/compute_store.py`），调度守护单库认领；会话库六张 legacy 死表（subagent_requests/approvals/scheduled_reminders/client_commands/interactions/hub_posts）及读写函数删除；进程内 IPC 事件总线删除，compute 完成通知改纯 DB 细粒度轮询（`ComputeNotifyBroker`），API 宕机窗口不再丢通知。
- 统一日志基建 `infra/logging_setup.py`：api_v2 落 `logs/api.log`，scheduler/kg_vec 经 stream 走各自重定向日志，logger 名全部归一化到 `cloudra.*` 树；`CLOUDRA_LOG_LEVEL` 控级别。
- 上帝文件拆分：`dag/controller.py`（1384 行）拆为门面 + supervision/evidence_inbox/stop_audit/drafts 四个 mixin（公开签名与 `_SUPERVISION_STATES` 类级共享语义不变）；`services/api_v2.py`（1105 行）拆为 `api_v2/` 包（app/context/models/sse + 九组 routers，`ApiContext` 显式注入、路由零闭包，create_v2_app 签名与路由表逐字节不变）。
- calculator 进程 nice +10 降权（`monitor.py` preexec_fn），保控制面调度份额；知识向量服务解释器可由 config `knowledge_vec_python` 指定（缺省探测仓库根 `.venv-trans`）；语义检索通道异常不再静默（warning + `last_health`），新增 `GET /api/v2/knowledge/health` 三通道健康聚合与前端 KnowledgePanel 健康状态条。
- 运行时环境定位 POSIX-only（flock/nice 依赖 fcntl 与 POSIX 语义），README 声明并撤下 Windows 安装指引。

### 修复
- 快照 `last_seqs` 改用 EventWriter 已落盘前缀，不再用 live `high_watermarks`（并发 append 后重启会跳过已入库事件）。
- `bind_stage_attachments` 与单条绑定共用 `ts_opt` 正常终止闸门，stale 后重算 stages，不再重放旧列表。
- 计算完成通知按已加载项目取数，未打开项目的积压不再占满 LIMIT。
- `.api_token` 新建即 0600，已存在但权限过宽就地修好；硬删除 artifact 路径收口在 `artifacts/` 下。
- 计算账本与磁盘/DAG 对齐：guard 终态先 CAS，cancel-all 已落 `cancelled` 则不写 `state_*.json`、不入 compute review；租约耗尽 reap 探 calc/guard flock，活作业不标 failed；`scheduler` 为 NULL 的旧行走本地取消桶。
- CommandBus 逐事件 persist-then-apply：落库失败丢弃未持久化尾巴，避免下次 flush 把从未 apply 的事件写进磁盘；包装路径已 apply 的事件失败不丢、留给下次重试。
- OpenRouter OAuth 回调 `postMessage` 钉同源 `window.location.origin`，接收端校验 `event.origin`。
- `CLOUDRA_API_TOKEN=off` 只允许回环绑定；`create_v2_app` / `cloudra web --host` 非回环直接拒启。
- runner 收尾 flush 持久化失败（`EventPersistenceError`）不再吞掉：任务失败可见，不把内存 SUCCEEDED 假装已经落库。
- 前端时间线：live 窗口裁掉的事件转入「Load earlier」页，不再静默丢失；`?runtime=` 只接受回环/同源，避免把 bearer 打到任意基址；SSE 白名单补上 `tool.requested` / program 生命周期等；`render-smiles` 走 bearer。
- 物种 `geometry` 绑定走 `validate_species_minimum`（须 0 虚频），与 `dag_submit_species_evidence` 同口径。
- 上下文压缩（GH #48，从 windows 分支回流）：thinking 模型摘要带 ` ```json ` 围栏或围栏后散文、`objective` 写成单元素数组/裸字符串、列表项写成裸字符串时，做无损形状提升后再校验（空 objective / 缺 text 仍 fail-loud）；拒替换 `error=''` 落到异常类型名；摘要超时下限 600s。前端 `/compact` 与 Compact 按钮按 agent 状态提示，并 toast `compaction.started`/`finished`（含拒因）。
- config 并发写丢键：旧 `save()` 用内存快照整文件重写 YAML，运行中服务会抹掉并发写入（如 `knowledge install` 的 plugins）；且 plugins 条目无法经 save 移除。改 `mutate_config` 后结构性消灭。
- 重启后 pending 投影孤儿（审批/提问）无声消失，agent 唤醒看不到终态；现显式落过期事件。
- 快照恢复在多项目交错写入下按全局 seq 高水位过滤会丢事件；改每项目 `last_seqs` + ORDER BY rowid 增量重放。
- 计算完成通知依赖进程内 IPC 总线，API 进程重启即丢；改纯 DB 轮询投递。

### 新增
- `conformer_search` 新增 `mode` 参数（CREST 后端）：`nci`（壁势下非共价复合物/氢键网络采样）、`qcg`（quantum cluster growth 显式溶剂壳生长，配 `solvent_smiles`+`nsolv`；只跑 grow——产物 `grow/cluster.xyz` + `qcg_energy.dat` 能量，ensemble 阶段刻意不纳入；依赖外部 xtb-IFF、缺失落专属终止类别 `qcg_xtbiff_missing` fail-loud；引擎被信号杀死落 `engine_crashed`；macOS arm64 上 gfnff 预优化路径实测崩溃、gfn2 grow 正常，安装与现状见 `deploy/xtbiff_macos_shim.md`）、`protonate`/`deprotonate`/`tautomerize`（质子化态/互变异构枚举，返回文案明示「含伪结构、逐条化学审查后才准用」且限单组分输入）；crest_runner 按 runtype 核对各自的产物文件名与产物原子数（CREST 2.12 实测口径），拓扑对比只对 default/nci 启用。
- 聊天记录分页回看：转录顶部新增「Load earlier」气泡，点击经 `eventsPage`（`before` 游标 + `tail`）向前翻一页 500 条更早事件，滚动位置保持不跳，可连续点击直到翻完；翻到头显示「beginning of history」结束标记。更早分页独立于实时 SSE 窗口存储，不被 `EVENTS_WINDOW` 裁剪。
- `cdxml_to_graph` 工具：基于 molli + RDKit 解析 ChemDraw CDXML 反应路线，生成节点为 isomeric SMILES 的候选机理图；多反应物/产物合并为反应物/产物络合物，支持 DAG 检测与 `dag_propose_mechanism` 提案生成，边信息携带溶剂/条件/试剂供计算参考，可选落盘 mol2。
- runtime_v2 原生提醒唤醒：`reminders.py` 拦截 `schedule` 工具，提醒落 `reminder.scheduled` / `reminder.cancelled` / `reminder.fired`（`schedule_id` 为事件 seq）；到点经 `agent.message` 投递 `[Reminder]` 并自动 reopen 终态 agent。进程启动 `rearm_all()` 从事件投影重建，过期立即触发——修复 v2 下 `schedule` 无人触发、挂起 agent 永睡的停摆。
- `NoticeManager`（`notices.py`）：统一上下文注入。`pin`/`unpin` 按键幂等的常驻注入（goal 钉、DAG 投影），`push` 一次性注入（交付 delta、唤醒附言）；`turn_pipeline` 拼消息时 `collect`（pins 在前，push 耗尽）。
- DAG 工具族：删除未发布的 `dag_graph` 单工具，拆成平铺字段的 `dag_*` verb（`dag_view` / `dag_init_from_template` / `dag_add_species` / `dag_add_step` / `dag_update_delivery_element` / `dag_schedule_work` / `dag_update_process_node` / `dag_remove_edge` / `dag_bind_evidence` / `dag_review_evidence` / `dag_set_coverage_contract` / `dag_message_supervisor` / `dag_delivery_report`）。引擎、分权、变更日志与原子批次不变；督导循环按工具名调度，不再嗅探 `action`。
- 交付即时反馈：`DagController.on_tool_finished` 返回 `DeliveryDelta`；`dag_stage` 把 `[DAG] evidence bound: …` 追加进当轮 tool result，并 `notices.push` 保证跨 run 可见。
- runtime_v2 为唯一运行时：Electron 前端流式输出（LLM token delta 经 `llm.chunk` 直发 SSE，不落事件日志）、thinking 分段折叠（绿标）与工具行（黄标）、Markdown + KaTeX 渲染。
- 前端 DAG 面板：双图真图渲染（dagre+SVG）、节点选中查看/编辑字段（不暴露 JSON）、覆盖率报告、mutation 历史、supervisor replan。
- 前端命令继承：`/goal`（目标锚点）、`/compact`（上下文压缩）、context 统计、skills 列表；审批与 ask_user 交互面板。
- 子 agent 派发 v2 原生化：`subagent_bridge.py`（SubAgentLauncher/SubAgentSwarm/get_subagent_report 经 CommandBus spawn，支持 is_wait 与父取消级联）；`hub_bridge.py`（agent_hub 论坛落 `hub.posted` 事件，通知/呼叫走 Mailbox）；审批/交互由 `pending.py` 内核 broker 承担（事件 + future，决策经 `approval.decide`/`interaction.respond` 命令）。
- 失败自动恢复：turn 崩溃原地重试（保留 history，`run.retry` 事件，默认 5 次退避，2s→30s 递增）；对 failed/cancelled 的 agent 发消息自动 reopen 新 run，前端不再暴露手动 Restart。
- 交付门禁移植到 v2：dag 模式下 `stop(delivery_disposition="complete")` 需通过交付覆盖率审计（`dag_stage` 拦截，复用 `DagController.audit_stop`），有未终态兄弟 agent 时 stop 视为挂起不审计。
- DAG 视图消歧：observed 节点新增 `arguments_summary`（路径参数优先），process 视图（`include_observed=true`）暴露 `tool_call_id`/`arguments_hash`/`arguments_summary`，Coordinator 可在多个同工具 observed 节点间辨认后走 `observed_<hex>` 别名 `bind_evidence`；dag_record/guided 投影提示同步更新。
- 多候选认领在执行者一侧消解：同工具多个计划候选时，`assignee` 恰为当前 agent 的唯一节点被直接认领（不再一律落 observed 留给 Coordinator）；顺带修复 v2 的 role_id 与 DAG 图 legacy assignee 词表（a-0..a-8）的映射缺口——此前子 agent 的 assigned_to_me 投影在 v2 下恒为空。
- Supervisor 活动前端可见：dag_guided 下每次督导触发经 `DagController.on_supervision` 钩子投影成一个复用的壳 agent 会话（角色 `supervisor`，挂在触发者名下，不走 LLM 管线），运行时 AgentBar 显示 running，结束落摘要消息——督导期间界面不再像卡死。
- 工作区按项目隔离，项目栏按工作区划分。
- 子 Agent 按领域重命名：explorer（探索+审查）、writer（论文写作）、researcher（文献）、small_mol（小分子量化）、md（分子动力学）、dft（第一性原理）、experiment（实验设计）、env（环境管理），替换掉 visionary/operator/coder。explorer 只读，writer 读写，其余全权限，危险操作统一走审批。
- 计算类 prompt 方法论：教 SOP 和翻车直觉而不是知识清单，起手先 `getskill` 加载对应 skill。
- AgentHub：加 `hub_posts` 表（schema v6）和 `agent_hub` 工具（post/browse/read/search，支持问答串），并行子 Agent 可共享 SQLite 发帖，只读 Agent 也能发。
- 通用网页搜索：加 `web_search` 工具，Tavily/Brave（需 key）→ Bing/DuckDuckGo（免 key）自动 fallback，和 `web_fetcher` 两段式用。
- 规划工具：加 `todo_write`（多步清单，同一时刻只能有一个 in_progress）和 `goal_set`（目标锚点，压缩后仍钉在上下文里）。
- Textual 全屏 TUI：`cloudra/tui/` 重写成全屏应用，支持对话消息渲染、会话切换、主/子 Agent 上下文分屏、绿/黄主题。
- harness 加固：`context_window`/`timeout` 进配置（不再硬编码）；工具参数校验失败会反馈给 LLM；传输层加超时和状态事件；`bashtools` 返回 `exit_code` 且截断超长首尾输出；主循环死循环检测；上下文压缩概要持久化。
- 模型原生联网搜索：`LLMConfig.native_search`（默认 `auto`）+ `native_search_params`。按 base_url/model 自动识别适配器（openai 搜索模型 / openrouter `web` 插件 / deepseek / gemini / custom），启用后在请求里注入服务商侧搜索工具、剔除外部 `web_search` 函数工具，避免双重搜索；结果以内联引用返回。状态栏显示「联网·<provider>」，聊天区把 `web_search_call` 事件并入「思考过程」。
- DeepSeek 原生搜索走 Responses API：新增 `LLMClient.create_responses`（POST `/responses`），把 chat.completions 风格的 kwargs/响应翻译成 Responses 形状（含流式 SSE 与 tool_call 增量合并），reAct 层零改动；base_url 尾部 `/v1` 自动兼容。
- 联网搜索引导：有搜索能力（原生或 `web_search` 工具）时，在 system prompt 注入「联网搜索（重要）」段落，要求任务依赖实时/外部信息时先搜再答。
- `todo_read` 工具：与 `todo_write`/`goal_set` 配对，随时读取当前任务清单与目标锚点；每 10 轮或 supervisor 反对时注入提醒，让 todo 真正驱动每轮行为。
- 目标严格模式与 `/goal` 命令：TUI 新增 `/goal <目标>`（设置目标锚点并固定到 Coordinator 上下文）、`/goal pause`（暂停当前任务）、`/goal`（查看）。设置目标后任务只有调用 `stop` 才能结束，无工具轮会注入「确认 goal 是否完成」提醒；未设目标时保持传统语义（有正文即完成）。
- 移除 `MAX_STEPS` 步数上限：循环结束由 `stop`/取消/死循环检测决定，不再有硬性步数天花板。
- `submit_compute_job` 支持 CP2K：新增 `cp2k` job_type（`calculator.sh` 分支、PATH 检查、`.out` 日志路径），guard 用轻量文本解析 CP2K 输出（cclib 已移除 CP2K 解析器）；顺带修复 guard 未透传 job_type 导致非 Gaussian 日志路径错配的问题。
- OpenAlex API key：配置项 `openalex_api_key`（`cloudra config set` / `config.yaml` / `CLOUDRA_OPENALEX_API_KEY` / `OPENALEX_API_KEY`）；`openalex_searcher` 有 key 则带上，没有则匿名降级。礼貌池邮箱 `openalex_mailto`（`CLOUDRA_OPENALEX_MAILTO` / `OPENALEX_MAILTO`）写入 User-Agent；未设置则只用通用 UA。

### 变更
- `chemrxiv_searcher` 改名叫 `openalex_searcher`，它其实一直检索整个 OpenAlex，没过滤过 ChemRxiv；Android 工具白名单和文档同步更新。
- 所有工具描述统一成“功能/适用/不适用/关键纪律”结构，把搜索、PDF、文件修改、计算流水线之间的分工边界写清楚。
- CLI 横幅版本号从 `cloudra.__version__` 读取，和 `pyproject.toml` 一致（本版 `0.1.0rc1`）。
- 死循环检测与步数预算：移除步数预算相关逻辑，保留 `AgentStuckLoop`（相同工具+参数连续调用）作为防空转兜底。
- 联网搜索展示：`web_search_call` 状态事件改为流中段逐条上报，并入「思考过程」面板而非孤立系统框。

### 修复
- `ts_guess` IDPP 插值在原子数 >3 时崩溃：`err (npair,) * diff (npair,3)` 的 numpy 广播只在 npair=3（现有单测）碰巧成立；C6H10 一类体系 npair=120 报 `shapes (120,) (120,3)`。梯度改成先扩成 `(npair,1)` 再乘位移。
- v2 删除 v1 worker/`compute_executor` 后异步 `submit_compute_job` 只把行写成 `ready`，无人 `claim_ready_compute_job`，计算任务永远领不走。已恢复 `runtime/compute_executor.py`：`ComputeBroker` 由 FastAPI lifespan 启动，扫描会话库领取任务并拉起 guard / Slurm。
- 子 agent 跑 `dag_record` 时证据落地不唤醒 Supervisor：`dag_stage` 对 `SubAgentLauncher`/`SubAgentSwarm` 快照 delivery revision + 已绑证据计数，差分有变化即父侧 `new_evidence`。
- `dag_init_from_template` 播种骨架后立即 `graph_initialization` 唤醒督导排产，不再等 Coordinator 留言。
- 前端 Agent 列表按 id 去重，避免 YOLO 级联 PATCH 同一 coordinator 多次抬高 `settings_revision`。
- v2 丢失模型原生联网搜索：`LegacyLLMProvider` 从不解析 native_search 适配器——外置 `web_search` 工具不剔除（模型绕开原生搜索走第三方）、provider 侧搜索参数不注入、DeepSeek 的 /responses 传输不启用；`LegacyPromptProvider` 还把 `web_search_available` 硬编码 False（「联网搜索」prompt 段消失）。已对齐 v1 行为：命中适配器时剥 `web_search` 函数工具、注入原生参数、`transport=="responses"` 走 `create_responses_with_retry`；`legacy_default_settings` 桥接 legacy 配置的 `native_search`/`native_search_params`。
- `DagController.maybe_supervise` 的 `on_supervision` 投影回调改为 best-effort：投影故障（如壳会话 spawn 被拒）只记 warning，督导照常运行、父 turn 不受连累（此前投影异常会在 supervisor.run 之前杀死整个 Coordinator turn，是 process 图从不推进的直接原因）。
- 子 agent 不继承 yolo：YOLO 是 per-agent 设置（spawn 时快照 = 项目 defaults → 角色 defaults → spawn patch），而 `_spawn_child` 只透传 `orchestration_mode`，父开了 yolo 子 agent 仍逐项弹审批。现在 yolo 提为项目级开关：AgentBar 顶栏的 YOLO 勾选写入项目 defaults（新 agent 自动继承）并级联 PATCH 现存 agent（`patch_settings` 原地生效）；spawn 时子 agent 另继承父值（subagent_bridge 与 hub_bridge call 共用 `_spawn_child`）；Inspector 里的 per-agent 勾选保留为单 agent 覆盖。
- `test_stream_marks_replay_boundary` 把全套回归卡死：httpx ASGITransport 缓冲整个响应体，无限 SSE 流经它永远等不到 `project.synced`（`send` 要等 app 跑完才返回，而 app 永不结束）。回放+边界标记逻辑抽成模块级 `_sse_replay` 生成器（端点行为不变），测试直接驱动生成器断言。
- `message_supervisor` 后整个 run 崩掉（`'dict' object has no attribute 'state'`，重试 2 次后 failed，工具气泡显示 interrupted）：旧快照里没有后加的 `supervisor` 内置角色，恢复时角色注册表被快照整个替换，shell spawn 被拒；`_SupervisionShell` 未检查 spawn 是否被拒，把 `{"error": ...}` dict 当 AgentSession 用。恢复改为快照角色合并覆盖到内置角色表上（补丁继续生效、新内置角色不丢）；shell 在 spawn 被拒时降级为无 UI 投影（督导本体照常运行）。
- compute 失败可观测性：guard（runtime/monitor.py）失败路径统一把可读原因落 `compute_jobs.last_error` 与 state json 的 `error` 字段——环境检查/命令构建失败直接落信息；日志解析失败带 calculator 退出码 + 日志尾部；计算失败从日志尾部提取终止标记段（Gaussian `Error termination`、CP2K `ABORT` 等，含上下文行，保序去重）；失败事件内联 `Failure reason:`。`query_compute_job` 的 last_error 不再返回空字符串。
- DAG 投影：failed 的 observed_tool_call 遥测节点不再混入 blockers 视图（它们是不可执行的历史记录，污染真正的排产阻塞项）。
- text_writer 等破坏性工具在 YOLO 模式下报 `'_LegacyAgentBridge' object has no attribute 'context_manager'`：YOLO 守卫改为对无 context_manager 的 v2 壳 bridge 容错（降级为空上下文）。
- 历史轮次的 thinking 被吞：reasoning 原本只经瞬时 `llm.chunk` 流式展示，不落库，刷新/重进后全部消失。现在每轮 LLM 调用落一条持久 `agent.thinking` 事件，前端折叠渲染（绿色标识），SSE 收到持久段时替换对应的流式段避免重复。
- 中间轮次的正文被吞：带工具调用的轮次，模型 narration 只活在流式气泡里，turn 结束即消失。现在 continue 轮的正文落持久 `agent.message_emitted`（stop 轮正文由 runner 最终消息承载，不重复落）。
- stop 轮的最终消息曾是 stop 工具输出 schema 的 JSON dump（模型的最终陈述被吞）：现在用户可见消息 = 模型正文，模型没写正文时回退 stop 输出的 message（保留 reason/[ANSWER] 语义）。
- 前端 SSE 漏注册 `agent.thinking`/`run.retry`/`hub.posted`/`compaction.requested` 事件类型（EventSource 按类型监听，未注册即静默丢弃）：持久 thinking 段实时不送达、去重逻辑不触发，已补齐并与后端 EVENT_TYPES 对齐。
- 重进会话时历史提示重复弹出：SSE 每次连接从 cursor 0 全量回放，审批/LLM 失败等 toast 对回放事件重复触发。现在回放末尾发 `project.synced` 边界标记，回放期只重建状态不弹提示。
- workspace_dir 相对路径静默嵌套：客户端传入剥掉前导 `/` 的路径时，下游会把它和 server 进程 cwd 拼成 `cwd/home/...` 的嵌套怪路径，所有文件/bash 工具全崩。现在 `project.create`/`project.update` 在命令层规范化：非绝对路径直接拒绝（清晰报错），`~` 展开，不存在的目录自动创建。
- 长会话历史事件被窗口截断：events 端点原本只返回最后 500 条且 `query_session` 取尾部，早期 message/thinking 事件掉出窗口（表现为"中间轮 content 被吞"）。端点改为从头分页（`tail=False`），前端翻页拉全量。
- DAG stage 在事件循环线程上同步建 SQLite（护栏告警）：`_controller` 改 async，`init()` 走 `asyncio.to_thread`。
- 非瞬态 LLM 错误（401/402/400 等 4xx）不再触发 runner 原地重试，直接 failed 落错；5xx/429/连接错误保持退避重试。
- 前端时间线：工具行配对（tool.finished）后从 openTools 删除，修复 cancel/run 结束时把历史已完成工具全部误标 interrupted 的问题。
- v2 恢复语义：进程重启后恢复出的 running/waiting agent 没有存活 runner（run 只在内存），restore 时统一落 failed 并记 `run.finished`（"interrupted by process restart"），界面不再僵尸转圈；发消息即可自动重开。
- YOLO 审批时模型没返回 `submit_approval_decision` tool_call 或参数解析失败，不再把“未返回 tool_call”这种内部实现错误当拒绝理由甩给主 Agent，而是在 Guard 内部告警、纠偏并重试（最多 3 次）；耗尽后按默认安全策略拒绝，返回给主 Agent 的是不含实现细节的中性原因。
- TUI 代码块「复制」按钮失效：`on_click` 命中检测未减去边框/内边距 gutter，4×1 热区永远点不中；修复并加回归测试。
- 审批/提问弹窗 `MarkupError` 崩溃：动态内容（工具参数、命令输出）按 console markup 解析遇 `[` 抛错打崩整个 TUI；改为 `SafeStatic`（markup 解析失败自动降级纯文本）+ `markup=False`。
- DeepSeek Responses 流式翻译缺 key：chunk 的 `delta`/`message` 未常驻 `content`/`tool_calls`，reAct 直接属性访问抛 `AttributeError('tool_calls')`；统一补齐占位 key，`ResponseDictWrapper.model_dump` 尊重 `exclude_none`。
- DeepSeek Chat Completions 注入 `web_search` 工具被 400 拒绝（`tools[..].type: unknown variant`）：原生搜索一律走 `/responses`，chat 路径不再注入。

### 移除
- v1 运行时整体删除：旧 FastAPI 面（`services/api.py`/`api_v1.py`）、`services/service.py` 应用服务层、legacy 执行核心（`runtime/runner|executor|workers|compute_executor|mobile_tasks`、`core/react.py`）、Flet GUI（`ui/`、`flet_app.py`）、Android 全家桶（`android/`、`extensions/cloudra_native/`、`device/`、`device_broker`、mobile/remote 相关 infra 与文档）、legacy 论坛存储（hub_posts）、`control_store`/`interactions`/`conversation_repo`/`case_bank`/`context_stats` 及对应测试。Managetool 四个跨 agent 工具只保留 schema（执行由 runtime_v2 桥接拦截）。
- CLI 收敛为启动器与运维命令（`web`/`config`/`logs`/`skills`/`backup`）；`run`/`gui`/`sessions`/`history`/`devices`/`android` 子命令移除。

## [2.0.0-beta] - 2026-07-26 ~ 2026-09-20

### 新增与核心重构
- **事件驱动架构全面重构 (Event-Driven Rewrite)**：
  - 废弃历史基于 ReAct 状态循环与阻塞式串行执行的旧内核，实现纯事件溯源驱动的 `runtime_v2`。
  - 引入 `CommandBus` 四阶段管线（决定 decider → 先持久化后生效 append+persist → 唯一无守卫状态更新 `apply_event` → 副作用 effect 执行）。
  - 支持会话无损增量重放与从事件日志确定性恢复。
- **DAG 反应机理图编排子系统 (DAG-Guided Orchestration)**：
  - 首次将化学反应机理探索形式化为有向无环图，以科学证据交付（Delivery-only）为核心契约。
  - 规范基态物种（极小值）与过渡态（一阶鞍点）的数据模型，支持阶段式证据绑定（`ts_guess`、`ts_opt`、`frequency`、`short_irc`、`thermochemistry`）。
  - 引入独立只读科学督导员（Supervisor），基于持久化信箱机制进行图结构检查与证据审核。
  - 建立严格的退出门禁（StopGate），在结题时对交付覆盖率与虚频合法性进行全自动审计。
- **科学子 Agent 团队矩阵与 AgentHub 协作网络**：
  - 确立统一的角色画像架构（`RoleProfile`），将 Agent 职责拆分为 8 个专业领域角色：`coordinator`（统筹）、`explorer`（探索审查）、`writer`（论文写作）、`researcher`（文献检索）、`small_mol`（小分子量化）、`md`（分子动力学）、`dft`（第一性原理材料）、`experiment`（实验设计）。
  - 新增 AgentHub 共享论坛与 Mailbox 消息信箱，支持多智能体异步协作发帖、检索与互唤醒。
  - 引入 `SubAgentSwarm` 批量并行派发与取消级联机制。
- **交互界面体系迭代**：
  - **Textual 全屏 TUI**：重写终端全屏界面，支持虚拟滚动（virtual transcript renderer）、KaTeX 数学公式渲染、流式 Markdown 折叠以及绿黄工业风格主题。
  - **React Web 控制台**：基于 Vite + React 构建现代化 Web 前端，集成 DAG 交互图谱可视化（dagre+SVG）、分子 SMILES 与 3D 构型渲染、会话与日志实时观察面板。
- **化学与量化计算工具集扩充**：
  - 新增 `cdxml_to_graph` 工具，基于 molli 与 RDKit 解析 ChemDraw CDXML 反应路线并自动生成反应机理图骨架。
  - 集成 CREST 构象搜索（NCI 弱相互作用、QCG 溶剂壳生长、互变异构体枚举）。
  - 集成 xTB 反应路径扫描（`xtb_path_runner`）与多维松弛扫描。
  - 集成 FlowER 机器学习反应机理预测（`mechanism_predict`）。
- **知识库 Chem-KB 体系构建**：
  - 导入包含 1.5 万化学实体与 1 万反应关系的知识图谱，构建混合检索通道与前端知识探索面板。
- **Benchmark 评测体系原型**：
  - 确立 3 层法医级评测架构原型（图同构 GED 覆盖率、物理自洽性、能垒准确度），构建包含 Easy / Normal / Hard / Impossible 的阶梯式候选题库。

## [1.8.0] - 2026-07-18

### 新增
- `first-principles-calculation` skill 加 `references/`（`ase-guide.md`、`ase-quick-reference.md` 和 3 个可运行示例脚本），内容来自 [jkitchin/skillz](https://github.com/jkitchin/skillz)（MIT，已保留版权声明）。写 ASE 脚本前可用 `getskill` 的 `other` 参数按需加载。
- LLM 调用全链路迁到 `AsyncOpenAI`（agent / yolo_guard / supervisor / context_manager / memory），解决同步调用冻结事件循环的问题。
- Token 级流式输出：`reAct` 把 LLM 增量以流式写入 `llm_chunk` 事件，前端 SSE 实时渲染；子 Agent（Follower）默认开启流式。
- 任务打断：API/前端可请求打断 Session，先置 `cancel_requested` 由 Agent 自行退出，超时后 SIGTERM 兜底，支持级联取消子 Agent 和计算任务。
- 对话式运行视图：前端运行区改成按 Session 分面板的 transcript，区分思考/内容/工具气泡，Coordinator 和子 Agent 各自署名；终态后在对话末尾只展示一个“最终结果”总结。
- 前端补齐 CLI 全部功能：YOLO 按 Session 勾选、设置弹窗（`GET/POST /api/config`）、日志查看器（`/logs`）、跨会话 Sessions 监控（`/api/sessions` 聚合）、Skills 列表。
- 配置 API：`GET /api/config`（脱敏）和 `POST /api/config/set`（带类型 coercion），与 `cloudra config set` 共用实现。

### 变更
- 移除 Tauri 桌面端和预构建的 `frontend/dist/` 目录；当前控制界面以 Textual TUI 为准，`cloudra gui` 仅作为实验性入口保留，暂不推荐生产使用。

### 修复
- 数据库锁冲突：遥测写入改成异步可丢弃；LLM 调用对 429/5xx 加指数退避重试。
- `reAct stop` 结果：`session.result` 现在取最后一条 assistant 正文，不再保存 stop 工具的原始 JSON 返回。
- pip 包缺数据文件：`pyproject.toml` 补 `package-data`（prompts / skills / `calculator.sh`），修复 wheel 安装后 `_load_prompt` 报错。

## [1.7.1] - 2026-07-12

### 新增
- 会话清空：左侧栏加“清空会话”按钮，二次确认后删除所有 Conversation / Session / 消息 / 审批记录。

### 改进
- 后端 API：新增 `DELETE /api/conversations` 和 `CloudraService.delete_all_conversations()`；CORS 支持 DELETE。
- 后端数据模型：调整 `session` 表结构以支持新的 Session 生命周期和事件记录。

## [1.7.0] - 2026-07-09

### 新增
- 自我学习与记忆：Agent 可以从过去的对话和成功案例里学习和反思。
- 科研监督员：新增独立 Agent，监督实验进度、确保科研严谨性并验证结果。
- 全局案例库：案例存储结构从原来的局部 DB 升级到全局 Case Bank，支持跨对话检索和经验复用。

### 改进
- PDF 解析：用 PyMuPDF 重构 PDF 提取逻辑，改到后台线程异步执行。
- YOLO Guard 网络：请求头被 OpenAI 或中转站拦截时，自动切换 User-Agent 做 fallback 请求。
- Function Calling 健壮性：根据参数反推工具名的兜底机制，兼容部分中转站返回空工具名的情况。

## [1.6.3] - 2026-07-07

### 新增
- `research-paper-writing` skill：指导 AI 写学术论文、Markdown/LaTeX 排版、期刊模板格式化。覆盖 storytelling、introduction、abstract、method、experiments、conclusion、related-work 等章节；包含 IEEE/Nature/Elsevier/ACM/APA 的 LaTeX 模板；包含 Pandoc/LaTeX 编译和文献管理工具用法。

### 改进
- 更新 writer prompt，要求写论文时调用 `research-paper-writing` skill，约束行文风格，禁用夸大其词。

## [1.6.2] - 2026-07-04

### 新增
- Coordinator 异步计算等待与事件唤醒：异步提交计算任务后，Coordinator 不再立即退出，而是保持存活并轮询后台任务；当 `guard` 注入计算完成事件后，Coordinator 被唤醒继续处理结果。
  - `_wait_for_subtasks` 扩展为 `_wait_for_background_tasks`，同时等子 Agent 任务和计算任务。
  - `run_task_async` 加事件唤醒循环。
  - 新增 `tests/test_run_task_async.py` 测试。

## [1.6.1] - 2026-07-04

### 新增
- `--yolo` CLI 选项：危险操作不再等用户审批，由独立 LLM Agent 自动判断是否合理。
  - 新增 `cloudra/yolo_guard.py` 安全判断模块。
  - 新增 `prompts/yolo_guard.md` 审计员 prompt。
  - 新增 `tests/test_yolo_guard.py` 测试。
- 上下文压缩：上下文超过模型窗口一半时，自动对最近 10 轮 assistant 之前的历史消息调 LLM 生成概要，避免无限增长。
  - 新增 `cloudra/token_estimator.py` 轻量 token 估算器。
  - 新增 `tests/test_context_manager.py` 测试。
- 多模态渲染优化：图片 base64 编码、视觉降级、视觉历史窗口（最近 10 轮）全部下沉到 `ContextManager.build_messages()`，简化 `Agent.llm_call()`。
- 模型视觉能力配置：`LLMConfig` 加 `supports_vision` 字段，可在 `config.yaml` 里分别为 Coordinator/Follower 配置。

### 改进
- `Agent.llm_call()` 大幅简化，移除重复的消息构建和异常驱动降级逻辑。
- `ContextManager` 成为上下文的唯一渲染来源，职责更清晰。
- 区分 `max_tokens`（生成限制）与 `context_window`（上下文窗口），避免大上下文模型配置冲突。
- 统一依赖源到 `pyproject.toml`，删除独立的 `requirements.txt`，补齐 `fastapi`/`uvicorn`。
- `cloudra.__version__` 作为唯一版本来源，`cli.py` 和 `api.py` 同步读取。

### 移除
- 删除废弃的临时脚本 `draw_caffeine.py`。

## [1.6.0] - 2026-06-18

### 新增
- 异步计算任务基础设施：引入 `submit_compute_job` 异步执行与后台守卫，支持长周期量子化学作业在后台排队运行。
- `ContextManager` 统一上下文管理：重构会话历史构建，实现消息组装与视图渲染的单点维护。
- 数据库异步化改造：底层 SQLite 驱动由同步 `sqlite3` 全面迁移至 `aiosqlite`，消除事件循环阻塞风险。
- 异步任务假失败检测与异常隔离机制。

## [1.5.1] - 2026-06-30

### 改进
- 系统提示词重构：精简各 Agent 提示词结构，规范工具使用边界与科学严谨度。
- 限制 Coordinator 工具暴露范围，引导其将具体计算工作委派给专业子 Agent。
- 优化用户交互反馈：改进流式输出呈现，修复空消息与重复数值问题。
- 更新 DFT 第一性原理计算 skill 与环境配置。
- 修复子 Agent 在 reAct 停止后未清理上下文导致模板污染的问题。

## [1.5.0] - 2026-06-25

### 新增
- 邮件远程监听器功能升级：支持任务邮件全文正文解析与自动化分发。

### 修复
- 子 Agent 上下文隔离：按任务独立分配子 Agent 上下文，彻底杜绝提示词模板污染。

## [1.2.1] - 2026-06-18

### 新增
- 新增系统自动化演示脚本（automated demo script）。

### 修复
- 修复工具权限验证漏洞与部分边缘场景下的调用崩溃。

## [1.2.0] - 2026-06-01

### 新增
- **波谱分析套件**：引入 `IRProcessor` 红外光谱分析模块与 NMR 核磁共振数据解析能力。
- **多模态化学工具**：新增 `image_to_smiles`（化学结构图像转 SMILES）、`smiles_to_mol` 与 `ask_user` 人机交互工具。
- **专业化子 Agent 矩阵**：初步引入领域子智能体（Visionary、Operator、Coder 等）。
- **上下文懒加载**：实现会话上下文懒加载机制，显著降低长会话内存与 Token 开销。
- **本地 API 服务**：新增基于 FastAPI 的本地控制面 API 服务。
- **远程邮件唤醒**：实现基于邮件监听的远程任务唤醒机制。

### 修复
- 数据库并发与乐观锁优化：解决多任务并发写入 SQLite 时的冲突与锁死问题。
- 修复 Windows 平台下 Bashtools 路径与执行兼容性问题。

## [1.0.0] - 2026-05-20

### 新增
- CLI 工具全面重构：规范化 Python 包结构与安装分发机制。
- 撰写多语言文档：全面更新 README，支持中英双语详细使用说明与 CLI 手册。
- 建立测试基建：引入基于 pytest 的单元测试套件，包含 IRProcessor 等核心组件回归测试。

## [0.1.0-alpha] - 2026-05-12

### 新增
- 仓库初始化（Initial commit: Cloudra - an AI agent for chemists）。
- 搭建基础 ReAct 智能体循环与大模型调用适配层。
- 实现初步分子结构绘制（molecule drawer）、化学图像解析（image reader）与多模态上下文接入。
