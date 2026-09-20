# Cloudra 文档中心

> **治理规则（2026-09-20 起）**：计划书 / 调研报告 / 进度手记 / 工作分工这类
> 阶段性文档，**完成使命即归档**（移入就近的 `archive/`），不再保留在主线；
> 主线只留「描述当前状态、随代码同步更新」的权威文档。判断标准一句话：
> 六个月后它描述的还是现状吗？不是就该在 archive/ 里。

## 权威文档（随代码同步更新）

| 文档 | 主题 |
| :--- | :--- |
| 根 `README.md` / `AGENTS.md` / `CHANGELOG.md` | 项目定位、仓库地图（模块职责与坑点）、演进记录 |
| [`DAG_ORCHESTRATION.md`](DAG_ORCHESTRATION.md) | 机理交付图编排规范（runtime_v2 核心编排） |
| [`TS_PROCESS_SOP.md`](TS_PROCESS_SOP.md) | TS 搜索自动化流程 SOP（`ts_prepare`/`ts_resume`） |
| [`KNOWLEDGE_TAGS.md`](KNOWLEDGE_TAGS.md) | 知识库标签体系 |
| [`PHASE8_NODE_REGISTRY.md`](PHASE8_NODE_REGISTRY.md) | 多节点/Slurm 注册表 |
| [`PLUGINS.md`](PLUGINS.md) | 插件机制 |
| [`novelty.md`](novelty.md) | 学术与技术定位（对标 El Agente 系列，论文立项依据） |
| `superpowers/plans/` `superpowers/specs/` | **设计历史**（按日期归档惯例保留，不更新） |
| `gold_compute/README.md` | gold 能垒 DFT 打标战役：目标、口径、验收标准、总账与缺口队列 |
| `ideapool/reaction_candidates/*.md` | benchmark 题源（生成器输入，**活文档**） |

## 归档位置

- `docs/archive/`：已实现的架构计划（DAG schema 重构、TS 后端门）、benchmark
  设计调研（benchmark_survey/）、评测报告（benchmarks/）；
- `gold_compute/archive/`：gold 战役批次文档与文献填充阶段记录；
- `paper/archive/`：论文进度手记、参考答案分工计划、被 narrative 取代的
  benchmark_construction 初稿；
- `ideapool/archive/`：GraphRAG 指南、benchmark 文献遴选、novelty 计划旧版
  （v0.7，由 `docs/novelty.md` 取代）。

## 写作区（非本中心管辖）

- `paper/`：论文正文（`draft.md`、`main.tex`、`sections/`、
  `benchmark_construction_narrative.md`、`literature_gap_analysis.md`、
  `supplementary_information.md`）；
- `知识卡片/`、`申请材料/`、`软著申请材料/`：外部交付物。
