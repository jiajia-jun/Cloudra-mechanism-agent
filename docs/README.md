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
| [`../scripts/README.md`](../scripts/README.md) | 开发、运行、数据维护与一次性文档脚本索引 |
| [`licenses/README.md`](licenses/README.md) | 项目许可证与第三方代码归属 |
| `superpowers/plans/` `superpowers/specs/` | **设计历史**（按日期归档惯例保留，不更新） |
| `gold_compute/README.md` | gold 战役现行策略：边选反应边填自算 gold；候选不来自既有文档 |
| `ideapool/reaction_candidates/*.md` | **存量** benchmark 题源（生成器输入）；本轮新候选另开策展，不从这里抄 |

## 归档位置

- `docs/archive/`：已实现的架构计划（DAG schema 重构、TS 后端门）、benchmark
  设计调研（benchmark_survey/）、评测报告（benchmarks/），以及已完成的
  [TS 交接](archive/HANDOFF_ts_strict_verify.md)和[旧运行异常记录](archive/HARNESS_NOTES.md)；
- `gold_compute/archive/`：已废止的 gold 战役计划（旧池全边 DFT、文献填充、批次手记），
  以及已完成的[能垒回填](../gold_compute/archive/HANDOFF_backfill.md)和
  [HG2 配对纠正](../gold_compute/archive/HANDOFF_hg2_pairing.md)交接；
- `paper/archive/`：论文进度手记、参考答案分工计划、被 narrative 取代的
  benchmark_construction 初稿，以及[阶段性文献调研快照](../paper/archive/chemistry_ai_agents_literature_report.md)；
- `ideapool/archive/`：GraphRAG 指南、benchmark 文献遴选、novelty 计划旧版
  （v0.7，由 `docs/novelty.md` 取代）。

## 写作区（非本中心管辖）

- `paper/`：论文正文（`draft.md`、`main.tex`、`sections/`、
  `benchmark_construction_narrative.md`、`literature_gap_analysis.md`、
  `supplementary_information.md`）；
- [`paper/literature/`](../paper/literature/README.md)：文献原件与下载残留索引；
- `assets/`：标志原图；前端使用的静态资源仍在 `frontend/public/`；
- `知识卡片/`、`申请材料/`、`软著申请材料/`：外部交付物，保持原路径。
