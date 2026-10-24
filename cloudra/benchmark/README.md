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

## 参考证据与复现

[Google Drive下载入口及完整包校验值](../../gold_compute/evidence/DELIVERY.md) · [复现步骤](../../gold_compute/evidence/REPRODUCE.md) · [逐题索引](../../gold_compute/evidence/README.md)。

[P1b 四臂实验数据包](https://drive.google.com/file/d/1EFYWbJFuDSSgHv12yGF0ntHIxoIaSwSU/view?usp=drivesdk) · [复评分结果与脚本](https://drive.google.com/file/d/12JdoiLjiUpSlpRPu0P9Sl2nor6XLv16N/view?usp=drivesdk) · [包校验与解压说明](../../docs/benchmarks/P1B_DELIVERY.md)：包含 48 次先导运行及复评分材料，下载需要文件访问权限；与 Gold 参考证据分开保存。

Git包含正式50题、Gold、索引及哈希，原始参考输入/日志/几何仅在Drive交付包。运行Benchmark用Agent本次交付的日志评分，不会自动下载Gold原件；审查或回读参考计算时，先按复现说明下载并还原到`gold_compute/evidence/`。这些文件和本地ZIP已被Git忽略，不要重新提交。Drive当前需文件访问权限。

## 判分口径

- 综合分为图结构 0.1、自洽性 0.3、准确度 0.6。
- 反应能垒为纯电子能差，相对对应物种已经计算并验证的稳定极小值；同物种构象连接可共用最低能参照。构象转换步骤以其局部起始构象为参照。不同立体底物与独立通道接触体分开处理。
- IRC 证明实际连接；能量参照不必等于 IRC 直接落到的构象。同一 TS 的真实双向 IRC 末帧优化到身份正确、零虚频极小值即可接受方向证明，无需整条 IRC 跑到底。
- IMP 最终正确否定得分，错误宣称正确、可达或交付可信数值失分；探索后正确否定不扣。
- NB1_E2/NQ5_E2 按既定 PT 规则有意不设数值参考。IB9 首步为用户确认的 5.65；第二步为负例。

## 评分机制与公平性规范（2026-10-24 修正）

评测系统已在 P1b 先导实验后完成评分公平性修复，彻底杜绝“算对了因格式被误判”：
- **Schema 宽容度**：节点与边的 `properties` 允许列表等复杂类型（如 `evidence_log: ["opt.log", "freq.log"]`），忽略无害的扩展注释键，避免触发整图作废与 −1.0 罚分。
- **TS 多日志完整绑定**：自动遍历并绑定 TS 节点引用的所有可用原生日志（优化、频率、IRC），确保频率分析块被准确提取，不因首文件无频率而误判无鞍点。
- **产物同构选择性比对**：定性选择性通过产物物种同构性（`species_substitution_cost`）对齐优势通道，不再强求匹配题库未公开的内部字符串标签。
- 详情与先导 48 沙箱实测对照详见 [评分公平性修复](../../docs/benchmarks/SCORING_FAIRNESS_FIXES.md) 与 [P1b 重算明细](../../docs/benchmarks/p1b_rescored_results.csv)。

原始文件、参照值和保留项见 [当前参考状态](../../gold_compute/queue_20261018/REFERENCE_STATUS.md) 与 [证据索引](../../gold_compute/evidence/README.md)。NR1 的成功 `ts_0042` 原件仍待补归档；HL1 endo 的真实 IRC 反应物端关联未闭环。这些事实保留，不伪称所有 Gold 均已自动通过严格验收。

## 检查

改动后运行语法检查、Ruff 和相关 Benchmark 模块测试；原生日志回放用于核对能垒提取和参照选择。工程测试通过、真实 Agent 运行完成与科学验收分别记录。
