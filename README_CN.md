# Cloudra

**面向有机小分子机理计算的自主 Agent 系统**  
*基于真实几何与电子感知 · DAG 交付契约驱动 · 无政府主义平权多 Agent 架构*

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](pyproject.toml)

[English](README.md) · [文档索引](docs/README.md) · [DAG 编排规范](docs/DAG_ORCHESTRATION.md)

> Cloudra 是一套面向计算化学机理探索的科研 Agent 系统。我们不声称能替代人类化学家给出绝对真理，也不盲目追求打榜指标；我们的核心目标是为长程、复杂的反应机理计算建立一套**不可造假、可确定性复核、能真正感知微观分子**的严密研究底座。

---

## 快速上手

### 1. 环境准备与安装

系统需要 Python ≥ 3.11 与 Node.js ≥ 18，以及可访问的 OpenAI 兼容大模型 API。

```bash
# 克隆仓库
git clone https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent

# 一键安装环境（自动配置 Python 虚拟环境与依赖）
./install.sh                 # Linux / macOS
# .\install.ps1              # Windows PowerShell

# 初始化配置文件
cloudra config init
```

### 2. 启动 Web 全栈工作台

Cloudra 提供单端口集成的现代 Web 控制台（FastAPI 控制面 + React/Vite SPA 前端）：

```bash
cloudra                      # 自动构建前端并拉起 Web 服务，同时打开浏览器
cloudra web --skip-build     # 复用已构建的前端资源快速启动
```

### 3. 极客风快捷指令（Slash Commands）

在主聊天框中键入 `/`，系统会自动弹出无冗余的快捷补全浮层，支持键盘上下切换与 Tab 快速补全：

- `/schedule [on|off]`：切换无人值守调度守护模式。开启后，Agent 在没有设定自唤醒闹钟时试图停止将被系统强制拦截，确保离线长任务不丢失。
- `/goal <任务目标描述>`：为当前会话锚定核心研究目标。该目标经过多轮上下文压缩依然常驻。
- `/yolo [on|off]`：一键热切换自动化安全审批（YOLO 模式），自动放行文件写入与高危计算提交。
- `/compact`：手动触发上下文结构化压缩，生成带文件交接指针的摘要并归档历史。
- `/help`：快速呼出指令指南。

### 4. 联网搜索配置（可选）

Cloudra 支持模型服务商的原生搜索与外部多引擎检索：

```bash
export CLOUDRA_COORDINATOR__NATIVE_SEARCH=auto        # off / auto / openai / openrouter / deepseek / gemini / custom
export CLOUDRA_COORDINATOR__NATIVE_SEARCH_PARAMS='{}' # 自定义注入参数（自建代理站使用）
```

若未开启原生搜索，系统会自动回落至外部检索工具（Tavily / Brave / Bing / DuckDuckGo）。

---

## 核心 Novelty：DAG 驱动的有机小分子机理计算

### 传统大模型做机理研究的致命瓶颈

在经典的有机反应机理研究中，从反应物出发到最终确立反应坐标是一条精密的长计算链：**原子映射 → 空间构象采样 → 过渡态初猜 → 鞍点优化 → 唯一虚频确认 → 双向 IRC 路径跟踪 → 端点几何优化 → 产物同构匹配 → 高精度热力学与活化能计算**。

以往的通用 LLM Agent 在处理化学问题时，通常把科研简化为“调工具 + 编文字”，从而不可避免地遭遇两重严重失效：

1. **微观结构盲区与空间幻觉**：大语言模型无法直接“看见”三维分子空间。在缺乏硬性物理约束时，模型会凭空捏造原子坐标、凭直觉摆放双分子进攻取向，并在漫长对话中逐渐遗忘工具输出的关键能量与虚频数值。
2. **“靠嘴宣布完成”的信任危机**：机理是否真正成立，往往由模型自己写一段看似严谨的总结散文来单方面判定。一段流畅的技术叙述经常掩盖了 IRC 路径跑偏、虚频不对或端点不匹配的硬伤，事后没有任何持久化证据能够证明哪一步结论基于哪次真实的量化计算。

### Cloudra 的解法：感知层 + 交付图契约

Cloudra 通过两条相互咬合的系统设计攻克上述缺陷：

```
                    ┌─────────────────────────────────────────┐
                    │       Coordinator / Peer Sub-Agents     │
                    └────────────────────┬────────────────────┘
                                         │  Propose Mechanism / Bind Evidence
                                         ▼
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│  Perception Layer       │ ───► │  Delivery Evidence DAG  │ ◄─── │  Scientific Supervisor  │
│  · No hand-written xyz  │      │  · Immutable Artifacts  │      │  · Review Call Inbox    │
│  · Reaction Mapping     │      │  · Ordered Stage Locks  │      │  · Gate Unlocking       │
│  · CREST / xTB Ensemble │      │  · Deterministic Audit  │      │  · Non-modifying Audit  │
│  · Mayer / IBO Analysis │      └─────────────────────────┘      └─────────────────────────┘
└─────────────────────────┘
```

#### 1. 真实几何与电子结构感知层（Perception Layer）
Agent 绝不手写坐标，也绝不凭模糊记忆转述数值，而是通过结构化感知工具与真实的物理引擎交互：
- **严格禁止手写坐标（`coord_guard` 物理守卫）**：无论是生成 `.gjf` 输入文件还是修改分子，坐标必须由标准工具链生成，从根本上杜绝坐标幻觉。
- **反应原子映射（Reaction Mapping）**：在 3D 结构中严格追踪反应物与产物的原子守恒、断键/成键配对与反应中心。
- **空间取向与构象采样**：借助 CREST 和 xTB 动力学松弛，在受约束的反应距离盒中进行构象系综采样，双分子如何靠近由力场松弛决定，拒绝人工摆放。
- **电子结构深度透视**：提供原子电荷、Mayer 键级（识别成键到一半的过渡态特征）、IBO Lewis 轨道图像，以及针对开壳层体系的 $\langle S^2 \rangle$ 自旋污染检测。
- **全流程路径工具**：支持 IDPP 鞍点插值初猜、柔性势能面扫描、严格的双向 IRC 积分分析，以及能够直接提取收敛状态、能量与振动模式的日志解析器。

#### 2. 交付证据图契约（Delivery-Only Evidence DAG）
机理研究到底有没有完成，系统不听模型的空头叙述，而是将假设固化为一张独立于聊天上下文的持久化**机理交付图（Delivery DAG）**：
- **元素即证据债务**：图中的节点代表基元物种在反应路径上的出现（通过将催化剂进入与催化剂回归标记为不同节点，严格保持图结构无环）；边代表基元反应步。每个元素均背负一份分阶段证据清单（Stage Contract）。
- **不可逾越的阶段锁**：基元反应步必须严格按照 `ts_guess`（初猜）→ `ts_opt`（鞍点优化）→ `frequency`（唯一虚频）→ `short_irc`（双向路径跟踪）→ `endpoints`（端点优化）→ `direction`（同构确认）→ `thermochemistry`（热化学量）的顺序依次交账，前置阶段未被支持前，后置阶段不可绑定。
- **确定性覆盖率审计**：节点与边只接受指向不可变计算产物的强类型引用。最终交付时，系统依据严密的确定性规则计算覆盖率，只有当所有必需阶段均被验证支持（或附带充分理由显式跳过）时才允许结题。

#### 3. 端到端机理研究实证
Cloudra 已在引导模式下全自动跑通 **Diels-Alder 环加成反应机理的端到端研究**：从文献与前驱体解析出发，自动构建机理图并逐一完成过渡态搜索、唯一虚频验证、IRC 双向跟踪、端点匹配与热力学势能面标定，整个计算轨迹与证据链均留存在数据库中，完全可追溯、可复查。

---

## 架构设计：无政府主义平权自组织与事件驱动内核

### 无政府主义设计哲学（Anarchist Peer-to-Peer Topology）

传统的多 Agent 系统往往迷信科层制的金字塔结构，设立自上而下的指挥官与繁琐的管理汇报层级，导致决策瓶颈与严重的上下文失真。

Cloudra 采用**无政府主义的平权设计哲学**：
- **平等协作，唯有专业分工不同**：在 Cloudra 中，没有主从依附或阶级高低的 Agent。无论是负责全局规划的 `coordinator`，还是专注量化计算的 `dft`、探索反应空间的 `explorer`、精通文献调研的 `researcher`、处理分子动力学的 `md`、拟定实验方案的 `experiment` 或是撰写报告的 `writer`，它们在内核中拥有完全平等的地位和独立的生命周期。
- **异步论坛与自由呼叫（AgentHub）**：Agent 之间通过共享的 `AgentHub` 论坛进行异步信息广播与发现共享。任何 Agent 都可以发帖、阅读最新进展，或直接使用 `call` 机制呼叫其他专长角色协同作战。任务由具备相应能力的 Agent 自主认领响应，形成去中心化的网状科研协作体。

### 事件驱动与动态 Notice 注入内核（S1 Event-Sourced Runtime）

Cloudra 的执行面由轻量、确定性的 `runtime_v2` 驱动：
- **全生命周期事件日志（EventLog & EventHub）**：每一次工具调用、大模型思考片段（`agent.thinking`）、状态迁移与图突变，均以只追加（append-only）的强类型事件落盘。系统天然具备审计重放、单轮崩溃退避重试（Retry）与跨进程断电恢复能力。
- **声明式 Notice 注入机制**：系统告别了容易引发脏状态污染的全局上下文拼接，而是通过 `notices.pin`（常驻置顶）与一次性推送管线，在 LLM 轮次拼装时以确定性规则注入当前的 DAG 缺口、研究目标（Goal）与调度提醒。
- **离线守护与自主 Schedule 机制**：结合底层 `ScheduleStage` 门禁与内置定时器系统，Agent 可以在提交长周期计算任务后主动设定闹钟并安全挂起；当闹钟触发或计算作业就绪时，系统会自动唤醒沉睡的 Agent 继续推进，真正实现离开电脑的无人值守长程探索。

---

## 三种工作模式：面向科学研究的对照消融边界

为了让研究人员能够精确量化“证据图记录机制”与“独立督导审查机制”对化学机理研究真实可靠性的影响，Cloudra 设计了三种严格消融的工作模式：

| 模式 | 运行行为 | 科学定位 |
| :--- | :--- | :--- |
| `standard`（默认） | 不记录机理图，普通对话与常规计算零额外开销 | 基础对照组（衡量传统 Agent 表现） |
| `dag_record` | 机理草稿自动接受，由 Agent 自主绑定证据，无独立督导介入 | 图记录消融组（测量证据图数据结构本身的规范效能） |
| `dag_guided` | 由独立的科学督导（Supervisor）审查草稿并逐条裁决计算调用 | 完整实验组（测量引入独立同行评议式督导的增强效果） |

工作模式可在 Web 界面的项目设置中实时无缝切换。

---

## 计算生态与基础设施

Cloudra 深度集成了计算化学主流工具链与高性能计算基础设施：

- **量子化学与物理计算**：支持 Gaussian、ORCA、xTB、CREST、VASP、CP2K 等主流程序；具备自动输入文件生成、本地执行守卫与 Slurm 集群作业异步托管能力。
- **化学信息学与微观表征**：无缝对接 RDKit、OpenBabel、Multiwfn、Molli 接口，支持分子 3D 构型修正、NMR/IR 光谱解析、反应物料守恒计算，以及高保真 CDXML 反应式解析（保留手性、连接关系、电荷与多重度）。
- **文献整合与学术写作**：内置 OpenAlex 科学文献检索与 LaTeX/Markdown 学术转化能力，所有结论均强制标注来源文献与理论级别（Level of Theory）。

---

## 仓库结构

```text
cloudra/
├── core/                        Agent 基类与科学督导（Supervisor）
├── services/                    控制面 API 服务（薄路由，基于 FastAPI）
├── persistence/                 SQLite 持久化、不可变产物快照、长期记忆、路径管理
├── base/                        数据契约与工具/技能加载基类
├── infra/                       多节点配置、LLM 传输层、事件总线、平台适配
├── dag/                         机理证据交付图子系统（Engine, Store, Controller）
├── runtime/                     确定性 prompt 组装、工作区快照、计算作业代理与监视
├── runtime_v2/                  事件驱动推理新内核（Pipeline, Commands, PolicyStages, Bridges）
├── tools/, subagents/           几何与电子感知工具库、领域专长 Agent（dft, md, explorer 等）
├── skills/, prompts/            实验方法学技能包与经过版本控制的角色策略
└── frontend/                    React + TypeScript + Vite 现代化 Web 控制台
```

---

## 开发与测试

运行全套单元测试与代码风格静态检查：

```bash
uv run pytest -q tests/            # 执行全套 700+ 项自动化测试
uv run pytest -q tests/test_dag*   # 聚焦 DAG 编排子系统
uv run pytest -q tests/test_runtime_v2* # 聚焦新内核与策略门禁
uv run ruff check cloudra tests    # 代码规范检查（line-length 120）
```

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

本项目采用 [MIT 许可证](pyproject.toml)。
