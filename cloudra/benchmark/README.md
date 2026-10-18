# 运行当前 50 题 Benchmark

正式题库位于 `ideapool/tasks/{easy,normal,hard,impossible}/`，共 20/10/10/10 题。所有 Gold 图与数值来自对应登记源；证据归档中的 `task_gold/` 是历史快照，不是运行入口。

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

## 判分口径

- 综合分为图结构 0.1、自洽性 0.3、准确度 0.6。
- 反应能垒为纯电子能差，相对对应物种已经计算并验证的稳定极小值；同物种构象连接可共用最低能参照。构象转换步骤以其局部起始构象为参照。不同立体底物与独立通道接触体分开处理。
- IRC 证明实际连接；能量参照不必等于 IRC 直接落到的构象。同一 TS 的真实双向 IRC 末帧优化到身份正确、零虚频极小值即可接受方向证明，无需整条 IRC 跑到底。
- IMP 最终正确否定得分，错误宣称正确、可达或交付可信数值失分；探索后正确否定不扣。
- NB1_E2/NQ5_E2 按既定 PT 规则有意不设数值参考。IB9 首步为用户确认的 5.65；第二步为负例。

原始文件、参照值和保留项见 [当前参考状态](../../gold_compute/queue_20261018/REFERENCE_STATUS.md) 与 [原始证据归档](../../gold_compute/queue_20261018/evidence/README.md)。NR1 的成功 `ts_0042` 原件仍待补归档；HL1 endo 的真实 IRC 反应物端关联未闭环。这些事实保留，不伪称所有 Gold 均已自动通过严格验收。

## 检查

改动后运行语法检查、Ruff 和相关 Benchmark 模块测试；原生日志回放用于核对能垒提取和参照选择。工程测试通过、真实 Agent 运行完成与科学验收分别记录。
