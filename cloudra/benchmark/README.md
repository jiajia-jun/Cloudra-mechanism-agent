# 运行当前 50 题 Benchmark

正式题库位于 `ideapool/tasks/{easy,normal,hard,impossible}/`，共 20/10/10/10 题。所有 Gold 图与数值来自对应登记源；旧证据快照中的 `task_gold/` 已移出当前证据包，不是运行入口。

## 启动

网页中的 Benchmark 面板选四个档位。运行机器须配置好模型、计算节点和对应软件；普通/困难题允许 xTB、PM7、B3LYP-D3(BJ)/def2-SVP，IMP 仅允许 xTB、PM7。xTB 方法的正式证据仍使用 ORCA/Gaussian 可解析的原生日志。

在仓库根目录启动命令行真实运行：

```bash
.venv/bin/python -m cloudra.benchmark \
  --backend runtime_v2 \
  --tasks-dir ideapool/tasks/easy \
  --tasks-dir ideapool/tasks/normal \
  --tasks-dir ideapool/tasks/hard \
  --tasks-dir ideapool/tasks/impossible \
  --data-dir benchmark_smoke_data/full50 \
  --concurrency 1
```

按计算节点容量调整并发。`--only NR1,NY3,HI1,HL1,IB9` 可限定任务。每次启动记录独立批次，结果、沙箱和运行事件保存在指定数据目录。默认命令行只选 easy 且 backend=none，是空运行，不代表真实评测。

## 数据与复现

[研究数据入口](../../docs/RESEARCH_DATA_CN.md)区分论文图表复算、P2 正式运行、P1b 先导运行与 Gold 参考计算。各数据包的版本、权限及上传状态只在对应交付页维护。

已经下载的 P2 完整归档（以及可选的 P1b Standard 主包）可以用一条命令重新评分。它调用 `BenchmarkRunner.score_sandbox`，有整理图时用整理图，否则用原生交付；Agent 和量化计算都不启动。SI 配套包仍负责按 CSV 重绘图表。写法、2026-11-02 准确度校正表和单题试跑见[归档重评分](../../docs/benchmarks/P2_DELIVERY.md#rescore-archived-deliveries)。

审查 Gold 时按[复现说明](../../gold_compute/evidence/REPRODUCE.md)下载和恢复原件；重新运行 Benchmark 使用本次 Agent 产生的日志评分，不会自动下载 Gold 原件。运行期即时评分是诊断快照，论文采用离线整理后的正式评分。

## 判分口径

- 运行阶段负责采集研究轨迹和原始计算产物；正式评估离线整理为统一机理图后评分。现有命令仍附带即时评分，该分数作为诊断快照。
- 离线整理允许依据该次运行已有记录恢复缺失 JSON、修复路径和换算已有数值；人工整理及字段来源要记录，各组使用同一规则。不能根据 Gold 新增研究结论或证据，原始交付完整性单独保留。
- 综合分为图结构 0.1、自洽性 0.3、准确度 0.6。
- 反应能垒为纯电子能差，相对对应物种已经计算并验证的稳定极小值；同物种构象连接可共用最低能参照。构象转换步骤以其局部起始构象为参照。不同立体底物与独立通道接触体分开处理。
- IRC 证明实际连接；能量参照不必等于 IRC 直接落到的构象。同一 TS 的真实双向 IRC 末帧优化到身份正确、零虚频极小值即可接受方向证明，无需整条 IRC 跑到底。
- IMP 最终正确否定得分，错误宣称正确、可达或交付可信数值失分；探索后正确否定不扣。
- NB1_E2/NQ5_E2 按既定 PT 规则有意不设数值参考。IB9 首步为用户确认的 5.65；第二步为负例。

## 历史评分修复

P1b 格式解析和证据关联修复见[评分公平性修复](../../docs/benchmarks/SCORING_FAIRNESS_FIXES.md)。[2026-10-24 四臂快照](../../docs/benchmarks/p1b_rescored_results.csv)与[2026-10-25 Standard 离线整理](../../docs/benchmarks/p1b_offline_20261025/README.md)是不同版本；后者不代表全部 48 次统一重评。

原始文件、参照值和保留项见 [当前参考状态](../../gold_compute/queue_20261018/REFERENCE_STATUS.md) 与 [证据索引](../../gold_compute/evidence/README.md)。NR1 的成功 `ts_0042` 原件仍待补归档；HL1 endo 的真实 IRC 反应物端关联未闭环。这些事实保留，不伪称所有 Gold 均已自动通过严格验收。

## 检查

改动后运行语法检查、Ruff 和相关 Benchmark 模块测试；原生日志回放用于核对能垒提取和参照选择。工程测试通过、真实 Agent 运行完成与科学验收分别记录。

## 评分细则

### 评分分量

| 评分项 | 权重 | 判定规则 | 人话解释 |
| :--- | :---: | :--- | :--- |
| **图结构相似度 (Graph)** | **10%** | 子图同构与覆盖率判定。交付图中多出的无关边不扣分，但关键边缺失或 `accessible` 状态颠倒会重罚。 | “你找没找到当前 Gold 参考中的关键机理主干？” |
| **物理自洽性 (Self-consistency)** | **30%** | **分级计分**：一阶鞍点 0.35、IRC 起点一致 0.15、两端端点 Opt/Freq 链 0.50（只通一侧给 0.25）。证据先按图上的绑定找，找不到时**在沙箱内检索**（按声明能量/几何剪枝，接受条件仍是 `verify_short_irc_direction` 通过）；`selfconsistency_passed` 仍按全有或全无记录，供科学验收口径使用。显式不可达目标直接记满分。 | “你算出来的每个分子结构在物理上站得住脚吗？有没有拿局部极大值冒充基态？” |
| **能垒准确度 (Accuracy)** | **60%** | 从 ORCA/Gaussian 真实日志中提取活化能垒，与黄金标准（Gold）比对。按高斯容差打分。 | “算出来的能垒和标准答案差多少 kcal/mol？” |

### 缺失与不一致证据

- **自洽失败不再倒扣图分**：图分只由 `graph_similarity` 决定；自洽层按上面三项分级扣分，同一件事只罚一次。
- **能垒声明兜底**：边没写 `barrier_kcal_mol` 时，用节点 `properties.energy_hartree` 的 `E(TS) − E(起点)` 按共享常量 `HARTREE_TO_KCAL_MOL` 反推，仍要求日志推算值与之一致。
- **造假 / 数据不一致 Fail-Loud 短路**：
  存在能垒证据时，若 Agent 声明的能垒既得不到任何合法日志组合支撑，交付证据也对不上参考答案，**评测触发短路：自洽性和准确度分量归零，最终得分仅保留 $0.1 \times \text{图分}$。** 证据包含与参考一致的合法组合时，沿用现有答案定义差异评分。
- **不完整交付按步骤扣分**：缺少目标步骤、缺日志推算或未声明能垒时，仅对应参考边的准确度记 0；分母仍包含全部 Gold 边，保留其他边、图结构和自洽项原有贡献。缺失扣分不受数值偏差扣分封顶保护，不因漏做获得保底分；部分得分不能代表完整机理通过科学验收。
