# TS 后端选型实验（Task 7）：前置状态与待批参数

> 对应计划 `docs/superpowers/plans/2026-09-11-chemical-structure-and-ts-workflow.md` 的 Task 7。
> **本实验尚未启动**：计划明确要求「用户批准方法与预算后才运行」，且「未完成实验前，不引入新
> 运行时依赖、不承诺所有体系均可自动找到 TS」。本文只记录**已具备的前置条件**、**待用户批准
> 的参数**与**比较口径**，不含任何实验结论、不含任何选型结论。

## 为什么现在写这份文件

第一、二阶段（Task 1–6）已经把 Task 7 需要的**可追溯底座**建好，并且都在测试里有护栏。
在这之前做后端选型会踩到同一个坑：任何"端到端跑通"的说法都无法与"给了好 XYZ"区分开。
因此本文的作用是把"底座的哪一部分已经可以用来做公平比较"写清楚，而不是提前给结论。

## 已具备的前置条件（有测试护栏）

| 能力 | 承担者 | 护栏 |
|---|---|---|
| 反应物/产物 SMILES → 逐组分结构 + 稳定原子身份 + 逐步力场轨迹 | `cloudra/tools/core/structure_builder.py` | `tests/test_structure_builder.py` |
| 多组分输入不被伪造成"复合物候选"（缺组装即 fail-loud） | `structure_builder.prepare_structure` | `test_multicomponent_produces_no_complex_candidate` |
| CREST 持久运行现场（命令行/输入/版本/日志/中间产物全留） | `cloudra/tools/core/crest_runner.py` | `tests/test_crest_runner.py` |
| 失败分层（初始优化失败 / 初始拓扑变化 / 搜索失败 / 超时 / 产物不完整 / 未知失败） | `crest_runner` | 同上（固定日志 + 真实引擎各一类） |
| 拓扑变更只记录不判定（片内/片间逐条列） | `cloudra/tools/core/topology_change.py` | `test_real_crest_topology_change_is_reported_not_judged` |
| 几何分析路径统一 + 结构化 Z-matrix 校验 | `cloudra/tools/chemcore/…`→`internal_coordinates.py` | `tests/test_internal_coordinates.py` |
| 失败作业几何仍可提取，但频率/TS 验证不被伪标完成 | `format_converter` / `dag/evidence_ingest.py` | `tests/test_compute_failed_job_artifacts.py` |

## 本机引擎事实（实测，供预算与可行性核对）

| 引擎 | 版本 | 关键能力核对 |
|---|---|---|
| CREST | 2.12（2022-05-19） | `-nci`（NCI 椭球势）存在；`--noreftopo` 存在且被解析器接受（见 `tests/fixtures/chemtool_issue33/README.md` 的"引擎能力核对"） |
| xTB | 6.7.1 独立 / CREST 2.12 内置声明兼容 6.4.0 | 独立 `xtb --opt` 可用于"预优化后交给 CREST"这条路线 |
| ORCA | 6.1.1 | NEB-TS 路线可用；注意本机 macOS 构建把主输出写 stdout，日志需经 `resolve_log_path` |
| RDKit | 2026.03.5 | MMFF94/UFF；`MinimizeTrajectory` 的 Snapshot 无 Python 绑定（见 `structure_artifacts.py` 说明） |
| autodE | **未安装** | 计划把它列为"待评估候选，尚未批准作为新依赖" |

## 待用户批准的参数（不批准不运行）

1. **候选后端集合**：计划给了两个候选——(a) autodE 的反应自动化流程；(b) 共享结构构建 +
   ORCA NEB-TS。是否两者都做，还是先做其中一个？
2. **测试体系**：计划要求从 #33 与既有任务池选择**多碎片 SN2、质子转移、分子内重排**三类。
   每类选几个体系、具体是哪几个（是否需要我先列候选清单供圈定）？
3. **方法与基组**：NEB-TS 的电子结构方法/基组、以及是否统一到现有 `method_policy` 白名单内。
4. **预算**：每类体系允许的 NEB 图像数、优化/频率/IRC 的计算步数上限与总机时上限
   （NEB-TS + 频率 + IRC 是三类作业，成本按体系规模放大）。
5. **输入契约**：是否要求 `reaction_search` 的输入必须是"两端 SMILES + 电荷/多重度"，
   还是也接受已知 XYZ 起点（计划明确"不能把给好 XYZ 当作端到端完成"，因此这决定评分口径）。
6. **多组分组装是否同时批准**（Task 2 的组装方案）：NEB-TS 需要合理的反应复合物起点；
   组装参数未批准前，多碎片体系的起点只能来自用户提供的 XYZ，从而**无法**评估"SMILES → TS"
   的真正端到端能力。

## 比较口径（计划要求，先写下来避免事后挪门槛）

- 全流程记录：输入校验 → 映射（含氢）→ 组装候选 → 路径 → TS 优化 → 频率与 IRC。
- 每个后端都记录：是否需要 agent 手工补救、计算耗费、可追溯性、**已验证结果数量**。
- "已验证"的判定沿用现有三态语义（`dag/evidence_ingest.py`）：没有频率数据就是**未验证**，
  不得计入已验证结果数量。
- 拆分作业与联合作业（含 ORCA 退出 139 的段错误形态）的对比属于 Task 6 遗留项：
  **仅在有计算授权后**进行，且不预先宣称"macOS 上必现"或"拆分必治"。

## 未复现项（必须如实标注）

- autodE 能否适配现有 scheduler / 方法白名单 / 取消与证据持久化：**未评估**（未安装、未批准）。
- 任何后端的实际成功率、耗时与可追溯性对比：**未实验**。
- issue #33 报告者那次 ORCA 段错误的原始日志、引擎版本与最小输入：不在本仓库内，**未复现**。
