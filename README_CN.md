# Cloudra

**面向有机小分子机理计算的自主 Agent 系统**  
*几何与电子结构工具 · 证据驱动的机理交付 · 事件驱动 Agent 协作*

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[English](README.md) · [文档中心](docs/README.md) · [核心创新点](docs/novelty.md) · [DAG 编排规范](docs/DAG_ORCHESTRATION.md) · [过渡态 SOP](docs/TS_PROCESS_SOP.md) · [插件系统](docs/PLUGINS.md)

> Cloudra 用结构化化学工具、可恢复的 Agent 运行过程和带证据的机理图支持计算化学研究。计算是否结束、科学证据是否成立、Benchmark 得分多少分别记录；机理结论仍需要结合化学判断与人工审查。

---

## 快速上手

### 1. 环境准备与安装

系统需要 Python ≥ 3.11、Node.js ≥ 22（默认 `javascript` 协议所用的 JS 宿主与前端测试脚本都要求 ≥ 22）、POSIX 环境（Linux/macOS——执行面依赖 `flock`/`nice` 语义），以及可访问的 OpenAI 兼容大模型 API。

```bash
# 克隆仓库
git clone https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent

# 一键安装环境（自动配置 Python 虚拟环境与依赖）
./install.sh

# 初始化配置文件
cloudra config init
```

### 2. 启动 Web 全栈工作台

Cloudra 提供单端口集成的现代 Web 控制台（FastAPI 控制面 + React/Vite SPA 前端）：

```bash
cloudra                      # 自动构建前端并拉起 Web 服务，同时打开浏览器
cloudra web --skip-build     # 复用已构建的前端资源快速启动
cloudra web --host 0.0.0.0   # 自定义绑定地址/端口（局域网 / 远程打开页面）
```

> 访问控制只验 token：`Authorization: Bearer …` 与 `?token=` 等价，不限方法、不验 Host。
> 本机浏览器打开启动时打印的 `#token=` URL 即可。默认只绑 `127.0.0.1:8000`。
> 非回环绑定不要再用 `CLOUDRA_API_TOKEN=off`。

### 3. 极客风快捷指令（Slash Commands）

在主聊天框中键入 `/`，系统会自动弹出无冗余的快捷补全浮层，支持键盘上下切换与 Tab 快速补全：

- `/schedule [on|off]`：切换自主调度模式。开启后，没有有效自唤醒提醒的停止请求会被拦截，便于在长计算期间挂起并恢复研究。
- `/goal <任务目标描述>`：为当前会话锚定核心研究目标。该目标经过多轮上下文压缩依然常驻。
- `/yolo [on|off]`：切换自动审批（YOLO模式），由自动审批策略评估需要授权的操作。
- `/compact`：手动触发上下文结构化压缩，生成带文件交接指针的摘要并归档历史。
- `/help`：快速呼出指令指南。

### 4. 联网搜索配置

`search` 工具默认使用 DeepSeek Search；`browser` 读取网页时默认使用 DeepSeek Fetch 并返回Markdown。截图和明确等待网页状态仍走浏览器。Search与Fetch共用一个独立于模型配置的API Key，可在全局设置中填写，也可通过命令行配置：

```bash
cloudra config set search_provider deepseek
cloudra config set deepseek_api_key YOUR_DEEPSEEK_API_KEY
```

也支持环境变量 `CLOUDRA_SEARCH_PROVIDER` 和 `CLOUDRA_DEEPSEEK_API_KEY`。可选供应商为 `deepseek`（默认）、`auto`、`tavily`、`brave`、`bing`、`duckduckgo`。明确选择供应商时，缺凭据或请求失败会直接报错；`auto` 按 DeepSeek、Tavily、Brave、Bing、DuckDuckGo 顺序尝试。非DeepSeek供应商沿用浏览器读取网页的路径。

模型服务商的原生搜索另行控制。DeepSeek的 `native_search=auto` 保留独立搜索工具；要启用其原生搜索，显式设置：

```bash
cloudra config set coordinator.native_search deepseek
```

其他模型供应商保留各自原生搜索行为；某个模型配置为 `native_search=off` 时使用独立搜索工具。

### 5. ChatGPT / Codex OAuth 登录

在“全局设置”中选择 **OpenAI Codex (ChatGPT 账号)**，点击登录按钮，打开授权页面并输入显示的一次性设备码。授权完成后，保存 Coordinator 或 Follower 的模型配置即可使用；两个角色共用 Cloudra 的账号登录。

也可以通过命令行完成：

```bash
cloudra auth codex login
cloudra config set coordinator.provider openai-codex
cloudra config set coordinator.model gpt-6-sol
cloudra config set follower.provider openai-codex
cloudra config set follower.model gpt-6-sol
cloudra auth codex status
# 退出 Cloudra 保存的账号登录：
cloudra auth codex logout
```

供应商别名支持 `codex`、`openai_codex`。可用模型以 ChatGPT 账号权限为准。设备码登录可能需要在 ChatGPT 账号或工作区安全设置中开启，参见 [OpenAI 认证说明](https://developers.openai.com/codex/auth/)。

Cloudra 在配置的数据目录下独立保存 `.codex_oauth.json`，文件仅允许当前用户读写。临近过期时自动刷新 access token，并在跨进程锁内保存轮换后的 refresh token；查询登录状态不会刷新。登录凭据不会返回给前端，也不会写入模型配置的 API Key 字段。

Codex 请求使用专用的 `https://chatgpt.com/backend-api/codex/responses` 端点，并设置 `store=false`。Agent、上下文压缩和辅助模型调用共用该传输；端点要求流式响应，Cloudra 会为 `stream=false` 的调用方汇总完整结果。通用的 `temperature`、`top_p` 与输出 token 上限不会发送到此端点。

---

## 当前题库与参考证据

正式题库共 **50题：简单20、普通10、困难10、Impossible（IMP）10**。当前JSON位于 `ideapool/tasks/{easy,normal,hard,impossible}/`，与对应生成源一起维护。

- [运行当前50题](cloudra/benchmark/README.md)：网页Benchmark面板选四档，或在命令行同时传入四个题库目录并指定 `--backend runtime_v2`。默认命令行只对简单档空运行，不能当作真实50题评测。
- [Google Drive完整证据包](https://drive.google.com/file/d/15YDa_ycWoLUANPsDdQ1rUOiNp_-wqOs5/view?usp=drivesdk) · [版本与校验值](gold_compute/evidence/DELIVERY.md) · [下载后复现](gold_compute/evidence/REPRODUCE.md)。
- 仓库保存正式题目、证据清单和说明；原始输入、日志、几何、Hessian通过Drive交付。当前包含886份整理证据和正式50题快照，试错包与运行缓存不在其中。
- [当前参考状态和保留项](gold_compute/queue_20261018/REFERENCE_STATUS.md)列明缺原件、端点来源限制和人工采信。题库可以加载和评分，不表示50题已全部具备可独立复现的完整原生日志。

评分仍为 `图结构0.1 + 自洽性0.3 + 准确度0.6`。反应能垒使用已确认的稳定反应物或中间体参照，IRC实际连接另行记录。IMP按最终交付判定：尝试计算后正确否定不扣分；最终误报可达或交付可信数值才扣分。

---

## 基于证据的反应机理研究

### 从机理假设到计算证据

机理研究会按需要涉及**原子映射 → 构象采样 → 有依据的TS初猜 → 鞍点优化 → 频率与虚频振动检查 → 双向IRC → 端点优化与身份确认 → 能量或热化学分析**。初猜生成成功或工具正常退出，都不能单独证明过渡态已经找到。

显式记录证据，是为了避免两类问题：

1. **结构和数字找不到出处**：坐标、能量或频率看起来合理，却无法对应到实际建模和计算结果。
2. **总结掩盖未完成的验证**：报告没有说清IRC跑偏、端点错误或驻点未验证，后续审查者也无法追溯每个结论所依据的原生日志。

### 化学工具与交付图契约

Cloudra把化学工具输出与机理图中的证据要求关联起来：

```
                    ┌─────────────────────────────────────────┐
                    │       Coordinator / Specialist Agents   │
                    └────────────────────┬────────────────────┘
                                         │  Propose Mechanism / Bind Evidence
                                         ▼
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│  Perception Layer       │ ───► │  Delivery Evidence DAG  │ ◄─── │  Scientific Supervisor  │
│  · Geometry provenance  │      │  · Immutable Artifacts  │      │  · Durable Review Inbox │
│  · Reaction Mapping     │      │  · Ordered Stage Locks  │      │  · Claim Adjudication   │
│  · CREST / xTB Ensemble │      │  · Deterministic Audit  │      │  · Read-only Graph Audit│
│  · Mayer / IBO Analysis │      └─────────────────────────┘      └─────────────────────────┘
└─────────────────────────┘
```

#### 1. 真实几何与电子结构感知层（Perception Layer）
结构化工具负责准备与检查几何，原生计算记录提供能量和频率：
- **几何来源检查（`coord_guard`）**：检查手工写入的坐标；格式转换、结构建模和量化优化提供可追溯的几何来源。
- **反应原子映射（Reaction Mapping）**：在 3D 结构中严格追踪反应物与产物的原子守恒、断键/成键配对与反应中心。
- **空间取向与构象采样**：借助CREST、xTB和约束优化，采样双分子接近取向与构象，而不是把未经松弛的摆放直接当成有效结构。
- **电子结构深度透视**：提供原子电荷、Mayer 键级（识别成键到一半的过渡态特征）、IBO Lewis 轨道图像，以及针对开壳层体系的 $\langle S^2 \rangle$ 自旋污染检测。
- **反应路径工具**：支持TS准备与精修、松弛势能面扫描、IRC端点来源追踪，以及能量、频率和收敛状态解析。初猜与搜索方式按具体化学问题选择，不把端点插值写成必经步骤。

#### 2. 交付证据图契约（Delivery-Only Evidence DAG）
机理研究到底有没有完成，系统不听模型的空头叙述，而是将假设固化为一张独立于聊天上下文的持久化**机理交付图（Delivery DAG）**：
- **元素即证据债务**：图中的节点代表基元物种在反应路径上的出现（通过将催化剂进入与催化剂回归标记为不同节点，严格保持图结构无环）；边代表基元反应步。每个元素均背负一份分阶段证据清单（Stage Contract）。
- **阶段证据要求**：每个元素按当前契约交付证据。默认机理草稿和新加反应步都要求 `ts_opt + frequency + short_irc`；`ts_guess`仅作建议，不能代替已验证鞍点。短IRC方向证明接受同一TS真实双向末帧分别优化到身份正确、零虚频的极小值，IRC本身无须完全收敛到底；在这段来源关联成立时，几何区间检查仅作提示。热化学及其他阶段按契约要求补充。
- **确定性覆盖率审计**：节点与边只接受指向不可变计算产物的强类型引用。最终交付时，系统依据严密的确定性规则计算覆盖率，只有当所有必需阶段均被验证支持（或附带充分理由显式跳过）时才允许结题。

#### 3. 工程验证与科学范围
回归测试检查运行时恢复、证据绑定、原生日志解析和评分；整理证据的日志回读核对已选参考值。这些检查与新一轮真实Agent运行、全部题目的科学验收分别记录，尚未补齐的证据保留在逐题说明中。

---

## 架构设计：Agent协作与事件驱动内核

### 角色和分工

各角色使用同一套 `runtime_v2` 执行内核，权限和职责分别明确：

- **Coordinator**拆解研究目标、委派工作，维护机理图与本次交付范围。
- **专门角色**按权限做研究、计算或写作，返回实际文件和工具回执。父子任务派发与AgentHub同伴呼叫共用项目内Agent生命周期，权限检查仍然生效。
- **Supervisor**是 `dag_guided` 下正常运行的Agent。每轮读取持久信箱中的待审证据、草稿与请求并作裁决，对交付图只读。接受草稿或同意某个声明，不能替代缺失或失败的科学证据。
- **AgentHub**保存论坛帖子、消息和同伴呼叫，让各Agent异步交换发现与进度。

### 事件驱动与动态 Notice 注入内核（S1 Event-Sourced Runtime）

Cloudra 的执行面由轻量、确定性的 `runtime_v2` 驱动：
- **全生命周期事件日志（EventLog & EventHub）**：每一次工具调用、大模型思考片段（`agent.thinking`）、状态迁移与图突变，均以只追加（append-only）的强类型事件落盘。系统天然具备审计重放、单轮崩溃退避重试（Retry）与跨进程断电恢复能力。
- **声明式 Notice 注入机制**：系统告别了容易引发脏状态污染的全局上下文拼接，而是通过 `notices.pin`（常驻置顶）与一次性推送管线，在 LLM 轮次拼装时以确定性规则注入当前的 DAG 缺口、研究目标（Goal）与调度提醒。
- **离线守护与自主 Schedule 机制**：结合底层 `ScheduleStage` 门禁与内置定时器/只读 `check_command` 轮询，Agent 可以在提交长周期计算任务后设定唤醒条件并安全挂起；检查成功或超时先到先醒，真正实现离开电脑的无人值守长程探索。
- **函数式内核与状态外化**：命令处理被拆成纯决策函数（无 IO，只产出事件草稿与副作用指令）、唯一无守卫的 `apply_event` 状态应用器（在线路径与崩溃恢复重放共用同一份逻辑）、以及负责执行副作用的薄壳层。快照只是节流缓存——恢复按每项目高水位线增量重放事件。任何持久状态都不留在进程内存里：审批、压缩请求、Agent 状态全部是事件投影，重启时孤儿审批/提问会被显式落 `approval.expired` / `interaction.expired` 终态事件，而不是无声消失。

### 进程拓扑：崩溃隔离的执行面

控制面与计算执行分开运行：

- **Web 进程**（`api_v2` + SPA，单端口）：控制面。它随时可以崩溃或重启——没有任何计算会随它死掉。
- **计算调度守护进程**（`cloudra scheduler`，自动后台拉起）：按节点容量认领队列中的作业并启动独立guard。Agent失败、取消推理或服务关停会保留量化计算。用户明确取消计算时先写 `cancel_requested`，guard只处理自己创建的进程组，确认进程退出且文件锁释放后才记录取消并释放容量。终态写入中央 `compute.db`，完成通知经数据库轮询送达控制面，API停机期间完成的作业仍可被发现。

控制面、调度器与guard之间的持久状态通过SQLite（WAL）和文件锁同步。

当前 `chem-kb` 通过图关键词匹配定位来源，再返回相应知识卡片的完整正文。图谱负责索引，不代替正文；检索不启动向量服务，也不在图匹配失败时自动扫描全文或用向量结果填补。知识健康检查分别报告图索引和来源正文是否可用。

`cloudra stop` 是显式全停入口：写入 `daemons.stop` 关停标志（自动拉起失效、守护进程自检退出），通知 API 优雅关停（取消并 await 全部 agent 运行与收尾任务、关闭流/客户端、回收归属的 JS host），并在有界等待内复查。单 agent 取消（`POST /api/v2/agents/{id}/cancel`）只停该 agent 的推理工作、不碰计算作业；已发给 LLM provider 的请求远端不可撤销——本地保证停止读取/重试/新发请求。

---

## 三种工作模式：面向科学研究的对照消融边界

为了让研究人员能够精确量化“证据图记录机制”与“独立督导审查机制”对化学机理研究真实可靠性的影响，Cloudra 设计了三种严格消融的工作模式：

| 模式 | 运行行为 | 科学定位 |
| :--- | :--- | :--- |
| `standard`（默认） | 不记录机理图，普通对话与常规计算零额外开销 | 基础对照组（衡量传统 Agent 表现） |
| `dag_record` | 机理草稿自动接受，由 Agent 自主绑定证据，无独立督导介入 | 图记录消融组（测量证据图数据结构本身的规范效能） |
| `dag_guided` | 由独立的科学督导（Supervisor）审查草稿并逐条裁决计算调用 | 完整实验组（测量引入独立同行评议式督导的增强效果） |

工作模式可在Web界面的项目设置中选择。

---

## 工具调用协议

默认协议是 `javascript`；`traditional` 是 per-agent 可选设置。默认情况下模型每次有线交换提交一段有界 JavaScript 程序（`js_exec`），在程序内编排其能力许可的工具，并用 `text(value)` 回传结果：

```js
const result = await tools.log_parser({log_path: '/absolute/path/calculation.out'});
text({call_id: result.call_id, ok: result.is_success, data: result.data});
```

设置为 `invocation_protocol: traditional`（Web 界面 Agent 设置，或设置补丁里的同一字段）时，模型改为每次有线交换发起一个工具调用，且完全不需要 JS 宿主。两种协议共用下面同一套生命周期与权限规则，区别只在派发形态。

- **同一生命周期、同一权限边界**：嵌套的 `tools.*` 调用与传统调用走同一条"持久化请求 → 策略 → 执行器 → 持久化原始结果"管线，是真实工具调用。选择该协议不授予任何额外权限——准入时重新校验能力——直接控制类工具（`stop`、`ask_user`、`schedule`）仍只能在顶层调用。
- **统一的 ToolResponse**：每个嵌套调用返回 `{call_id, is_success, summary, data, duration_ms}`。业务失败以 `is_success: false` 正常返回；策略拒绝则以可捕获的 `ToolCallError` 拒绝（`code` 如 `policy_blocked`，附 `stage` 与宿主调用 ID）——捕获它不会获得任何权限。
- **run 级冻结**：协议在 run 启动时冻结；修改设置只影响下一个 run，绝不重启或中途转换当前 run。
- **串行后端**：每个 Agent 的完整工具生命周期一次只执行一个调用，即使程序使用 `Promise.all` 也一样。不声明任何工具并行能力。
- **凭据而非隐藏状态**：`program.finished` 记录逐调用凭据（`status`、`effect_state`、`raw_result_event_id`）、程序输出与脱敏错误。UI 程序卡片直接渲染这些事件，源码下载是持久 `program.submitted` 事件的快照。
- **不恢复堆、不自动重跑**：JS 进程/堆从不做检查点。重启时将未完成的程序与调用标记为 interrupted，绝不重放副作用；失败的程序只返回一次普通的失败交换，后续模型轮次可提交修复后的程序。

### 安装

访客程序运行在独立 Node ≥ 22 进程内的 QuickJS-WASM 中。一次性安装锁定的宿主依赖：

```bash
npm ci --prefix cloudra/runtime_v2/js_host --ignore-scripts --no-audit --no-fund
```

Cloudra 在执行或服务启动期间绝不运行 npm。缺少 Node 或依赖时，`javascript` 模式的 run（默认协议）报告 `runtime_unavailable`，不做任何静默回退；`traditional` 模式的 run 完全不需要 JS 依赖。对 pip 安装的包，对 `<site-packages>/cloudra/runtime_v2/js_host` 执行同一命令。

### 安全边界

支持的威胁模型是**本地单用户运行时**：在 QuickJS-WASM、可杀死的进程与敌意输入校验的桥接之内遏制不可信的生成 JS——64 KiB 源码上限、有界 JSON 行传输、1 MiB 工具结果上限、CPU 中断检查、15 秒空闲看门狗、`--max-old-space-size=128`（V8 堆提示，不是 OS RSS 限制）、最小环境变量、固定在用户工作区之外的 cwd。这**不是**加固的多租户 OS 沙箱：Node/引擎漏洞属于残余风险，最小 cwd/env 无法阻止被攻陷的宿主读取文件。OS 级沙箱/容器明确不在范围内——请勿运行你不信任的程序。

---

## 计算生态与基础设施

Cloudra 深度集成了计算化学主流工具链与高性能计算基础设施：

- **量子化学与物理计算**：支持 Gaussian、ORCA、xTB、CREST、VASP、CP2K 等主流程序；具备自动输入文件生成、本地执行守卫与 Slurm 集群作业异步托管能力。
- **化学信息学与微观表征**：无缝对接 RDKit、OpenBabel、Multiwfn、Molli 接口，支持分子 3D 构型修正、NMR/IR 光谱解析、反应物料守恒计算，以及高保真 CDXML 反应式解析（保留手性、连接关系、电荷与多重度）。
- **文献整合与学术写作**：提供OpenAlex文献检索和LaTeX/Markdown报告工具；研究报告应注明来源文献、计算方法与证据路径。

---

## 仓库结构

```text
cloudra/                         Python 包：运行内核、服务、工具、评测、prompts 与 skills
frontend/                        React + TypeScript + Vite Web 控制台
scripts/                         安装、运行、数据脚本与 application_docs/ 一次性文档编辑脚本
deploy/                          部署与远程计算指南
tests/                           回归测试与科学验证样本
docs/                            当前架构/SOP、证据、许可证、标志资源与 archive/
paper/                           论文正文、literature/ 文献原件与 archive/ 调研快照
ideapool/                        版本化题源、生成题集与历史调研
gold_compute/                    Gold状态、证据索引、Drive交付/复现说明与归档
kg_data/, vector_store/          知识图谱输入与向量元数据
知识卡片/                       知识卡片源档案
```

详细入口见[文档中心](docs/README.md)、[脚本索引](scripts/README.md)和[文献索引](paper/literature/README.md)。根目录保留配置、许可证/引用文件与 `install.sh`、`web.sh`；临时运行目录和构建产物不入库。申报交付物、答辩 PPT 和制作工作区已移出当前版本，旧材料可从 Git 历史恢复。

---

## 开发与测试

先做语法与规范检查，再运行改动模块的相关测试。完整套件交给CI，本地日常修改不跑全集。

```bash
uv run python -m compileall -q cloudra tests
uv run ruff check cloudra tests
uv run pytest -q tests/test_dag_engine.py        # 例如：DAG引擎改动
uv run pytest -q tests/test_runtime_v2_replay_equivalence.py  # 例如：恢复与重放改动
```

Benchmark与原生日志回读见[运行说明](cloudra/benchmark/README.md)。回读原件前须先按[Drive复现说明](gold_compute/evidence/REPRODUCE.md)恢复文件；普通代码与单元检查不自动下载云端证据。

---

## 引用

若在科研工作中使用或参考了 Cloudra，请引用本仓库并注明具体的 Commit Hash：

```bibtex
@misc{cloudra2026,
  title  = {Cloudra: An Autonomous Agent for Organic Small-Molecule Mechanism Computation},
  author = {{Cloudra Developers}},
  year   = {2026},
  url    = {https://github.com/yyywaa/Cloudra-mechanism-agent},
  note   = {Commit-pinned research software for mechanistic organic chemistry}
}
```

## 开源许可证

Copyright (C) 2026 Cloudra Team。

Cloudra 是自由软件：你可以依照[ GNU Affero 通用公共许可证](LICENSE)（由自由软件基金会发布）的条款重新发布和/或修改它，许可证版本为第 3 版，或（由你选择）任何更新的版本。

Cloudra 的分发是希望它能有用，但不提供任何担保；甚至不提供适销性或特定用途适用性的默示担保。详情见 [GNU Affero 通用公共许可证](LICENSE)。

本仓库内嵌的第三方组件各自保留其原有许可证，见 [docs/licenses/](docs/licenses/README.md)。

`cloudra/skills/` 下的技能是有意的例外：每个技能在 frontmatter 中声明 `license: MIT`，采用 MIT 许可，以便这些知识能被其他 Agent harness 无障碍采用。引擎、DAG、工具与调度器仍然遵循 AGPL。

贡献采用 Developer Certificate of Origin 模式，请使用 `git commit -s` 签署提交，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
