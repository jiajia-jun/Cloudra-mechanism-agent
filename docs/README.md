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
| [`RUNTIME_OBSERVABILITY.md`](RUNTIME_OBSERVABILITY.md) | Agent 活动、工具完整回执、实时阶段与计算关联 API |
| [`TS_PROCESS_SOP.md`](TS_PROCESS_SOP.md) | TS 搜索自动化流程 SOP（`ts_prepare`/`ts_resume`） |
| [`TS_STATE_MACHINE_ACCEPTANCE.md`](TS_STATE_MACHINE_ACCEPTANCE.md) | TS 状态机阶段、证据关联与验收语义 |
| [`KNOWLEDGE_TAGS.md`](KNOWLEDGE_TAGS.md) | 知识库标签体系 |
| [`PHASE8_NODE_REGISTRY.md`](PHASE8_NODE_REGISTRY.md) | 多节点/Slurm 注册表 |
| [`PLUGINS.md`](PLUGINS.md) | 插件机制 |
| [`novelty.md`](novelty.md) | 学术与技术定位（对标 El Agente 系列，论文立项依据） |
| [`../scripts/README.md`](../scripts/README.md) | 开发、运行、数据维护与一次性文档脚本索引 |
| [`licenses/README.md`](licenses/README.md) | 项目许可证与第三方代码归属 |
| `superpowers/plans/` `superpowers/specs/` | **设计历史**（按日期归档惯例保留，不更新） |
| [`../cloudra/benchmark/README.md`](../cloudra/benchmark/README.md) | 当前 50 题 Benchmark 运行入口、方法范围和评分口径 |
| [`../gold_compute/queue_20261018/REFERENCE_STATUS.md`](../gold_compute/queue_20261018/REFERENCE_STATUS.md) | 当前参考值、稳定参照及科学验收限定 |
| [`../gold_compute/evidence/README.md`](../gold_compute/evidence/README.md) | 逐题证据索引、原件清单和缺件状态 |
| [`../gold_compute/evidence/DELIVERY.md`](../gold_compute/evidence/DELIVERY.md) / [`REPRODUCE.md`](../gold_compute/evidence/REPRODUCE.md) | Drive 下载入口、版本与校验信息、恢复及复现步骤 |
| [`../gold_compute/README.md`](../gold_compute/README.md) | Gold 策展与参考口径；归档材料不作为新待算队列 |
| `ideapool/reaction_candidates/*.md` | 存量 Benchmark 题源，与登记表一起生成正式 JSON |

## 当前题库与证据（2026-10-18）

正式题库在 `ideapool/tasks/{easy,normal,hard,impossible}/`，共 **50 题：20/10/10/10**。代码、题库 JSON、逐题说明与校验清单随仓库更新；原始输入、日志、几何和 Hessian 只放在 [Google Drive 交付包](https://drive.google.com/file/d/15YDa_ycWoLUANPsDdQ1rUOiNp_-wqOs5/view?usp=drivesdk)，按[复现说明](../gold_compute/evidence/REPRODUCE.md)恢复后审查。

交付包收录 886 份整理证据，31 题有选定原件；其余缺件、独立种子与真实 IRC 的区别、IB9 人工采信等限定均保留。题库能加载或工程检查通过，不等于所有题的原件和科学验收已经齐全。旧题库快照、试错 run 与旧待办报告不覆盖现行正式定义。

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

### 本轮根目录归档（2026-10-16）

- [化学工具接口进度记录](archive/chem-interface-2026-09-27-progress.md)：原 `.superpowers/chem-interface/progress.md`，保留原文，仅作历史记录。
- [NA1 空环境说明](archive/NA1_clean_env/README.md)：原 `archive/NA1_clean_env/README.md`，保留旧工作区布局说明；此处是文档档案，不是新的运行工作区。
- [F1 旧机理图来源说明](../gold_compute/archive/F1_root_snapshot/README.md)：原根目录 `mechanism_graph.json`；原图保留，不作为当前金标准或完整验收证据。

## 写作区（非本中心管辖）

- `paper/`：论文正文（`draft.md`、`main.tex`、`sections/`、
  `benchmark_construction_narrative.md`、`literature_gap_analysis.md`、
  `supplementary_information.md`）；
- [`paper/literature/`](../paper/literature/README.md)：文献原件与下载残留索引；
- `assets/`：标志原图；前端使用的静态资源仍在 `frontend/public/`；
- `知识卡片/`：知识卡片源档案，保持原路径。
- 申报材料、软著交付副本、答辩 PPT 及制作工作区已移出当前版本；需要旧材料时从 Git 历史恢复。
