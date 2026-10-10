# DAG 交付与科学校验边界修复验收

日期：2026-10-10。分支：`codex/dag-validation-boundaries`。基线：`161d023e`。

## 现场与修复范围

NU3 现场中，科学 complete 被拦住，但 Supervisor 允许 partial；独立评分仍未通过。此次修复工程入口、交付文件和展示边界，不更改方法、科学合格线、Gold、Benchmark 权重或不可达策略。

- 修复五配位磷环的显式/隐式氢表示不一致。现场 OXA 几何匹配环结构，不能因此把塌缩成环的 BET 认作开链；原有手性规则保持。
- 频率结果改为 `frequency_count_valid` / `frequency_data_present`，`mode_matched` 默认 false；描述不再声称身份或方向通过。
- `ts_opt` 独立要求原生优化收敛与同几何的单虚频证据。增加独立 `opt_file` 提交；两个直接阶段绑定入口也检查 Opt/Freq 同几何。
- 带跳过、豁免或空检查契约的范围完成显示 `scope_completed`。partial 的审批与科学 complete 分开。
- `mechanism_graph.json` 与 DAG 物种、步骤及声明范围对应。唯一端点映射允许交付文件使用不同步骤 ID，并在 receipt 保存对应关系；跨类型 ID 冲突、重复目标、遗漏目标与删除必需 TS 引用均拒绝。
- 能量声明须指向当前提交的不可变文件；原始日志字节、声明的具体几何及原生能量必须匹配。TS 能量不能借用另一份极小值日志。能垒核对明确起点/TS 日志的能量差；复用原有 1e-4 Ha 声明舍入允许量，两个操作数传播该允许量，不更改 Gold 准确度容差。非有限值拒绝。
- 部分交付审批绑定交付文件 SHA；新增、编辑或删除文件使旧审批失效。Benchmark DAG 退出必须先有交付文件；普通项目仍可没有该文件。
- stop 回执仅表示请求收到。候选答复在所有结束门禁放行及最终登记后才发布，等待审批或科学缺口期间不会成为公开最终答复。
- 审计前后读取同事务状态指纹；最终登记在 `BEGIN IMMEDIATE` 内再次检查状态并读取图版本。新图节点、同版本新审查、最终登记前的新证据均要求重新审计。
- 快照保存首次读出的字节，并核对快照和源文件实际 SHA。最终 receipt 固定不可变副本，文件变化不能生成与审批 SHA 不符的记录。

## 验证

使用已有项目 Python 环境，在独立测试数据目录验证。没有真实模型 API 请求或量化计算。

- `compileall cloudra tests`：通过。
- `ruff check cloudra tests`：通过。
- 22 个相关模块集中回归：**493 passed**，20.89 秒。覆盖 DAG store/engine、阶段绑定、真实文件科学检查、物种身份、审核、停止门禁、两个 Agent 协议、runtime adapters/pipeline、TS process、失败产物及异步静态护栏。
- Benchmark 能垒、准确度和组分绑定子集：**23 passed, 174 deselected**。
- 前端 completion 标签测试：通过。
- 前端 `tsc -b && vite build`：通过。保留现有 bundle 大小提示。
- 额外最终 StopTool / artifact 回归：通过。
- 两位只读审阅者独立复核，已报告的数据库竞态、快照竞态、错误 TS 日志、非有限值和 ID 覆盖问题均消除，无限定范围内剩余阻塞项。

本地测试没有运行全套 `pytest tests/`。五条 SWIG 依赖弃用提示不影响结果。

## 交付与验收边界

本次仅交付本地源码修复，未重启已有 Web/scheduler 服务，未推送远端。原 NU3 现场、计算产物与正式评分保留原值；这些回归不构成 NU3 科学成功或新评分。真实计算补齐和新 Benchmark 运行是后续独立验收。
