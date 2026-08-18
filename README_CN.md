# Cloudra

**自主有机小分子机理计算 Agent：几何与电子感知 + 可审计机理证据链。**

[![CI](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/ci.yml)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](pyproject.toml)

[English](README.md) · [文档索引](docs/README.md) · [DAG 编排](docs/DAG_ORCHESTRATION.md)

> Cloudra 是仍在积极开发的研究软件。它不声称能自主保证科学结论正确，也不声称在
> benchmark 上优于其他方案。已验证的范围与明确不作声明的证据见[验证现状](#验证现状)。

## 研究问题：LLM 做机理研究，为什么会失败

小分子反应机理的阐明是一条环环相扣的长计算链：原子映射 → 构象采样 → 过渡态搜索 →
频率分析 → IRC → 端点优化 → 热化学。今天的 LLM Agent 大多把化学当成"调工具 +
写总结"，在这类研究上有两种典型失败，而且都伤在"可信"二字上：

1. **模型感知不到分子。** 放任自流时，模型会手写坐标、凭感觉摆分子取向、凭逐渐
   漂移的记忆转述工具输出的数值。而几何与电子结构——机理恰恰由它们构成——正是
   语言模型看不见的东西。
2. **完成靠宣布，不靠证据。** 机理是否真正确立，由模型自己的总结来判断。一段
   读起来合理的文字可以代替一条经过 IRC 验证的反应路径；没有任何持久记录说明
   哪一步建立在哪份证据上。

Cloudra 用两条互相咬合的设计对症这两种失败：

- **几何与电子感知**——Agent 通过结构化工具*感知*分子：从不手写坐标，也不凭记忆
  转述数值，而是逐字引用当次计算输出；
- **机理证据图**——机理假设被落成一张可审计的证据图，完成度由确定性规则**算出来**，
  而不是由模型**说出来**。

这套组合已经**完整跑通了一整个 D-A 环加成机理研究**（见
[一次完整的端到端演示：D-A 环加成](#一次完整的端到端演示d-a环加成)）。

## 设计一：让模型真正"看见"分子

Cloudra 的 Agent 有一整套面向分子的"眼睛和手"，全部返回结构化结果，代替了对坐标
和能量的手写与转述：

- **原子映射**：给出反应物与产物的原子对应关系，标出哪些键断开、哪些键形成，
  并跟随具体 3D 结构追踪反应中心。
- **结构分析**：报告键长键角异常、区分可旋转键、识别立体化学，并支持编辑反应
  中心的内坐标（Z-matrix）。
- **构象搜索**：把反应原子对锁定在合理距离内采样构象；双分子如何靠近由
  力场/xtb 弛豫决定，而不是靠猜。
- **电子结构分析**：原子电荷、Mayer 键级（能看到"成了一半"的键）、IBO Lewis
  图像、开壳层自旋与 ⟨S²⟩ 检查。
- **反应路径**：IDPP 插值过渡态初猜、扫描准备/解析、严格的 IRC 方向验证，以及
  返回结构化能量、频率与收敛状态的日志解析。

所有角色执行同一条硬规则：**禁止手写坐标**——"只是微调几个原子"也没有例外。

## 设计二：把机理假设变成可审计的证据图

机理研究"到底研究清楚了没有"，不能听模型一句话。Cloudra 把正在研究的机理落成
一张持久的**机理证据图**——它是唯一长期保存的图，独立于聊天上下文：

- **图上的每个元素都欠着明确的"证据债"。** 节点是中间体在路径上的每一次出现；
  催化循环把"催化剂进入"与"催化剂回归"记成不同节点，从而保持图无环。边是基元
  反应步。每个元素挂着一份**分阶段证据清单**：中间体要经过几何优化、频率、单点
  能；基元步则要按过渡态初猜 → 过渡态优化 → 频率（且虚频唯一）→ 短 IRC → 两个
  端点 → 方向/身份确认 → 热化学的顺序逐项交账。顺序不能跳，前面欠的后面补不上。
- **证据必须是不可变记录，不是散文。** 每个节点和边携带类型化引用（计算产物 /
  计算作业 / 工具结果 / 物种记录），指向不可变的存档；一个裸文件路径或一句
  "已确认"都不算证据。模型永远不能自己把结论标成"完成"。
- **交付由覆盖率审计把关。** 声明完成时，系统逐阶段核对：每个必需阶段要么有
  支持的证据，要么被显式"跳过"且附上理由。被复核**驳回**的证据不是处置——那是
  仍然欠着的开放缺口，只能靠重新补证据或显式跳过关闭。只有用户本人能豁免
  交付门槛。
- **独立的科学督导。** 在引导模式下，一个专门的督导角色（Supervisor）负责：
  接受或驳回机理草稿（接受前计算入口保持关闭），随后逐条复核每个与交付相关的
  计算调用，把证据绑定到对应阶段。它不能改动机理图结构、不能替模型"提升"证据、
  不能宣布研究完成。
- **证据是动态补齐的。** 每次与交付相关的工具调用或计算作业完成后，都会进入
  督导的复核收件箱；督导对每条给出"同意/驳回/跳过"的判定并说明理由。整个过程
  ——每一次图变更、操作者、理由和证据引用——都持久化在会话数据库里，事后可以
  完整审计。

## 一次完整的端到端演示：D-A 环加成

Cloudra 已在引导模式下**完整跑通 D-A 环加成机理研究**：

- 协调 Agent（Coordinator）拆解目标，派出文献与领域子 Agent，并把候选机理连同
  每个元素的证据清单设计成机理证据图；
- 科学督导接受机理草稿后解锁计算，随后复核每一个与交付相关的调用——反应映射、
  构象采样、TS 搜索、优化+频率、短双向 IRC、端点优化、端点匹配、热化学——把
  证据逐阶段绑定，并对失败和不合格的证据做出反应；
- 系统的确定性校验把关每次阶段绑定（顺序、调用成功、证据是完工产物而非提交
  记录、解析器检查）；
- 最终交付由确定性覆盖率报告把关：声称的基元步达到端点级证据（IRC 链接、端点
  优化完成），报告的能量带明确的理论级别（level of theory）来源说明。

完整轨迹事后可查、可审计——这本身也是机理研究"可复现"的一部分。

## 三种工作模式：为对照研究设计的消融边界

证据图的效果和督导监督的效果，能不能分开测量？Cloudra 让每个项目在三种模式间
选择（运行中也可以随时切换）：

| 模式 | 行为 |
| --- | --- |
| `standard`（默认） | 不记任何图，普通科研工作零额外成本 |
| `dag_record` | 草稿自动接受，Coordinator 自己绑定证据，无独立督导 |
| `dag_guided` | 督导接受草稿 + 逐条复核每个与交付相关的调用 |

三档构成一组对照实验：记录证据的模式对比普通模式，可以测量"记录证据图本身的
效果"；引入督导监督的模式对比纯记录，可以测量"独立督导监督的效果"。模式在
Web UI 的项目设置中切换。

## 研究过程中的辅助能力

除了两条核心设计，Cloudra 还提供一整套面向长程研究的辅助设施：

- **多 Agent 协作**：一个协调 Agent 派发领域子 Agent——文献调研、小分子量化计算、
  分子动力学、第一性原理、实验设计、论文写作、环境管理——批量并行、互相呼叫，
  结果汇聚回协调 Agent。
- **目标锚点与上下文压缩**：用 `/goal` 命令固定研究目标（上下文压缩后仍然保留）；
  长会话可手动压缩（`/compact`），摘要后继续工作。
- **定时提醒**：为计算、会议或灵感设置提醒，到点自动唤醒 Agent。
- **Agent 论坛**：并行子 Agent 可以共享发现、互相通知与呼叫。
- **审批与提问**：危险操作（改文件、提交计算等）需用户批准；Agent 可随时向用户
  提问，全程在界面面板中交互。
- **自动恢复**：单轮失败原地自动重试；进程重启后，对之前中断的 Agent 发一条
  消息即可自动重开，实验不会因断电丢状态。

## 覆盖范围

当前工具与技能生态覆盖：

- 小分子量子化学：结构准备、构象搜索、TS/IRC 工作流、Gaussian / ORCA 输入
  生成、计算作业异步提交（Gaussian / VASP / ORCA / CP2K）、状态监控和日志解析；
- 电子结构分析、原子映射、格式转换、可视化和图像到结构工作流；
- 文献检索（OpenAlex 等）、文档转换、证据整合与学术写作，联网搜索（服务商
  原生或外部工具）并附来源引用；
- NMR 与 IR 数据处理；
- 分子动力学、周期第一性原理、实验设计和科研软件环境的领域规划。

"有工具"不等于"结论正确"。方法选择、收敛性、对照、不确定性与结果解释仍需研究者
负责。Cloudra 的目标是保留完成这些审阅所需的证据。

## 验证现状

自动化测试覆盖图存储与变更引擎（无环性、不可变证据引用、原子批次、并发冲突
检测、分权边界）、确定性交付完成度、模式隔离、会话持久化与重启恢复、感知工具
（原子映射、内坐标、构象搜索、TS/扫描解析、日志解析）、prompt 组装、命令幂等、
产物快照边界、节点路由、Slurm 命令构造和备份恢复。CI 在 CPython 3.11–3.13 上
运行全套测试。上述 D-A 环加成研究是一次已演示的端到端运行，不是 benchmark。

以下证据仍然缺失，因此项目**不作对应声明**：

- 与其他 Agent 或人类基线对比的科研 benchmark 结果；
- 多反应体系上机理发现成功率的系统性评测；
- 真实 Slurm 集群上的提交、取消和恢复实验；
- 公网部署和长周期运维可靠性。

## 安装

Cloudra 需要 Python 3.11 或更新版本，以及 OpenAI 兼容的模型服务。

```bash
git clone https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
cloudra config init
```

开发 checkout 也可以用一键安装脚本：

```bash
./install.sh                 # Linux / macOS
# .\install.ps1              # Windows PowerShell
```

如果集群 home 位于 NFS/Lustre，应把 `CLOUDRA_DATA_DIR` 放到具有可靠文件锁的本地
磁盘；SQLite WAL 不能充当多主机共享数据库。

### 联网搜索配置

默认 `native_search=auto`：按模型服务地址（`base_url`）与模型名自动识别并启用
服务商侧原生搜索。需要时可用环境变量覆盖：

```bash
export CLOUDRA_COORDINATOR__NATIVE_SEARCH=auto        # off / auto / openai / openrouter / deepseek / gemini / custom
export CLOUDRA_COORDINATOR__NATIVE_SEARCH_PARAMS='{}' # 自定义注入参数（自建中转站用）
```

未启用原生搜索时，Agent 使用外部 `web_search` 工具（Tavily / Brave / Bing /
DuckDuckGo）作为兜底。启用后外部工具会被剔除，避免双重搜索。
请注意，外部工具的性能要比模型内部搜索弱一些。

## 使用入口

推荐使用 Web 前端（需要 Node.js >= 18）：

```bash
./install.sh               # 首次：安装 Python 包并初始化配置
cloudra                    # 安装 npm 依赖、构建并启动 Web 服务
cloudra web --skip-build   # 复用已经构建的 frontend/dist
```

Web UI 提供：按项目隔离的工作区、可在所有并行 Agent 间切换的 AgentBar、逐条
事件可追溯的 Inspector、运行中切换自动审批（YOLO）/模型、审批/提问/产物控制
面板、`/goal` 与 `/compact` 命令，以及机理证据图与复核收件箱面板（DAG 面板）。

真实计算需要对应科研软件及许可证。

## 可复现性

用于科研时，请固定 commit hash，并记录模型、prompt、工具版本、软件环境和计算
输入。运行时会记录每次 prompt 组装的版本；证据图会话还会随会话保存督导
模型、prompt 版本与图策略版本的快照；每一次图变更的操作者、理由和基线版本都
留在只追加的变更日志里。

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/DAG_ORCHESTRATION.md`](docs/DAG_ORCHESTRATION.md) | 机理证据图编排：分阶段证据清单、三种模式、分权与证据派生（面向开发者） |
| [`docs/PHASE8_NODE_REGISTRY.md`](docs/PHASE8_NODE_REGISTRY.md) | JSON 节点注册表、工作区路由、local/Slurm 计算执行与恢复语义（面向部署） |
| [`AGENTS.md`](AGENTS.md) | 仓库地图与开发约定（面向贡献者） |

## 仓库结构

```text
cloudra/
├── core/                        Agent 基类与科学督导
├── services/                    控制面 API（唯一 HTTP 服务）
├── persistence/                 SQLite 持久化、产物快照、记忆、路径
├── base/                        数据类与加载器基类
├── infra/                       配置、LLM 传输、事件、平台支撑
├── dag/                         机理证据图子系统（可选，按项目开启）
├── runtime/                     prompt 组装、工作区快照、计算作业代理与日志监视
├── runtime_v2/                  事件驱动推理内核（唯一推理循环）
├── tools/, subagents/           感知工具、科研能力与领域角色
├── skills/, prompts/            科研方法与角色策略
└── frontend/                    React Web 控制界面
```

## 开发

```bash
uv run pytest -q tests/            # 全套测试
uv run ruff check cloudra tests    # lint（line-length 120）
```

## 引用

Cloudra 目前没有归档 release。在归档版本发布前，请连同使用的确切 commit 一起
引用本仓库：

```bibtex
@misc{cloudra,
  title  = {Cloudra: An Autonomous Agent for Organic Small-Molecule Mechanism Computation},
  author = {{Cloudra Developers}},
  year   = {2026},
  url    = {https://github.com/yyywaa/Cloudra-mechanism-agent},
  note   = {Commit-pinned research software; see repository README for evaluation status}
}
```

只有完成对应评测的版本才会加入正式 citation 文件和 benchmark 报告。

## 许可证

MIT，见 [`pyproject.toml`](pyproject.toml)。
